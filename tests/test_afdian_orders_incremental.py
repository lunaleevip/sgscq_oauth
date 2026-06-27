import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.afdian_orders_incremental import sync_incremental_orders


class AfdianOrdersIncrementalTest(unittest.TestCase):
    def test_sync_stops_after_seen_order_and_merges_only_new_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            checkpoint_path = repo / "afdian" / "order_checkpoint.json"
            checkpoint_path.parent.mkdir(parents=True)
            checkpoint_path.write_text(
                json.dumps({"version": 1, "processed_order_ids": ["old-order"]}),
                encoding="utf-8",
            )
            calls = []

            def fetch_page(page):
                calls.append(page)
                if page == 1:
                    return [
                        {
                            "out_trade_no": "new-order",
                            "user_id": "u1",
                            "show_amount": "5.00",
                            "status": 2,
                        },
                        {
                            "out_trade_no": "old-order",
                            "user_id": "u1",
                            "show_amount": "5.00",
                            "status": 2,
                        },
                    ]
                raise AssertionError("should stop before page 2")

            changed = sync_incremental_orders(repo, fetch_page, max_pages=5, generated_at=123)

            self.assertEqual(1, changed)
            self.assertEqual([1], calls)
            user = json.loads((repo / "afdian" / "users" / "u1.json").read_text(encoding="utf-8"))
            self.assertEqual(5.0, user["amount"])
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual("new-order", checkpoint["processed_order_ids"][0])
            self.assertIn("old-order", checkpoint["processed_order_ids"])

    def test_sync_reads_multiple_pages_until_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            calls = []

            def fetch_page(page):
                calls.append(page)
                if page == 1:
                    return [
                        {
                            "out_trade_no": "order1",
                            "user_id": "u1",
                            "show_amount": "5.00",
                            "status": 2,
                        }
                    ]
                return []

            changed = sync_incremental_orders(repo, fetch_page, max_pages=5, generated_at=123)

            self.assertEqual(1, changed)
            self.assertEqual([1, 2], calls)

    def test_sync_does_not_merge_order_already_recorded_in_user_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            user_dir = repo / "afdian" / "users"
            user_dir.mkdir(parents=True)
            (user_dir / "u1.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "updated_at": 100,
                        "user_id": "u1",
                        "amount": 5.0,
                        "level": 1,
                        "sponsor": True,
                        "orders": [{"out_trade_no": "order1", "amount": 5.0}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def fetch_page(page):
                if page == 1:
                    return [
                        {
                            "out_trade_no": "order1",
                            "user_id": "u1",
                            "show_amount": "5.00",
                            "status": 2,
                        }
                    ]
                return []

            changed = sync_incremental_orders(repo, fetch_page, max_pages=2, generated_at=123)

            self.assertEqual(0, changed)
            user = json.loads((user_dir / "u1.json").read_text(encoding="utf-8"))
            self.assertEqual(5.0, user["amount"])
            self.assertEqual([{"out_trade_no": "order1", "amount": 5.0}], user["orders"])


if __name__ == "__main__":
    unittest.main()
