import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.afdian_sponsors_dump import build_snapshot, write_outputs


class AfdianSponsorsDumpTest(unittest.TestCase):
    def test_full_snapshot_user_files_include_order_ids_and_amounts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "afdian"
            orders = [
                {
                    "out_trade_no": "order1",
                    "user_id": "u1",
                    "show_amount": "5.00",
                    "status": 2,
                },
                {
                    "out_trade_no": "order2",
                    "user_id": "u1",
                    "total_amount": "10.00",
                    "status": "paid",
                },
                {
                    "out_trade_no": "order2",
                    "user_id": "u1",
                    "total_amount": "10.00",
                    "status": "paid",
                },
            ]

            snapshot = build_snapshot(orders, [], generated_at=123)
            write_outputs(out_dir, snapshot)

            user = json.loads((out_dir / "users" / "u1.json").read_text(encoding="utf-8"))
            self.assertEqual(15.0, user["amount"])
            self.assertEqual(
                [
                    {"out_trade_no": "order1", "amount": 5.0},
                    {"out_trade_no": "order2", "amount": 10.0},
                ],
                user["orders"],
            )
            checkpoint = json.loads((out_dir / "order_checkpoint.json").read_text(encoding="utf-8"))
            self.assertIn("order1", checkpoint["processed_order_ids"])
            self.assertIn("order2", checkpoint["processed_order_ids"])

    def test_full_snapshot_uses_private_user_id_for_login_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "afdian"
            orders = [
                {
                    "out_trade_no": "order1",
                    "user_id": "openapi-user",
                    "user_private_id": "oauth-user",
                    "show_amount": "5.00",
                    "status": 2,
                },
            ]

            snapshot = build_snapshot(orders, [], generated_at=123)
            write_outputs(out_dir, snapshot)

            self.assertFalse((out_dir / "users" / "openapi-user.json").exists())
            user = json.loads((out_dir / "users" / "oauth-user.json").read_text(encoding="utf-8"))
            self.assertEqual("oauth-user", user["user_id"])
            self.assertEqual([{"out_trade_no": "order1", "amount": 5.0}], user["orders"])

    def test_full_snapshot_clears_stale_user_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "afdian"
            users_dir = out_dir / "users"
            users_dir.mkdir(parents=True)
            (users_dir / "stale.json").write_text("{}", encoding="utf-8")

            snapshot = build_snapshot(
                [
                    {
                        "out_trade_no": "order1",
                        "user_id": "u1",
                        "show_amount": "5.00",
                        "status": 2,
                    }
                ],
                [],
                generated_at=123,
            )
            write_outputs(out_dir, snapshot)

            self.assertFalse((users_dir / "stale.json").exists())
            self.assertTrue((users_dir / "u1.json").exists())


if __name__ == "__main__":
    unittest.main()
