#!/usr/bin/env python3
"""Merge a paid Afdian order webhook into a single user cache file."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any


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


def parse_amount(value: Any) -> float:
    try:
        return float(str(value).strip())
    except Exception:
        return 0.0


def money(value: float) -> float:
    return round(float(value) + 0.0000001, 2)


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


def is_paid_order(payload: dict[str, Any]) -> bool:
    if int(payload.get("ec", -1)) != 200:
        return False
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if data.get("type") != "order":
        return False
    order = data.get("order") if isinstance(data.get("order"), dict) else {}
    status = first_non_empty(order, "status", "order_status").lower()
    return status in {"2", "paid", "success", "finished", "complete", "completed"}


def user_file_name(user_id: str) -> str:
    safe = urllib.parse.quote(user_id, safe="")
    if not safe:
        raise ValueError("empty user_id")
    return f"{safe}.json"


def order_amount(order: dict[str, Any]) -> float:
    for key in ("total_amount", "show_amount", "pay_amount", "amount", "price"):
        amount = parse_amount(order.get(key))
        if amount > 0:
            return amount
    return 0.0


def merge_order_payload(repo_path: Path, payload: dict[str, Any], generated_at: int | None = None) -> bool:
    if not is_paid_order(payload):
        return False

    order = payload["data"]["order"]
    user_id = first_non_empty(order, "user_id", "uid", "id", "user_private_id")
    amount = order_amount(order)
    if not user_id or amount <= 0:
        return False

    updated_at = int(generated_at if generated_at is not None else time.time())
    users_dir = repo_path / "afdian" / "users"
    users_dir.mkdir(parents=True, exist_ok=True)
    user_path = users_dir / user_file_name(user_id)

    current: dict[str, Any] = {}
    if user_path.exists():
        try:
            current = json.loads(user_path.read_text(encoding="utf-8"))
        except Exception:
            current = {}

    new_amount = money(parse_amount(current.get("amount")) + amount)
    plan_name = first_non_empty(current, "plan_name")
    if not plan_name:
        plan_name = first_non_empty(order, "plan_name", "plan_title", "product_name", "remark")

    merged = {
        "version": int(current.get("version") or 1),
        "updated_at": updated_at,
        "user_id": user_id,
        "name": first_non_empty(current, "name") or user_id,
        "avatar": first_non_empty(current, "avatar"),
        "amount": new_amount,
        "level": level_for_amount(new_amount),
        "plan_name": plan_name,
        "sponsor": True,
    }

    tmp = user_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(user_path)
    print(f"[OK] merged Afdian order into {user_path}")
    return True


def load_event_payload() -> dict[str, Any]:
    event_path = os.environ.get("GITHUB_EVENT_PATH", "").strip()
    if event_path:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        payload = event.get("client_payload")
        if isinstance(payload, dict) and "data" in payload:
            return payload
        if isinstance(payload, dict) and "order" in payload:
            return {"ec": 200, "data": {"type": "order", "order": payload["order"]}}
        if isinstance(payload, dict):
            return {"ec": 200, "data": {"type": "order", "order": payload}}
        return event
    return json.load(sys.stdin)


def main() -> None:
    repo_path = Path(os.environ.get("OAUTH_REPO_PATH", ".")).resolve()
    payload = load_event_payload()
    changed = merge_order_payload(repo_path, payload)
    if not changed:
        print("[INFO] no paid Afdian order found; nothing changed")


if __name__ == "__main__":
    main()
