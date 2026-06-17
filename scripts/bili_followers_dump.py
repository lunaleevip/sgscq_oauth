#!/usr/bin/env python3
"""Dump current B 站 followers list to sgscq_oauth GitHub Pages.

Usage:
    export BILI_COOKIE="SESSDATA=...; bili_jct=...; DedeUserID=..."
    export BILI_UP_MID="173883695"            # optional, default 173883695
    export OAUTH_REPO_PATH="D:/Coder/sgscq_oauth"  # optional
    python tools/bili_followers_dump.py

Outputs (only after fully successful crawl):
    <OAUTH_REPO_PATH>/bilibili/followers.json
    <OAUTH_REPO_PATH>/bilibili/followers.compact.txt

Does NOT auto-commit / push — review the diff first, then:
    cd <OAUTH_REPO_PATH>
    git add bilibili/followers.json bilibili/followers.compact.txt
    git commit -m "chore: weekly follower snapshot YYYY-MM-DD"
    git push
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


BILI_COOKIE = os.environ.get("BILI_COOKIE", "").strip()
BILI_UP_MID = os.environ.get("BILI_UP_MID", "173883695").strip()
# 默认指向脚本所在仓库根（适配 GitHub Actions 的 ${{ github.workspace }}）。
# 本地跑可用 OAUTH_REPO_PATH 环境变量覆盖。
_default_repo = Path(__file__).resolve().parent.parent
OAUTH_REPO_PATH = Path(os.environ.get("OAUTH_REPO_PATH", str(_default_repo)))

PAGE_SIZE = 50               # B 站官方上限
PAGE_SLEEP_SEC = 1.5         # 每页之间的间隔，避免 412
MAX_PAGES = 1000             # 兜底：5 万粉丝
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def http_get_json(url: str, cookie: str) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Cookie": cookie,
        "Referer": f"https://space.bilibili.com/{BILI_UP_MID}",
        "Accept": "application/json, text/plain, */*",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def fetch_followers(cookie: str, up_mid: str) -> list[str]:
    """Crawl all pages of /x/relation/followers, return list of mid as str."""
    seen: set[str] = set()
    ordered: list[str] = []

    for page in range(1, MAX_PAGES + 1):
        params = {
            "vmid": up_mid,
            "pn": page,
            "ps": PAGE_SIZE,
            "order": "desc",
            "order_type": "attention",
        }
        url = "https://api.bilibili.com/x/relation/followers?" + urllib.parse.urlencode(params)
        try:
            data = http_get_json(url, cookie)
        except Exception as e:
            raise SystemExit(f"[ERROR] page {page} HTTP failed: {e}")

        code = data.get("code", -1)
        if code != 0:
            raise SystemExit(
                f"[ERROR] page {page} returned code={code} message={data.get('message')}"
            )

        payload = data.get("data") or {}
        items = payload.get("list") or []
        if not items:
            print(f"[INFO] page {page}: no more followers, stop.")
            break

        new_count = 0
        for item in items:
            mid_raw = item.get("mid")
            if mid_raw is None:
                continue
            mid = str(mid_raw)
            if mid in seen:
                continue
            seen.add(mid)
            ordered.append(mid)
            new_count += 1

        total = payload.get("total", -1)
        print(f"[INFO] page {page}: +{new_count} new, total seen {len(ordered)} (server total={total})")

        if len(items) < PAGE_SIZE:
            print(f"[INFO] page {page}: short page, stop.")
            break

        time.sleep(PAGE_SLEEP_SEC)

    return ordered


def write_outputs(out_dir: Path, up_mid: str, followers: list[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # followers.json: numeric sort — stable diff between snapshots, human review.
    sorted_mids = sorted(followers, key=lambda x: int(x))

    payload = {
        "version": 1,
        "up_mid": up_mid,
        "generated_at": int(time.time()),
        "count": len(sorted_mids),
        "followers": sorted_mids,
    }

    json_path = out_dir / "followers.json"
    compact_path = out_dir / "followers.compact.txt"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # followers.compact.txt: keep crawl order (newest follow first) — App can stream-match
    # and disconnect early. Most users querying right after they follow hit the first KB.
    compact_path.write_text("\n".join(followers) + ("\n" if followers else ""), encoding="utf-8")

    print(f"[OK] wrote {json_path}  ({json_path.stat().st_size} bytes, sorted)")
    print(f"[OK] wrote {compact_path}  ({compact_path.stat().st_size} bytes, newest-first)")


def main() -> None:
    if not BILI_COOKIE:
        print("[ERROR] BILI_COOKIE env var is empty.")
        print("        Login bilibili.com in your browser, copy SESSDATA / bili_jct / DedeUserID,")
        print('        then: export BILI_COOKIE="SESSDATA=xxx; bili_jct=xxx; DedeUserID=xxx"')
        sys.exit(1)

    if not OAUTH_REPO_PATH.exists():
        print(f"[ERROR] OAUTH_REPO_PATH does not exist: {OAUTH_REPO_PATH}")
        sys.exit(1)

    out_dir = OAUTH_REPO_PATH / "bilibili"
    print(f"[INFO] dumping followers of vmid={BILI_UP_MID} → {out_dir}")

    followers = fetch_followers(BILI_COOKIE, BILI_UP_MID)
    if not followers:
        print("[ERROR] zero followers crawled — refusing to overwrite snapshot.")
        sys.exit(1)

    # Guard against suspicious shrinkage: if existing snapshot has >2× more followers,
    # something likely went wrong (cookie expired mid-crawl, etc.). Refuse to clobber.
    existing_json = out_dir / "followers.json"
    if existing_json.exists():
        try:
            old = json.loads(existing_json.read_text(encoding="utf-8"))
            old_count = int(old.get("count", 0))
            if old_count >= 50 and len(followers) < old_count // 2:
                print(
                    f"[ERROR] new count {len(followers)} is < 50% of old count {old_count}. "
                    "Refusing to overwrite. If this is intentional, delete the existing file first."
                )
                sys.exit(1)
        except Exception as e:
            print(f"[WARN] could not parse existing followers.json: {e}")

    write_outputs(out_dir, BILI_UP_MID, followers)
    print(f"[DONE] {len(followers)} followers crawled.")
    print()
    print("Next steps (review then push):")
    print(f"  cd {OAUTH_REPO_PATH}")
    print(f"  git diff bilibili/followers.json")
    print(f"  git add bilibili/followers.json bilibili/followers.compact.txt")
    print(f'  git commit -m "chore: weekly follower snapshot $(date +%F)"')
    print(f"  git push")


if __name__ == "__main__":
    main()
