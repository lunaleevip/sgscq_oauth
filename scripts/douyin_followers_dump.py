#!/usr/bin/env python3
"""Dump current Douyin followers identifiers to the sgscq OAuth static repo.

This uses a browser-session cookie. Douyin web APIs change more often than
Bilibili, so the endpoint URL is configurable through
DOUYIN_FOLLOWERS_URL_TEMPLATE. The default template targets the common web
followers endpoint and supports {target_id}, {cursor}, and {count}.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from urllib.error import HTTPError


DOUYIN_COOKIE = os.environ.get("DOUYIN_COOKIE", "").strip()
DOUYIN_TARGET_ID = os.environ.get("DOUYIN_TARGET_ID", "").strip()
DOUYIN_REFERER_ID = os.environ.get("DOUYIN_REFERER_ID", DOUYIN_TARGET_ID).strip()
DOUYIN_REFERER_URL = os.environ.get("DOUYIN_REFERER_URL", "").strip()
DOUYIN_FOLLOWERS_URL_TEMPLATE = os.environ.get("DOUYIN_FOLLOWERS_URL_TEMPLATE", "").strip()
DOUYIN_SIGNED_URL = os.environ.get("DOUYIN_SIGNED_URL", "").strip()
DOUYIN_EXTRA_HEADERS = os.environ.get("DOUYIN_EXTRA_HEADERS", "").strip()
DOUYIN_ID_FIELDS = [
    field.strip()
    for field in os.environ.get(
        "DOUYIN_ID_FIELDS",
        "uid,unique_id,short_id,sec_uid,sec_user_id",
    ).split(",")
    if field.strip()
]
DOUYIN_NAME_FIELDS = [
    field.strip()
    for field in os.environ.get(
        "DOUYIN_NAME_FIELDS",
        "nickname,nick_name,name,display_name",
    ).split(",")
    if field.strip()
]

_default_repo = Path(__file__).resolve().parent.parent
OAUTH_REPO_PATH = Path(os.environ.get("OAUTH_REPO_PATH", str(_default_repo)))

PAGE_SIZE = int(os.environ.get("DOUYIN_PAGE_SIZE", "20"))
PAGE_SLEEP_SEC = float(os.environ.get("DOUYIN_PAGE_SLEEP_SEC", "1.5"))
MAX_PAGES = int(os.environ.get("DOUYIN_MAX_PAGES", "1000"))
INCREMENTAL_MAX_PAGES = int(os.environ.get("DOUYIN_INCREMENTAL_MAX_PAGES", "5"))
SYNC_MODE = os.environ.get("DOUYIN_SYNC_MODE", "incremental").strip().lower()
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
DISCOVERED_PROFILE_NAMES: dict[str, str] = {}
DISCOVERED_OBJECT_KEYS: set[str] = set()


def default_url_template() -> str:
    return (
        "https://www.douyin.com/aweme/v1/web/user/follower/list/?"
        "device_platform=webapp&aid=6383&channel=channel_pc_web"
        "&sec_user_id={target_id}&count={count}&max_time={cursor}"
    )


def clean_windows_curl_escapes(value: str) -> str:
    return str(value).replace("^", "")


def clean_url_template(template: str) -> str:
    return "".join(clean_windows_curl_escapes(template).split())


def has_pagination_placeholder(template: str) -> bool:
    return "{cursor}" in template or "{offset}" in template


def build_page_url(target_id: str, cursor: str, count: int, offset: int = 0) -> str:
    if DOUYIN_SIGNED_URL:
        return clean_url_template(DOUYIN_SIGNED_URL)
    template = clean_url_template(DOUYIN_FOLLOWERS_URL_TEMPLATE or default_url_template())
    quoted_target = urllib.parse.quote(target_id, safe="")
    return template.format(
        target_id=quoted_target,
        cursor=urllib.parse.quote(str(cursor), safe=""),
        count=int(count),
        offset=int(offset),
    )


def extra_headers_from_env() -> dict[str, str]:
    if not DOUYIN_EXTRA_HEADERS:
        return {}
    try:
        payload = json.loads(clean_windows_curl_escapes(DOUYIN_EXTRA_HEADERS))
    except json.JSONDecodeError as exc:
        raise ValueError(f"DOUYIN_EXTRA_HEADERS must be a JSON object: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("DOUYIN_EXTRA_HEADERS must be a JSON object.")
    return {str(key): str(value) for key, value in payload.items() if str(key).strip()}


def build_request_headers(url: str, cookie: str) -> dict[str, str]:
    referer = DOUYIN_REFERER_URL or "https://www.douyin.com/jingxuan"
    headers = {
        "User-Agent": USER_AGENT,
        "Cookie": clean_windows_curl_escapes(cookie),
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
    }
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    uifid = first_non_empty({"uifid": query.get("uifid", [""])[0]}, "uifid")
    if uifid:
        headers["uifid"] = uifid
    headers.update(extra_headers_from_env())
    return headers


def response_preview(body: str) -> str:
    return body[:200].replace("\r", " ").replace("\n", " ")


def describe_http_error(exc: HTTPError) -> str:
    body = exc.read().decode("utf-8", errors="replace")
    return (
        f"HTTP {exc.code} {exc.reason} content-type={exc.headers.get('Content-Type', '')} "
        f"preview={response_preview(body)!r}"
    )


def http_get_json(url: str, cookie: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers=build_request_headers(url, cookie),
    )
    try:
        resp = urllib.request.urlopen(req, timeout=20)
    except HTTPError as exc:
        raise ValueError(describe_http_error(exc)) from exc
    with resp:
        body = resp.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"non-JSON response HTTP {resp.status} content-type={resp.headers.get('Content-Type', '')} "
                f"preview={response_preview(body)!r}"
            ) from exc


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def nested_get(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_list(data: dict[str, Any], paths: list[tuple[str, ...]]) -> list[dict[str, Any]]:
    for path in paths:
        value = nested_get(data, *path)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def page_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    return first_list(
        data,
        [
            ("followers",),
            ("user_list",),
            ("list",),
            ("data", "followers"),
            ("data", "user_list"),
            ("data", "list"),
        ],
    )


def first_non_empty(obj: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = obj.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "null":
            return text
    return ""


def extract_follower_ids(item: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    seen = set()
    for field in DOUYIN_ID_FIELDS:
        value = first_non_empty(item, field)
        if value and value not in seen:
            ids.append(value)
            seen.add(value)
    user = as_dict(item.get("user"))
    for field in DOUYIN_ID_FIELDS:
        value = first_non_empty(user, field)
        if value and value not in seen:
            ids.append(value)
            seen.add(value)
    return ids


def extract_profile_names(item: dict[str, Any]) -> dict[str, str]:
    user = as_dict(item.get("user"))
    name = first_non_empty(user, *DOUYIN_NAME_FIELDS) or first_non_empty(item, *DOUYIN_NAME_FIELDS)
    if not name:
        return {}
    return {identifier: name for identifier in extract_follower_ids(item)}


def extract_object_key(item: dict[str, Any]) -> str:
    ids = extract_follower_ids(item)
    return ids[0] if ids else ""


def first_cursor(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    payload = as_dict(data.get("data"))
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def next_cursor(data: dict[str, Any]) -> str:
    return first_cursor(data, "max_time", "max_cursor", "min_time", "cursor", "next_cursor")


def should_continue(data: dict[str, Any]) -> bool:
    value = data.get("has_more")
    if value is None:
        value = as_dict(data.get("data")).get("has_more")
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def fetch_followers(
    cookie: str,
    target_id: str,
    max_pages: int = MAX_PAGES,
    stop_at_seen: set[str] | None = None,
) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    cursor = os.environ.get("DOUYIN_INITIAL_CURSOR", "0")
    template = clean_url_template(DOUYIN_SIGNED_URL or DOUYIN_FOLLOWERS_URL_TEMPLATE or default_url_template())
    supports_pagination = has_pagination_placeholder(template)

    for page in range(1, max_pages + 1):
        url = build_page_url(target_id, cursor, PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
        try:
            data = http_get_json(url, cookie)
        except Exception as exc:
            raise SystemExit(f"[ERROR] page {page} HTTP failed: {exc}")

        code = data.get("status_code", data.get("code", 0))
        if str(code) not in {"0", "200"}:
            raise SystemExit(
                f"[ERROR] page {page} returned code={code} message={data.get('status_msg') or data.get('message')}"
            )

        items = page_items(data)
        if not items:
            print(f"[INFO] page {page}: no more followers, stop.")
            break

        new_count = 0
        for item in items:
            ids = extract_follower_ids(item)
            if stop_at_seen and any(value in stop_at_seen for value in ids):
                print(f"[INFO] page {page}: reached existing follower, stop incremental crawl.")
                return ordered
            object_key = extract_object_key(item)
            if object_key:
                DISCOVERED_OBJECT_KEYS.add(object_key)
            DISCOVERED_PROFILE_NAMES.update(extract_profile_names(item))
            for value in ids:
                if value in seen:
                    continue
                seen.add(value)
                ordered.append(value)
                new_count += 1

        print(f"[INFO] page {page}: +{new_count} identifiers, total seen {len(ordered)}")

        if not supports_pagination:
            print(f"[INFO] page {page}: signed URL has no pagination placeholder, stop.")
            break

        next_value = next_cursor(data)
        if not should_continue(data) or not next_value or next_value == cursor:
            print(f"[INFO] page {page}: no next page, stop.")
            break
        cursor = next_value
        time.sleep(PAGE_SLEEP_SEC)

    return ordered


def read_existing_followers(out_dir: Path) -> list[str]:
    compact_path = out_dir / "followers.compact.txt"
    if compact_path.exists():
        return [
            line.strip()
            for line in compact_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    json_path = out_dir / "followers.json"
    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8-sig"))
            followers = payload.get("followers") or []
            return [str(value).strip() for value in followers if str(value).strip()]
        except Exception as exc:
            print(f"[WARN] could not parse existing followers.json: {exc}")
    return []


def read_existing_profiles(out_dir: Path) -> dict[str, str]:
    json_path = out_dir / "followers.json"
    if not json_path.exists():
        return {}
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"[WARN] could not parse existing profile names: {exc}")
        return {}
    profiles = payload.get("profiles") or payload.get("profile_names") or {}
    if not isinstance(profiles, dict):
        return {}
    out: dict[str, str] = {}
    for identifier, value in profiles.items():
        name = ""
        if isinstance(value, dict):
            name = first_non_empty(value, *DOUYIN_NAME_FIELDS)
        else:
            name = str(value).strip()
        if str(identifier).strip() and name:
            out[str(identifier).strip()] = name
    return out


def read_existing_follower_object_count(out_dir: Path) -> int:
    json_path = out_dir / "followers.json"
    if not json_path.exists():
        return 0
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"[WARN] could not parse existing follower count: {exc}")
        return 0
    for key in ("follower_object_count", "count"):
        try:
            value = int(payload.get(key, 0))
            if value > 0:
                return value
        except Exception:
            continue
    return 0


def merge_followers(existing: list[str], recent: list[str]) -> list[str]:
    merged: list[str] = []
    seen = set()
    for value in recent + existing:
        text = str(value).strip()
        if not text or text in seen:
            continue
        merged.append(text)
        seen.add(text)
    return merged


def sort_key(value: str) -> tuple[int, Any]:
    text = str(value)
    if text.isdigit():
        return (0, int(text))
    return (1, text.lower())


def write_outputs(
    out_dir: Path,
    target_id: str,
    followers: list[str],
    generated_at: int | None = None,
    follower_object_count: int | None = None,
    profiles: dict[str, str] | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    sorted_ids = sorted(followers, key=sort_key)
    identifier_count = len(sorted_ids)
    object_count = int(follower_object_count) if follower_object_count is not None else identifier_count
    profile_payload = {
        identifier: {"name": name}
        for identifier, name in sorted((profiles or {}).items(), key=lambda x: sort_key(x[0]))
        if identifier in set(sorted_ids) and str(name).strip()
    }

    payload = {
        "version": 1,
        "platform": "douyin",
        "target_id": target_id,
        "generated_at": int(generated_at if generated_at is not None else time.time()),
        "count": identifier_count,
        "follower_object_count": object_count,
        "identifier_count": identifier_count,
        "followers": sorted_ids,
    }
    if profile_payload:
        payload["profiles"] = profile_payload

    json_path = out_dir / "followers.json"
    compact_path = out_dir / "followers.compact.txt"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    compact_path.write_text("\n".join(followers) + ("\n" if followers else ""), encoding="utf-8")

    print(f"[OK] wrote {json_path} ({json_path.stat().st_size} bytes, sorted)")
    print(f"[OK] wrote {compact_path} ({compact_path.stat().st_size} bytes, newest-first)")


def main() -> None:
    if not DOUYIN_COOKIE:
        print("[ERROR] DOUYIN_COOKIE env var is empty.")
        print("        Login douyin.com in your browser and copy the web Cookie.")
        sys.exit(1)
    if not DOUYIN_TARGET_ID:
        print("[ERROR] DOUYIN_TARGET_ID env var is empty.")
        print("        Use the target account sec_user_id, or override DOUYIN_FOLLOWERS_URL_TEMPLATE.")
        sys.exit(1)
    if not OAUTH_REPO_PATH.exists():
        print(f"[ERROR] OAUTH_REPO_PATH does not exist: {OAUTH_REPO_PATH}")
        sys.exit(1)

    out_dir = OAUTH_REPO_PATH / "douyin"
    print(f"[INFO] dumping Douyin followers of target={DOUYIN_TARGET_ID} -> {out_dir}")

    existing_followers = read_existing_followers(out_dir)
    existing_profiles = read_existing_profiles(out_dir)
    existing_object_count = read_existing_follower_object_count(out_dir)
    if SYNC_MODE == "full":
        followers = fetch_followers(DOUYIN_COOKIE, DOUYIN_TARGET_ID)
    else:
        followers = merge_followers(
            existing_followers,
            fetch_followers(
                DOUYIN_COOKIE,
                DOUYIN_TARGET_ID,
                max_pages=INCREMENTAL_MAX_PAGES,
                stop_at_seen=set(existing_followers),
            ),
        )
    profiles = existing_profiles if SYNC_MODE != "full" else {}
    profiles.update(DISCOVERED_PROFILE_NAMES)
    follower_object_count = (
        len(DISCOVERED_OBJECT_KEYS)
        if SYNC_MODE == "full" and DISCOVERED_OBJECT_KEYS
        else (existing_object_count + len(DISCOVERED_OBJECT_KEYS) if SYNC_MODE != "full" else None)
    )

    if not followers:
        print("[ERROR] zero Douyin follower identifiers crawled; refusing to overwrite snapshot.")
        sys.exit(1)

    existing_json = out_dir / "followers.json"
    if existing_json.exists():
        try:
            old = json.loads(existing_json.read_text(encoding="utf-8-sig"))
            old_count = int(old.get("count", 0))
            if SYNC_MODE == "full" and old_count >= 50 and len(followers) < old_count // 2:
                print(
                    f"[ERROR] new count {len(followers)} is < 50% of old count {old_count}. "
                    "Refusing to overwrite. If this is intentional, delete the existing file first."
                )
                sys.exit(1)
        except Exception as exc:
            print(f"[WARN] could not parse existing followers.json: {exc}")

    write_outputs(
        out_dir,
        DOUYIN_TARGET_ID,
        followers,
        follower_object_count=follower_object_count,
        profiles=profiles,
    )
    print(f"[DONE] {len(followers)} Douyin follower identifiers crawled.")


if __name__ == "__main__":
    main()
