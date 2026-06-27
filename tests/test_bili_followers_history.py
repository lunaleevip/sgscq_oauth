import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.bili_followers_history_union import collect_history_followers


class BiliFollowersHistoryTest(unittest.TestCase):
    def test_collect_history_followers_unions_compact_snapshots_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            out_dir = repo / "bilibili"
            out_dir.mkdir()
            compact = out_dir / "followers.compact.txt"

            compact.write_text("3\n2\n1\n", encoding="utf-8")
            subprocess.run(["git", "add", "bilibili/followers.compact.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "first"], cwd=repo, check=True, stdout=subprocess.DEVNULL)

            compact.write_text("5\n4\n3\n", encoding="utf-8")
            subprocess.run(["git", "add", "bilibili/followers.compact.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "second"], cwd=repo, check=True, stdout=subprocess.DEVNULL)

            followers = collect_history_followers(repo, max_commits=10)

            self.assertEqual(["5", "4", "3", "2", "1"], followers)


if __name__ == "__main__":
    unittest.main()
