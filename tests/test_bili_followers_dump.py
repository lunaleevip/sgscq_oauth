import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.bili_followers_dump import followers_for_sync, merge_followers, write_outputs


class BiliFollowersDumpTest(unittest.TestCase):
    def test_incremental_merge_preserves_existing_followers(self):
        merged = merge_followers(["3", "2", "1"], ["5", "4", "3"])

        self.assertEqual(["5", "4", "3", "2", "1"], merged)

    def test_incremental_fetch_failure_keeps_existing_snapshot_when_allowed(self):
        def failing_fetch():
            raise SystemExit("[ERROR] page 1 returned code=-352 message=-352")

        followers = followers_for_sync(
            existing_followers=["3", "2", "1"],
            sync_mode="incremental",
            fetch_recent=failing_fetch,
            allow_existing_on_incremental_error=True,
        )

        self.assertEqual(["3", "2", "1"], followers)

    def test_write_outputs_keeps_json_sorted_and_compact_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "bilibili"

            write_outputs(out_dir, "173883695", ["5", "4", "3", "2", "1"], generated_at=123)

            payload = json.loads((out_dir / "followers.json").read_text(encoding="utf-8"))
            self.assertEqual(5, payload["count"])
            self.assertEqual(["1", "2", "3", "4", "5"], payload["followers"])
            compact = (out_dir / "followers.compact.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(["5", "4", "3", "2", "1"], compact)


if __name__ == "__main__":
    unittest.main()
