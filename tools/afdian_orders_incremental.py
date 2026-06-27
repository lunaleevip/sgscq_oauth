#!/usr/bin/env python3
"""Incrementally merge recent Afdian orders into per-user cache files."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable

try:
    from . import afdian_sponsors_dump
    from .afdian_webhook_merge import load_checkpoint, merge_order_payload, order_id
except ImportError:
    import afdian_sponsors_dump
    from afdian_webhook_merge import load_checkpoint, merge_order_payload, order_id


DEFAULT_MAX_PAGES = 5


def order_payload(order: dict[str, Any]) -> dict[str, Any]:
    return {"ec": 200, "data": {"type": "order", "order": order}}


def sync_incremental_orders(
    repo_path: Path,
    fetch_page: Callable[[int], list[dict[str, Any]]],
    max_pages: int = DEFAULT_MAX_PAGES,
    generated_at: int | None = None,
) -> int:
    changed = 0
    stop = False
    processed = set(load_checkpoint(repo_path).get("processed_order_ids") or [])
    updated_at = int(generated_at if generated_at is not None else time.time())

    for page in range(1, max_pages + 1):
        orders = fetch_page(page)
        print(f"[INFO] query-order page {page}: +{len(orders)}")
        if not orders:
            break
        for order in orders:
            oid = order_id(order)
            if oid and oid in processed:
                print(f"[INFO] reached processed Afdian order: {oid}")
                stop = True
                break
            if merge_order_payload(repo_path, order_payload(order), generated_at=updated_at):
                changed += 1
                if oid:
                    processed.add(oid)
        if stop:
            break
        time.sleep(float(os.environ.get("AFDIAN_ORDER_PAGE_SLEEP_SEC", "0.4")))

    print(f"[DONE] merged {changed} recent Afdian orders.")
    return changed


def fetch_order_page(page: int) -> list[dict[str, Any]]:
    data = afdian_sponsors_dump.post_signed_json("query-order", {"page": page})
    if int(data.get("ec", -1)) != 200:
        raise SystemExit(f"[ERROR] query-order page {page} failed: ec={data.get('ec')} em={data.get('em')}")
    payload = data.get("data") or {}
    page_items = payload.get("list") or []
    if not isinstance(page_items, list):
        raise SystemExit(f"[ERROR] query-order page {page}: data.list is not a list")
    return [x for x in page_items if isinstance(x, dict)]


def main() -> None:
    if not afdian_sponsors_dump.AFDIAN_USER_ID or not afdian_sponsors_dump.AFDIAN_TOKEN:
        print("[ERROR] AFDIAN_USER_ID and AFDIAN_TOKEN env vars are required.")
        raise SystemExit(1)
    repo_path = Path(os.environ.get("OAUTH_REPO_PATH", ".")).resolve()
    max_pages = int(os.environ.get("AFDIAN_INCREMENTAL_MAX_PAGES", str(DEFAULT_MAX_PAGES)))
    sync_incremental_orders(repo_path, fetch_order_page, max_pages=max_pages)


if __name__ == "__main__":
    main()
