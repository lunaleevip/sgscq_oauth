#!/usr/bin/env python3
"""Dump Afdian sponsor entitlements to the sgscq OAuth static repo.

Usage:
    export AFDIAN_USER_ID="..."
    export AFDIAN_TOKEN="..."
    export OAUTH_REPO_PATH="D:/Coder/sgscq_oauth"  # optional
    python tools/afdian_sponsors_dump.py

Outputs, only after a successful crawl:
    <OAUTH_REPO_PATH>/afdian/entitlements.json
    <OAUTH_REPO_PATH>/afdian/top100.json
    <OAUTH_REPO_PATH>/afdian/users/<user_id>.json
    <OAUTH_REPO_PATH>/afdian/sponsors.compact.txt
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


AFDIAN_USER_ID = os.environ.get("AFDIAN_USER_ID", "").strip()
AFDIAN_TOKEN = os.environ.get("AFDIAN_TOKEN", "").strip()
AFDIAN_API_BASE = os.environ.get("AFDIAN_API_BASE", "https://ifdian.net").rstrip("/")
OAUTH_REPO_PATH = Path(os.environ.get("OAUTH_REPO_PATH", "D:/Coder/sgscq_oauth"))

ORDER_PAGE_SLEEP_SEC = float(os.environ.get("AFDIAN_ORDER_PAGE_SLEEP_SEC", "0.4"))
SPONSOR_PAGE_SLEEP_SEC = float(os.environ.get("AFDIAN_SPONSOR_PAGE_SLEEP_SEC", "0.4"))
MAX_PAGES = int(os.environ.get("AFDIAN_MAX_PAGES", "1000"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def signed_body(params: dict[str, Any]) -> bytes:
    params_json = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
    ts = int(time.time())
    sign = md5_hex(AFDIAN_TOKEN + "params" + params_json + "ts" + str(ts) + "user_id" + AFDIAN_USER_ID)
    body = {
        "user_id": AFDIAN_USER_ID,
        "params": params_json,
        "ts": ts,
        "sign": sign,
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def post_signed_json(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{AFDIAN_API_BASE}/api/open/{endpoint}"
    req = urllib.request.Request(
        url,
        data=signed_body(params),
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def fetch_paginated(endpoint: str, sleep_sec: float) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    total_pages = 1
    page = 1

    while page <= total_pages and page <= MAX_PAGES:
        data = post_signed_json(endpoint, {"page": page})
        if int(data.get("ec", -1)) != 200:
            raise SystemExit(f"[ERROR] {endpoint} page {page} failed: ec={data.get('ec')} em={data.get('em')}")

        payload = data.get("data") or {}
        total_pages = int(payload.get("total_page") or payload.get("total_pages") or 1)
        page_items = payload.get("list") or []
        if not isinstance(page_items, list):
            raise SystemExit(f"[ERROR] {endpoint} page {page}: data.list is not a list")

        items.extend(x for x in page_items if isinstance(x, dict))
        print(f"[INFO] {endpoint} page {page}/{total_pages}: +{len(page_items)}, total {len(items)}")
        if page >= total_pages or not page_items:
            break
        page += 1
        time.sleep(sleep_sec)

    return items


def first_non_empty(obj: dict[str, Any] | None, *keys: str) -> str:
    if not obj:
        return ""
    for key in keys:
        value = obj.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "null":
            return text
    return ""


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def parse_amount(value: Any) -> float:
    try:
        return float(str(value).strip())
    except Exception:
        return 0.0


def money(value: float) -> float:
    return round(float(value) + 0.0000001, 2)


def money_text(value: float) -> str:
    value = money(value)
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}"


def level_for_amount(amount: float) -> int:
    if amount >= 5000:
        return 5
    if amount >= 1000:
        return 4
    if amount >= 500:
        return 3
    if amount >= 100:
        return 2
    if amount >= 5:
        return 1
    return 0


def is_completed_order(order: dict[str, Any]) -> bool:
    status = first_non_empty(order, "status", "order_status").lower()
    if status in {"2", "paid", "success", "finished", "complete", "completed"}:
        return True
    paid = order.get("is_paid", order.get("paid"))
    if isinstance(paid, bool):
        return paid
    return str(paid).lower() in {"1", "true", "yes"}


def extract_user_id(obj: dict[str, Any]) -> str:
    direct = first_non_empty(obj, "user_id", "uid", "id", "user_private_id")
    if direct:
        return direct
    user = as_dict(obj.get("user"))
    nested = first_non_empty(user, "user_id", "uid", "id", "user_private_id")
    if nested:
        return nested
    sponsor = as_dict(obj.get("sponsor"))
    nested = first_non_empty(sponsor, "user_id", "uid", "id", "user_private_id")
    if nested:
        return nested
    sponsor_user = as_dict(sponsor.get("user"))
    return first_non_empty(sponsor_user, "user_id", "uid", "id", "user_private_id")


def extract_name(obj: dict[str, Any]) -> str:
    direct = first_non_empty(obj, "name", "nickname", "user_name")
    if direct:
        return direct
    user = as_dict(obj.get("user"))
    nested = first_non_empty(user, "name", "nickname", "user_name")
    if nested:
        return nested
    sponsor = as_dict(obj.get("sponsor"))
    nested = first_non_empty(sponsor, "name", "nickname", "user_name")
    if nested:
        return nested
    sponsor_user = as_dict(sponsor.get("user"))
    return first_non_empty(sponsor_user, "name", "nickname", "user_name")


def extract_order_amount(order: dict[str, Any]) -> float:
    for key in ("total_amount", "show_amount", "pay_amount", "amount", "price"):
        amount = parse_amount(order.get(key))
        if amount > 0:
            return amount
    return 0.0


def extract_plan_name(obj: dict[str, Any]) -> str:
    direct = first_non_empty(obj, "plan_title", "plan_name", "product_name", "remark", "name", "title")
    if direct:
        return direct
    plans = obj.get("sponsor_plans")
    if isinstance(plans, list):
        for plan in plans:
            name = first_non_empty(as_dict(plan), "name", "plan_name", "title")
            if name:
                return name
    return ""


def extract_sponsor_amount(sponsor: dict[str, Any]) -> float:
    for key in ("all_sum_amount", "total_amount", "sum_amount", "pay_amount", "sponsor_amount"):
        amount = parse_amount(sponsor.get(key))
        if amount > 0:
            return amount
    total = 0.0
    plans = sponsor.get("sponsor_plans")
    if isinstance(plans, list):
        for plan in plans:
            total += parse_amount(as_dict(plan).get("price"))
    return total


def ensure_user(users: dict[str, dict[str, Any]], user_id: str) -> dict[str, Any]:
    if user_id not in users:
        users[user_id] = {
            "name": "",
            "avatar": "",
            "amount": 0.0,
            "level": 0,
            "plan_name": "",
            "sponsor": False,
        }
    return users[user_id]


def build_snapshot(
    orders: list[dict[str, Any]],
    sponsors: list[dict[str, Any]],
    generated_at: int | None = None,
) -> dict[str, Any]:
    users: dict[str, dict[str, Any]] = {}

    for order in orders:
        if not is_completed_order(order):
            continue
        user_id = extract_user_id(order)
        amount = extract_order_amount(order)
        if not user_id or amount <= 0:
            continue
        out = ensure_user(users, user_id)
        out["amount"] = money(float(out["amount"]) + amount)
        out["sponsor"] = True
        name = extract_name(order)
        plan_name = extract_plan_name(order)
        if name and not out["name"]:
            out["name"] = name
        if plan_name and not out["plan_name"]:
            out["plan_name"] = plan_name

    for sponsor in sponsors:
        user = as_dict(sponsor.get("user"))
        user_id = extract_user_id(user) or extract_user_id(sponsor)
        if not user_id:
            continue
        out = ensure_user(users, user_id)
        sponsor_amount = money(extract_sponsor_amount(sponsor))
        if float(out["amount"]) <= 0 and sponsor_amount > 0:
            out["amount"] = sponsor_amount
            out["sponsor"] = True
        name = extract_name(user) or extract_name(sponsor)
        avatar = first_non_empty(user, "avatar")
        plan_name = extract_plan_name(sponsor)
        if name:
            out["name"] = name
        if avatar:
            out["avatar"] = avatar
        if plan_name and not out["plan_name"]:
            out["plan_name"] = plan_name

    for user_id, out in users.items():
        out["amount"] = money(float(out["amount"]))
        out["level"] = level_for_amount(float(out["amount"]))
        out["sponsor"] = bool(out["amount"] > 0)
        if not out["name"]:
            out["name"] = user_id

    top = sorted(
        (
            {"user_id": user_id, **out}
            for user_id, out in users.items()
            if float(out["amount"]) > 0
        ),
        key=lambda row: (-float(row["amount"]), str(row["name"]).lower(), str(row["user_id"])),
    )[:100]

    return {
        "version": 1,
        "updated_at": int(generated_at if generated_at is not None else time.time()),
        "count": len(users),
        "users": dict(sorted(users.items())),
        "top100": top,
    }


def compact_lines(snapshot: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for index, row in enumerate(snapshot.get("top100") or [], start=1):
        lines.append(
            "\t".join(
                [
                    str(index),
                    str(row.get("user_id", "")),
                    str(row.get("name", "")),
                    money_text(parse_amount(row.get("amount", 0))),
                    str(row.get("level", 0)),
                ]
            )
        )
    return lines


def user_file_name(user_id: str) -> str:
    safe = urllib.parse.quote(user_id, safe="")
    if not safe:
        raise ValueError("empty user_id")
    return f"{safe}.json"


def top100_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": snapshot.get("version", 1),
        "updated_at": snapshot.get("updated_at", 0),
        "count": len(snapshot.get("top100") or []),
        "top100": snapshot.get("top100") or [],
    }


def user_payload(snapshot: dict[str, Any], user_id: str, user: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": snapshot.get("version", 1),
        "updated_at": snapshot.get("updated_at", 0),
        "user_id": user_id,
        "name": user.get("name", ""),
        "avatar": user.get("avatar", ""),
        "amount": user.get("amount", 0.0),
        "level": user.get("level", 0),
        "plan_name": user.get("plan_name", ""),
        "sponsor": user.get("sponsor", False),
    }


def clear_generated_user_files(users_dir: Path) -> None:
    if not users_dir.exists():
        return
    for path in users_dir.glob("*.json"):
        if path.is_file():
            path.unlink()


def write_outputs(out_dir: Path, snapshot: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "entitlements.json"
    top100_path = out_dir / "top100.json"
    compact_path = out_dir / "sponsors.compact.txt"
    users_dir = out_dir / "users"

    old_count = 0
    if json_path.exists():
        try:
            old = json.loads(json_path.read_text(encoding="utf-8"))
            old_count = int(old.get("count", 0))
        except Exception as exc:
            print(f"[WARN] could not parse existing {json_path}: {exc}")

    new_count = int(snapshot.get("count", 0))
    if old_count >= 20 and new_count < old_count // 2:
        raise SystemExit(
            f"[ERROR] new count {new_count} is < 50% of old count {old_count}; refusing to overwrite"
        )

    users_dir.mkdir(parents=True, exist_ok=True)
    clear_generated_user_files(users_dir)

    tmp_json = json_path.with_suffix(".json.tmp")
    tmp_top100 = top100_path.with_suffix(".json.tmp")
    tmp_compact = compact_path.with_suffix(".txt.tmp")
    tmp_json.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_top100.write_text(json.dumps(top100_payload(snapshot), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_compact.write_text("\n".join(compact_lines(snapshot)) + "\n", encoding="utf-8")
    tmp_json.replace(json_path)
    tmp_top100.replace(top100_path)

    for user_id, user in snapshot.get("users", {}).items():
        user_path = users_dir / user_file_name(str(user_id))
        tmp_user = user_path.with_suffix(".json.tmp")
        tmp_user.write_text(
            json.dumps(user_payload(snapshot, str(user_id), user), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp_user.replace(user_path)

    tmp_compact.replace(compact_path)

    print(f"[OK] wrote {json_path} ({json_path.stat().st_size} bytes)")
    print(f"[OK] wrote {top100_path} ({top100_path.stat().st_size} bytes)")
    print(f"[OK] wrote {len(snapshot.get('users', {}))} user files under {users_dir}")
    print(f"[OK] wrote {compact_path} ({compact_path.stat().st_size} bytes)")


def main() -> None:
    if not AFDIAN_USER_ID or not AFDIAN_TOKEN:
        print("[ERROR] AFDIAN_USER_ID and AFDIAN_TOKEN env vars are required.")
        sys.exit(1)
    if not OAUTH_REPO_PATH.exists():
        print(f"[ERROR] OAUTH_REPO_PATH does not exist: {OAUTH_REPO_PATH}")
        sys.exit(1)

    print(f"[INFO] dumping Afdian entitlements to {OAUTH_REPO_PATH / 'afdian'}")
    orders = fetch_paginated("query-order", ORDER_PAGE_SLEEP_SEC)
    sponsors = fetch_paginated("query-sponsor", SPONSOR_PAGE_SLEEP_SEC)
    snapshot = build_snapshot(orders, sponsors)
    if int(snapshot["count"]) <= 0:
        print("[ERROR] zero sponsor entitlements generated; refusing to overwrite snapshot.")
        sys.exit(1)
    write_outputs(OAUTH_REPO_PATH / "afdian", snapshot)
    print(f"[DONE] {snapshot['count']} users, {len(snapshot['top100'])} top entries.")


if __name__ == "__main__":
    main()
