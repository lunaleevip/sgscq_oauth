import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.afdian_webhook_merge import merge_order_payload


class AfdianWebhookMergeTest(unittest.TestCase):
    def test_paid_order_creates_user_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            payload = {
                "ec": 200,
                "data": {
                    "type": "order",
                    "order": {
                        "user_id": "u1",
                        "out_trade_no": "order1",
                        "total_amount": "5.00",
                        "show_amount": "5.00",
                        "status": 2,
                    },
                },
            }

            changed = merge_order_payload(repo, payload, generated_at=123)

            self.assertTrue(changed)
            user_path = repo / "afdian" / "users" / "u1.json"
            data = json.loads(user_path.read_text(encoding="utf-8"))
            self.assertEqual("u1", data["user_id"])
            self.assertEqual(5.0, data["amount"])
            self.assertEqual(1, data["level"])
            self.assertEqual(True, data["sponsor"])
            self.assertEqual(123, data["updated_at"])
            self.assertEqual([{"out_trade_no": "order1", "amount": 5.0}], data["orders"])
            checkpoint = json.loads((repo / "afdian" / "order_checkpoint.json").read_text(encoding="utf-8"))
            self.assertIn("order1", checkpoint["processed_order_ids"])

    def test_paid_order_uses_public_user_id_for_login_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            payload = {
                "ec": 200,
                "data": {
                    "type": "order",
                    "order": {
                        "user_id": "openapi-user",
                        "user_private_id": "oauth-user",
                        "out_trade_no": "order1",
                        "total_amount": "5.00",
                        "status": 2,
                    },
                },
            }

            changed = merge_order_payload(repo, payload, generated_at=123)

            self.assertTrue(changed)
            self.assertFalse((repo / "afdian" / "users" / "oauth-user.json").exists())
            data = json.loads((repo / "afdian" / "users" / "openapi-user.json").read_text(encoding="utf-8"))
            self.assertEqual("openapi-user", data["user_id"])
            self.assertEqual([{"out_trade_no": "order1", "amount": 5.0}], data["orders"])

    def test_paid_order_merges_into_existing_user_cache(self):
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
                        "name": "已有用户",
                        "avatar": "https://example.com/avatar.png",
                        "amount": 95.0,
                        "level": 1,
                        "plan_name": "旧方案",
                        "sponsor": True,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            payload = {
                "ec": 200,
                "data": {
                    "type": "order",
                    "order": {
                        "user_id": "u1",
                        "out_trade_no": "order2",
                        "show_amount": "10.00",
                        "status": "paid",
                    },
                },
            }

            changed = merge_order_payload(repo, payload, generated_at=200)

            self.assertTrue(changed)
            data = json.loads((user_dir / "u1.json").read_text(encoding="utf-8"))
            self.assertEqual("已有用户", data["name"])
            self.assertEqual("https://example.com/avatar.png", data["avatar"])
            self.assertEqual(105.0, data["amount"])
            self.assertEqual(2, data["level"])
            self.assertEqual("旧方案", data["plan_name"])
            self.assertEqual(200, data["updated_at"])
            self.assertEqual([{"out_trade_no": "order2", "amount": 10.0}], data["orders"])

    def test_duplicate_order_id_in_user_file_does_not_increment_amount_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            user_dir = repo / "afdian" / "users"
            user_dir.mkdir(parents=True)
            (user_dir / "u1.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "updated_at": 123,
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
            payload = {
                "ec": 200,
                "data": {
                    "type": "order",
                    "order": {
                        "user_id": "u1",
                        "out_trade_no": "order1",
                        "show_amount": "5.00",
                        "status": 2,
                    },
                },
            }

            self.assertFalse(merge_order_payload(repo, payload, generated_at=124))

            data = json.loads((repo / "afdian" / "users" / "u1.json").read_text(encoding="utf-8"))
            self.assertEqual(5.0, data["amount"])
            self.assertEqual(123, data["updated_at"])
            self.assertEqual([{"out_trade_no": "order1", "amount": 5.0}], data["orders"])

    def test_paid_order_without_order_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            payload = {
                "ec": 200,
                "data": {
                    "type": "order",
                    "order": {
                        "user_id": "u1",
                        "show_amount": "5.00",
                        "status": 2,
                    },
                },
            }

            changed = merge_order_payload(repo, payload, generated_at=123)

            self.assertFalse(changed)
            self.assertFalse((repo / "afdian" / "users" / "u1.json").exists())

    def test_unpaid_order_does_not_write_user_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            payload = {
                "ec": 200,
                "data": {
                    "type": "order",
                    "order": {
                        "user_id": "u1",
                        "show_amount": "5.00",
                        "status": 1,
                    },
                },
            }

            changed = merge_order_payload(repo, payload, generated_at=123)

            self.assertFalse(changed)
            self.assertFalse((repo / "afdian" / "users" / "u1.json").exists())


if __name__ == "__main__":
    unittest.main()
