import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.douyin_followers_dump import (
    extract_follower_ids,
    merge_followers,
    next_cursor,
    page_items,
    should_continue,
    write_outputs,
)


class DouyinFollowersDumpTest(unittest.TestCase):
    def test_extract_follower_ids_accepts_common_douyin_identity_fields(self):
        item = {
            "uid": "uid-1",
            "unique_id": "unique-1",
            "short_id": "short-1",
            "sec_uid": "sec-1",
            "sec_user_id": "sec-user-1",
        }

        self.assertEqual(
            ["uid-1", "unique-1", "short-1", "sec-1", "sec-user-1"],
            extract_follower_ids(item),
        )

    def test_page_items_supports_common_response_shapes(self):
        self.assertEqual([{"uid": "1"}], page_items({"followers": [{"uid": "1"}]}))
        self.assertEqual([{"uid": "2"}], page_items({"data": {"followers": [{"uid": "2"}]}}))
        self.assertEqual([{"uid": "3"}], page_items({"data": {"list": [{"uid": "3"}]}}))
        self.assertEqual([{"uid": "4"}], page_items({"user_list": [{"uid": "4"}]}))

    def test_cursor_and_has_more_support_common_fields(self):
        self.assertEqual("99", next_cursor({"data": {"max_time": 99}}))
        self.assertEqual("101", next_cursor({"cursor": 101}))
        self.assertEqual(True, should_continue({"data": {"has_more": 1}}))
        self.assertEqual(False, should_continue({"has_more": 0}))

    def test_incremental_merge_preserves_existing_followers(self):
        merged = merge_followers(["3", "2", "1"], ["5", "4", "3"])

        self.assertEqual(["5", "4", "3", "2", "1"], merged)

    def test_write_outputs_keeps_json_sorted_and_compact_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "douyin"

            write_outputs(out_dir, "target-sec-id", ["5", "4", "3", "2", "1"], generated_at=123)

            payload = json.loads((out_dir / "followers.json").read_text(encoding="utf-8"))
            self.assertEqual("douyin", payload["platform"])
            self.assertEqual("target-sec-id", payload["target_id"])
            self.assertEqual(5, payload["count"])
            self.assertEqual(["1", "2", "3", "4", "5"], payload["followers"])
            compact = (out_dir / "followers.compact.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(["5", "4", "3", "2", "1"], compact)


if __name__ == "__main__":
    unittest.main()
