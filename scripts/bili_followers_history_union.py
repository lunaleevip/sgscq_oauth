#!/usr/bin/env python3
"""Union Bilibili follower snapshots from git history."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from .bili_followers_dump import merge_followers, read_existing_followers, write_outputs
except ImportError:
    from bili_followers_dump import merge_followers, read_existing_followers, write_outputs


SNAPSHOT_PATHS = ["bilibili/followers.compact.txt", "bilibili/followers.json"]


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def parse_snapshot(path: str, content: str) -> list[str]:
    if path.endswith(".compact.txt"):
        return [line.strip() for line in content.splitlines() if line.strip()]
    try:
        payload = json.loads(content)
    except Exception:
        return []
    followers = payload.get("followers") or []
    return [str(mid).strip() for mid in followers if str(mid).strip()]


def collect_history_followers(repo: Path, max_commits: int = 200) -> list[str]:
    merged: list[str] = []

    revs_text = git(repo, "rev-list", f"--max-count={max_commits}", "HEAD", "--", *SNAPSHOT_PATHS).stdout
    for rev in [line.strip() for line in revs_text.splitlines() if line.strip()]:
        for path in SNAPSHOT_PATHS:
            shown = git(repo, "show", f"{rev}:{path}", check=False)
            if shown.returncode != 0:
                continue
            merged = merge_followers(merged, parse_snapshot(path, shown.stdout))
    merged = merge_followers(merged, read_existing_followers(repo / "bilibili"))
    return merged


def main() -> None:
    repo = Path(os.environ.get("OAUTH_REPO_PATH", ".")).resolve()
    up_mid = os.environ.get("BILI_UP_MID", "173883695").strip()
    max_commits = int(os.environ.get("BILI_HISTORY_MAX_COMMITS", "200"))
    followers = collect_history_followers(repo, max_commits=max_commits)
    if not followers:
        print("[ERROR] no followers found in git history")
        sys.exit(1)
    write_outputs(repo / "bilibili", up_mid, followers)
    print(f"[DONE] unioned {len(followers)} followers from git history.")


if __name__ == "__main__":
    main()
