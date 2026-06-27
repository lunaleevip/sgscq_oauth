import unittest
from pathlib import Path


class AfdianWorkflowTest(unittest.TestCase):
    def test_snapshot_commit_step_rebases_before_commit_and_retries_push(self):
        workflow = Path(".github/workflows/afdian-sync-fast.yml").read_text(encoding="utf-8")

        self.assertIn("concurrency:", workflow)
        self.assertIn("full_sync:", workflow)
        self.assertIn("types: [afdian_order, afdian_incremental]", workflow)
        self.assertIn("python tools/afdian_orders_incremental.py", workflow)
        self.assertIn("github.event.action == 'afdian_incremental'", workflow)
        self.assertIn("git stash push --include-untracked", workflow)
        self.assertIn("git pull --rebase origin", workflow)
        self.assertIn("git push origin \"HEAD:${target_branch}\"", workflow)
        self.assertIn("for attempt in 1 2 3", workflow)
        self.assertIn("afdian/order_checkpoint.json", workflow)
        self.assertIn("git ls-files --others --exclude-standard -- afdian/users", workflow)

    def test_scheduled_workflows_run_every_five_minutes(self):
        afdian = Path(".github/workflows/afdian-sync-fast.yml").read_text(encoding="utf-8")
        bili = Path(".github/workflows/bili-followers-fast.yml").read_text(encoding="utf-8")

        self.assertIn('cron: "1,6,11,16,21,26,31,36,41,46,51,56 * * * *"', afdian)
        self.assertIn("cron: '1,6,11,16,21,26,31,36,41,46,51,56 * * * *'", bili)
        self.assertIn("types: [bili_followers]", bili)
        self.assertIn("full_sync:", bili)
        self.assertIn("BILI_SYNC_MODE:", bili)
        self.assertIn("fetch-depth: 0", bili)
        self.assertIn("python scripts/bili_followers_history_union.py", bili)
        self.assertIn("for attempt in 1 2 3", bili)

    def test_external_cron_dispatches_both_sync_events(self):
        script = Path("tools/oauth_sync_dispatch_cron.php").read_text(encoding="utf-8")

        self.assertIn("'afdian_incremental'", script)
        self.assertIn("'bili_followers'", script)
        self.assertIn("GITHUB_DISPATCH_TOKEN", script)
        self.assertIn("https://api.github.com/repos/{$repo}/dispatches", script)


if __name__ == "__main__":
    unittest.main()
