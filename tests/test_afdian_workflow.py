import unittest
from pathlib import Path


class AfdianWorkflowTest(unittest.TestCase):
    def test_snapshot_commit_step_rebases_before_commit_and_retries_push(self):
        workflow = Path(".github/workflows/afdian-sponsors.yml").read_text(encoding="utf-8")

        self.assertIn("concurrency:", workflow)
        self.assertIn("full_sync:", workflow)
        self.assertIn("python tools/afdian_orders_incremental.py", workflow)
        self.assertIn("git stash push --include-untracked", workflow)
        self.assertIn("git pull --rebase origin", workflow)
        self.assertIn("git push origin \"HEAD:${target_branch}\"", workflow)
        self.assertIn("for attempt in 1 2 3", workflow)
        self.assertIn("afdian/order_checkpoint.json", workflow)
        self.assertIn("git ls-files --others --exclude-standard -- afdian/users", workflow)

    def test_scheduled_workflows_run_every_five_minutes(self):
        afdian = Path(".github/workflows/afdian-sponsors.yml").read_text(encoding="utf-8")
        bili = Path(".github/workflows/bili-followers.yml").read_text(encoding="utf-8")

        self.assertIn('cron: "*/5 * * * *"', afdian)
        self.assertIn("cron: '*/5 * * * *'", bili)
        self.assertIn("for attempt in 1 2 3", bili)


if __name__ == "__main__":
    unittest.main()
