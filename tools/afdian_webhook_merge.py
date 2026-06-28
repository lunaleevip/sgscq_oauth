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

MAX_CHECKPOINT_ORDER_IDS = 2000


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


def order_id(order: dict[str, Any]) -> str:
    return first_non_empty(order, "out_trade_no", "trade_no", "order_id", "id")


def order_user_id(order: dict[str, Any]) -> str:
    return first_non_empty(order, "user_private_id", "user_id", "uid", "id")


def order_rows(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return rows
    seen = set()
    for row in value:
        if not isinstance(row, dict):
            continue
        oid = first_non_empty(row, "out_trade_no", "trade_no", "order_id", "id")
        amount = order_amount(row)
        if not oid or oid in seen or amount <= 0:
            continue
        rows.append({"out_trade_no": oid, "amount": amount})
        seen.add(oid)
    return rows


def checkpoint_path(repo_path: Path) -> Path:
    return repo_path / "afdian" / "order_checkpoint.json"


def load_checkpoint(repo_path: Path) -> dict[str, Any]:
    path = checkpoint_path(repo_path)
    if not path.exists():
        return {"version": 1, "processed_order_ids": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "processed_order_ids": []}
    ids = data.get("processed_order_ids")
    if not isinstance(ids, list):
        ids = []
    return {
        "version": int(data.get("version") or 1),
        "updated_at": int(data.get("updated_at") or 0),
        "processed_order_ids": [str(x) for x in ids if str(x).strip()],
    }


def save_checkpoint(repo_path: Path, checkpoint: dict[str, Any], updated_at: int) -> None:
    path = checkpoint_path(repo_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ids = []
    seen = set()
    for value in checkpoint.get("processed_order_ids") or []:
        text = str(value).strip()
        if text and text not in seen:
            ids.append(text)
            seen.add(text)
        if len(ids) >= MAX_CHECKPOINT_ORDER_IDS:
            break
    data = {
        "version": int(checkpoint.get("version") or 1),
        "updated_at": updated_at,
        "processed_order_ids": ids,
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def merge_order_payload(repo_path: Path, payload: dict[str, Any], generated_at: int | None = None) -> bool:
    if not is_paid_order(payload):
        return False

    order = payload["data"]["order"]
    user_id = order_user_id(order)
    amount = order_amount(order)
    current_order_id = order_id(order)
    if not user_id or not current_order_id or amount <= 0:
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

    orders = order_rows(current.get("orders"))
    if current_order_id in {row["out_trade_no"] for row in orders}:
        print(f"[INFO] Afdian order already exists in user cache: {current_order_id}")
        return False
    orders.append({"out_trade_no": current_order_id, "amount": amount})

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
        "orders": orders,
    }

    tmp = user_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(user_path)
    checkpoint = load_checkpoint(repo_path)
    processed = checkpoint.get("processed_order_ids") or []
    checkpoint["processed_order_ids"] = [current_order_id] + processed
    save_checkpoint(repo_path, checkpoint, updated_at)
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
