import unittest
from pathlib import Path


class AfdianWorkflowTest(unittest.TestCase):
    def test_snapshot_commit_step_rebases_before_commit_and_retries_push(self):
        workflow = Path(".github/workflows/afdian-sponsors.yml").read_text(encoding="utf-8")

        self.assertIn("concurrency:", workflow)
        self.assertIn("git stash push --include-untracked", workflow)
        self.assertIn("git pull --rebase origin", workflow)
        self.assertIn("git push origin \"HEAD:${target_branch}\"", workflow)
        self.assertIn("for attempt in 1 2 3", workflow)
        self.assertIn("git ls-files --others --exclude-standard -- afdian/users", workflow)


if __name__ == "__main__":
    unittest.main()
