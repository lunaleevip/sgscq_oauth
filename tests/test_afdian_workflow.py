import unittest
from pathlib import Path


class AfdianWorkflowTest(unittest.TestCase):
    def test_afdian_checkout_does_not_depend_on_external_actions(self):
        workflow = Path(".github/workflows/afdian-sync-fast.yml").read_text(encoding="utf-8")

        self.assertNotIn("uses: actions/checkout", workflow)
        self.assertIn("GH_REPO_TOKEN: ${{ github.token }}", workflow)
        self.assertIn("git init .", workflow)
        self.assertIn("git fetch --depth=2 origin", workflow)
        self.assertIn("git checkout -B \"${target_branch}\" FETCH_HEAD", workflow)

    def test_snapshot_commit_step_rebases_before_commit_and_retries_push(self):
        workflow = Path(".github/workflows/afdian-sync-fast.yml").read_text(encoding="utf-8")

        self.assertIn("concurrency:", workflow)
        self.assertIn("full_sync:", workflow)
        self.assertIn("types: [afdian_order, afdian_incremental, afdian_full]", workflow)
        self.assertIn("python tools/afdian_orders_incremental.py", workflow)
        self.assertIn("github.event.action == 'afdian_incremental'", workflow)
        self.assertIn("github.event.action == 'afdian_full'", workflow)
        self.assertIn("git stash push --include-untracked", workflow)
        self.assertIn("git pull --rebase origin", workflow)
        self.assertIn("git push origin \"HEAD:${target_branch}\"", workflow)
        self.assertIn("for attempt in 1 2 3", workflow)
        self.assertIn("afdian/order_checkpoint.json", workflow)
        self.assertIn("git ls-files --others --exclude-standard -- afdian/users", workflow)

    def test_scheduled_workflows_use_reduced_social_frequency(self):
        afdian = Path(".github/workflows/afdian-sync-fast.yml").read_text(encoding="utf-8")
        bili = Path(".github/workflows/bili-followers-fast.yml").read_text(encoding="utf-8")
        douyin = Path(".github/workflows/douyin-followers-fast.yml").read_text(encoding="utf-8")

        self.assertIn('cron: "2,12,22,32,42,52 * * * *"', afdian)
        self.assertIn('cron: "7 * * * *"', afdian)
        self.assertIn("github.event.schedule == '7 * * * *'", afdian)
        self.assertIn("cron: '2 */2 * * *'", bili)
        self.assertIn("cron: '17 */12 * * *'", bili)
        self.assertIn("types: [bili_followers, bili_followers_full]", bili)
        self.assertIn("github.event.action == 'bili_followers_full'", bili)
        self.assertIn("github.event.schedule == '17 */12 * * *'", bili)
        self.assertIn("full_sync:", bili)
        self.assertIn("BILI_SYNC_MODE:", bili)
        self.assertIn("fetch-depth: 0", bili)
        self.assertIn("python scripts/bili_followers_history_union.py", bili)
        self.assertIn("for attempt in 1 2 3", bili)
        self.assertIn("schedule:", douyin)
        self.assertIn("cron: '22 */2 * * *'", douyin)
        self.assertIn("cron: '37 */12 * * *'", douyin)
        self.assertIn("types: [douyin_followers, douyin_followers_full]", douyin)
        self.assertIn("github.event.action == 'douyin_followers_full'", douyin)
        self.assertIn("github.event.schedule == '37 */12 * * *'", douyin)
        self.assertIn("DOUYIN_ENABLED:", douyin)
        self.assertIn("DOUYIN_REFERER_URL:", douyin)
        self.assertIn("DOUYIN_EXTRA_HEADERS:", douyin)
        self.assertIn("secret DOUYIN_ENABLED is not true", douyin)
        self.assertIn("DOUYIN_SYNC_MODE:", douyin)
        self.assertIn("python scripts/douyin_followers_dump.py", douyin)
        self.assertIn("No Douyin snapshot files.", douyin)
        self.assertIn("for attempt in 1 2 3", douyin)

    def test_external_cron_dispatches_afdian_and_bili_events(self):
        script = Path("tools/oauth_sync_dispatch_cron.php").read_text(encoding="utf-8")

        self.assertIn("'afdian_incremental'", script)
        self.assertIn("'afdian_full'", script)
        self.assertIn("sgscq_afdian_full_hour", script)
        self.assertIn("'bili_followers'", script)
        self.assertIn("'bili_followers_full'", script)
        self.assertIn("sgscq_bili_incremental_slot", script)
        self.assertIn("sgscq_bili_full_slot", script)
        self.assertIn("'douyin_followers'", script)
        self.assertIn("'douyin_followers_full'", script)
        self.assertIn("sgscq_douyin_incremental_slot", script)
        self.assertIn("sgscq_douyin_full_slot", script)
        self.assertIn("intdiv((int) gmdate('G'), 2)", script)
        self.assertIn("intdiv((int) gmdate('G'), 12)", script)
        self.assertIn("GITHUB_DISPATCH_TOKEN", script)
        self.assertIn("https://api.github.com/repos/{$repo}/dispatches", script)


if __name__ == "__main__":
    unittest.main()
