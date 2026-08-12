import json
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.douyin_followers_dump import (
    build_request_headers,
    build_page_url,
    clean_windows_curl_escapes,
    describe_http_error,
    extract_follower_ids,
    extract_profile_names,
    fetch_followers,
    has_pagination_placeholder,
    merge_followers,
    next_cursor,
    page_items,
    protected_snapshot_followers,
    read_existing_follower_object_count,
    should_continue,
    should_reject_incomplete_full_snapshot,
    write_outputs,
)
from scripts import douyin_followers_dump as douyin_dump


class DouyinFollowersDumpTest(unittest.TestCase):
    def test_extract_follower_ids_keeps_only_douyin_account_ids(self):
        item = {
            "uid": "uid-1",
            "unique_id": "unique-1",
            "short_id": "short-1",
            "sec_uid": "sec-1",
            "sec_user_id": "sec-user-1",
        }

        self.assertEqual(["unique-1"], extract_follower_ids(item))

    def test_extract_follower_ids_falls_back_to_short_id(self):
        item = {
            "uid": "uid-1",
            "short_id": "short-1",
            "sec_user_id": "sec-user-1",
        }

        self.assertEqual(["short-1"], extract_follower_ids(item))

    def test_extract_profile_names_maps_all_identifiers_to_nickname(self):
        item = {
            "uid": "uid-1",
            "sec_user_id": "sec-user-1",
            "user": {
                "unique_id": "unique-1",
                "nickname": "测试昵称",
            },
        }

        self.assertEqual({"unique-1": "测试昵称"}, extract_profile_names(item))

    def test_page_items_supports_common_response_shapes(self):
        self.assertEqual([{"uid": "1"}], page_items({"followers": [{"uid": "1"}]}))
        self.assertEqual([{"uid": "2"}], page_items({"data": {"followers": [{"uid": "2"}]}}))
        self.assertEqual([{"uid": "3"}], page_items({"data": {"list": [{"uid": "3"}]}}))
        self.assertEqual([{"uid": "4"}], page_items({"user_list": [{"uid": "4"}]}))

    def test_cursor_and_has_more_support_common_fields(self):
        self.assertEqual("99", next_cursor({"data": {"max_time": 99}}))
        self.assertEqual("100", next_cursor({"data": {"max_cursor": 100}}))
        self.assertEqual("101", next_cursor({"cursor": 101}))
        self.assertEqual(True, should_continue({"data": {"has_more": 1}}))
        self.assertEqual(False, should_continue({"has_more": 0}))

    def test_next_cursor_prefers_min_time_for_douyin_follower_pagination(self):
        self.assertEqual(
            "older-page-cursor",
            next_cursor({"max_time": "newest-item-time", "min_time": "older-page-cursor"}),
        )

    def test_build_page_url_removes_whitespace_from_secret_template(self):
        old_template = douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE
        try:
            douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE = (
                "https://www.douyin.com/aweme/v1/web/user/follower/list/?\n"
                "  device_platform=webapp&sec_user_id={target_id}  \n"
                "  &screen_width  =1707&browser_language=zh-  CN&max_time={cursor}&count={count}"
            )

            url = build_page_url("sec id", "0", 20)

            self.assertNotRegex(url, r"\s")
            self.assertIn("sec_user_id=sec%20id", url)
            self.assertIn("screen_width=1707", url)
            self.assertIn("browser_language=zh-CN", url)
        finally:
            douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE = old_template

    def test_clean_windows_curl_escapes_removes_powershell_carets(self):
        self.assertEqual(
            "a%3Db&c=%22x%22",
            clean_windows_curl_escapes("a^%^3Db^&c=^%^22x^%^22"),
        )

    def test_build_page_url_removes_windows_curl_escapes_from_template(self):
        old_template = douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE
        try:
            douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE = (
                "https://www.douyin.com/api?sec_user_id={target_id}^&msToken=abc^%^3D^&count={count}"
            )

            url = build_page_url("target", "0", 20)

            self.assertNotIn("^", url)
            self.assertIn("&msToken=abc%3D", url)
        finally:
            douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE = old_template

    def test_build_page_url_supports_offset_placeholder(self):
        old_template = douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE
        try:
            douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE = (
                "https://www.douyin.com/api?sec_user_id={target_id}&offset={offset}&max_time={cursor}&count={count}"
            )

            url = build_page_url("target", "123", 20, offset=40)

            self.assertIn("offset=40", url)
            self.assertIn("max_time=123", url)
        finally:
            douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE = old_template

    def test_build_page_url_prefers_signed_url_without_formatting(self):
        old_signed_url = douyin_dump.DOUYIN_SIGNED_URL
        old_use_f2 = getattr(douyin_dump, "USE_F2_ABOGUS", None)
        try:
            douyin_dump.USE_F2_ABOGUS = False
            douyin_dump.DOUYIN_SIGNED_URL = (
                "https://www.douyin.com/api?offset=13^&msToken=abc^%^3D^&a_bogus=signed"
            )

            url = build_page_url("target", "123", 20, offset=40)

            self.assertEqual(
                "https://www.douyin.com/api?offset=13&msToken=abc%3D&a_bogus=signed",
                url,
            )
        finally:
            douyin_dump.DOUYIN_SIGNED_URL = old_signed_url
            if old_use_f2 is None:
                del douyin_dump.USE_F2_ABOGUS
            else:
                douyin_dump.USE_F2_ABOGUS = old_use_f2

    def test_build_page_url_regenerates_f2_signature_for_each_cursor(self):
        old_signed_url = douyin_dump.DOUYIN_SIGNED_URL
        old_use_f2 = getattr(douyin_dump, "USE_F2_ABOGUS", None)
        old_source_type = getattr(douyin_dump, "DOUYIN_SOURCE_TYPE", None)
        old_abogus = getattr(douyin_dump, "F2ABogus", None)
        old_fingerprint = getattr(douyin_dump, "F2BrowserFingerprintGenerator", None)
        signed_queries = []
        test_case = self

        class FakeFingerprintGenerator:
            @staticmethod
            def generate_fingerprint(browser_name):
                test_case.assertEqual("Edge", browser_name)
                return "test-fingerprint"

        class FakeABogus:
            def __init__(self, fp, user_agent):
                test_case.assertEqual("test-fingerprint", fp)
                test_case.assertIn("Mozilla/5.0", user_agent)

            def generate_abogus(self, query, body):
                signed_queries.append(query)
                return ("ignored", f"signature-{len(signed_queries)}", "ignored", "ignored")

        try:
            douyin_dump.DOUYIN_SIGNED_URL = (
                "https://www.douyin.com/aweme/v1/web/user/follower/list/?"
                "sec_user_id=stale&offset=0&max_time=1590331351&count=20"
                "&source_type=1&msToken=keep&a_bogus=expired"
            )
            douyin_dump.USE_F2_ABOGUS = True
            douyin_dump.DOUYIN_SOURCE_TYPE = "4"
            douyin_dump.F2ABogus = FakeABogus
            douyin_dump.F2BrowserFingerprintGenerator = FakeFingerprintGenerator

            first = build_page_url("target", "0", 20, offset=0)
            second = build_page_url("target", "123", 20, offset=20)

            self.assertIn("sec_user_id=target", first)
            self.assertIn("max_time=0", first)
            self.assertIn("offset=0", first)
            self.assertIn("source_type=4", first)
            self.assertIn("a_bogus=signature-1", first)
            self.assertIn("max_time=123", second)
            self.assertIn("offset=20", second)
            self.assertIn("a_bogus=signature-2", second)
            self.assertNotIn("a_bogus=expired", first + second)
            self.assertEqual(2, len(signed_queries))
        finally:
            douyin_dump.DOUYIN_SIGNED_URL = old_signed_url
            for name, old_value in (
                ("USE_F2_ABOGUS", old_use_f2),
                ("DOUYIN_SOURCE_TYPE", old_source_type),
                ("F2ABogus", old_abogus),
                ("F2BrowserFingerprintGenerator", old_fingerprint),
            ):
                if old_value is None:
                    delattr(douyin_dump, name)
                else:
                    setattr(douyin_dump, name, old_value)

    def test_has_pagination_placeholder_detects_signed_single_page_template(self):
        self.assertFalse(has_pagination_placeholder("https://www.douyin.com/api?offset=13&max_time=123"))
        self.assertTrue(has_pagination_placeholder("https://www.douyin.com/api?offset={offset}&max_time=123"))
        self.assertTrue(has_pagination_placeholder("https://www.douyin.com/api?offset=0&max_time={cursor}"))

    def test_build_request_headers_uses_browser_referer_and_url_uifid(self):
        old_referer = douyin_dump.DOUYIN_REFERER_URL
        old_extra = douyin_dump.DOUYIN_EXTRA_HEADERS
        try:
            douyin_dump.DOUYIN_REFERER_URL = ""
            douyin_dump.DOUYIN_EXTRA_HEADERS = ""

            headers = build_request_headers(
                "https://www.douyin.com/aweme/v1/web/user/follower/list/?uifid=uifid-123",
                "cookie=abc^%^22",
            )

            self.assertEqual("https://www.douyin.com/jingxuan", headers["Referer"])
            self.assertEqual("uifid-123", headers["uifid"])
            self.assertEqual("cookie=abc%22", headers["Cookie"])
        finally:
            douyin_dump.DOUYIN_REFERER_URL = old_referer
            douyin_dump.DOUYIN_EXTRA_HEADERS = old_extra

    def test_build_request_headers_allows_json_extra_header_overrides(self):
        old_extra = douyin_dump.DOUYIN_EXTRA_HEADERS
        try:
            douyin_dump.DOUYIN_EXTRA_HEADERS = '{"Referer":"https://www.douyin.com/custom","x-test":"ok"}'

            headers = build_request_headers("https://www.douyin.com/api?uifid=from-url", "cookie=abc")

            self.assertEqual("https://www.douyin.com/custom", headers["Referer"])
            self.assertEqual("ok", headers["x-test"])
            self.assertEqual("from-url", headers["uifid"])
        finally:
            douyin_dump.DOUYIN_EXTRA_HEADERS = old_extra

    def test_describe_http_error_includes_response_preview(self):
        error = HTTPError(
            "https://www.douyin.com/api",
            400,
            "Bad Request",
            {"Content-Type": "application/json"},
            BytesIO(b'{"status_code":400,"status_msg":"bad signature"}'),
        )

        message = describe_http_error(error)
        error.close()

        self.assertIn("HTTP 400 Bad Request", message)
        self.assertIn("content-type=application/json", message)
        self.assertIn("bad signature", message)

    def test_incremental_merge_preserves_existing_followers(self):
        merged = merge_followers(["3", "2", "1"], ["5", "4", "3"])

        self.assertEqual(["5", "4", "3", "2", "1"], merged)

    def test_protected_snapshot_followers_never_drops_existing_ids(self):
        followers = protected_snapshot_followers(["old-3", "old-2", "old-1"], ["new-1", "old-2"])

        self.assertEqual(["new-1", "old-2", "old-3", "old-1"], followers)

    def test_incomplete_full_snapshot_is_rejected_before_merge(self):
        self.assertTrue(should_reject_incomplete_full_snapshot(existing_count=1000, recent_count=400))
        self.assertFalse(should_reject_incomplete_full_snapshot(existing_count=1000, recent_count=950))
        self.assertFalse(should_reject_incomplete_full_snapshot(existing_count=0, recent_count=0))

    def test_fetch_followers_retries_transient_page_errors(self):
        old_http_get_json = douyin_dump.http_get_json
        old_template = douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE
        old_sleep = douyin_dump.time.sleep
        try:
            douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE = (
                "https://www.douyin.com/api?sec_user_id={target_id}&max_time={cursor}&count={count}"
            )
            calls = []
            sleeps = []

            def fake_http_get_json(url, cookie):
                calls.append(url)
                if len(calls) < 3:
                    raise ValueError("temporary 429")
                return {"status_code": 0, "followers": [{"unique_id": "1"}], "has_more": 0}

            douyin_dump.http_get_json = fake_http_get_json
            douyin_dump.time.sleep = lambda seconds: sleeps.append(seconds)

            followers = fetch_followers(
                "cookie",
                "target",
                max_pages=1,
                http_retries=3,
                retry_sleep_sec=7,
            )

            self.assertEqual(["1"], followers)
            self.assertEqual(3, len(calls))
            self.assertEqual([7, 7], sleeps)
        finally:
            douyin_dump.http_get_json = old_http_get_json
            douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE = old_template
            douyin_dump.time.sleep = old_sleep

    def test_fetch_followers_retries_empty_pages_before_stopping(self):
        old_http_get_json = douyin_dump.http_get_json
        old_template = douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE
        old_sleep = douyin_dump.time.sleep
        try:
            douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE = (
                "https://www.douyin.com/api?sec_user_id={target_id}&max_time={cursor}&count={count}"
            )
            responses = [
                {"status_code": 0, "followers": [], "has_more": 1, "max_time": "a"},
                {"status_code": 0, "followers": [{"unique_id": "1"}], "has_more": 0, "max_time": "b"},
            ]
            sleeps = []

            def fake_http_get_json(url, cookie):
                return responses.pop(0)

            douyin_dump.http_get_json = fake_http_get_json
            douyin_dump.time.sleep = lambda seconds: sleeps.append(seconds)

            followers = fetch_followers(
                "cookie",
                "target",
                max_pages=1,
                empty_page_retries=1,
                retry_sleep_sec=9,
            )

            self.assertEqual(["1"], followers)
            self.assertEqual([9], sleeps)
        finally:
            douyin_dump.http_get_json = old_http_get_json
            douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE = old_template
            douyin_dump.time.sleep = old_sleep

    def test_fetch_followers_zero_max_pages_runs_until_no_more_pages(self):
        old_http_get_json = douyin_dump.http_get_json
        old_template = douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE
        try:
            douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE = (
                "https://www.douyin.com/api?sec_user_id={target_id}&max_time={cursor}&count={count}"
            )
            responses = [
                {"status_code": 0, "followers": [{"unique_id": "1"}], "max_time": "a", "has_more": 1},
                {"status_code": 0, "followers": [{"unique_id": "2"}], "max_time": "b", "has_more": 1},
                {"status_code": 0, "followers": [{"unique_id": "3"}], "max_time": "c", "has_more": 0},
            ]

            def fake_http_get_json(url, cookie):
                return responses.pop(0)

            douyin_dump.http_get_json = fake_http_get_json

            self.assertEqual(["1", "2", "3"], fetch_followers("cookie", "target", max_pages=0))
        finally:
            douyin_dump.http_get_json = old_http_get_json
            douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE = old_template

    def test_fetch_followers_f2_signed_url_uses_response_cursor_for_next_page(self):
        old_http_get_json = douyin_dump.http_get_json
        old_signed_url = douyin_dump.DOUYIN_SIGNED_URL
        old_use_f2 = getattr(douyin_dump, "USE_F2_ABOGUS", None)
        old_abogus = getattr(douyin_dump, "F2ABogus", None)
        old_fingerprint = getattr(douyin_dump, "F2BrowserFingerprintGenerator", None)
        old_sleep = douyin_dump.time.sleep
        calls = []
        test_case = self

        class FakeFingerprintGenerator:
            @staticmethod
            def generate_fingerprint(browser_name):
                return "test-fingerprint"

        class FakeABogus:
            def __init__(self, fp, user_agent):
                pass

            def generate_abogus(self, query, body):
                return ("ignored", "fresh-signature", "ignored", "ignored")

        try:
            douyin_dump.DOUYIN_SIGNED_URL = (
                "https://www.douyin.com/aweme/v1/web/user/follower/list/?"
                "sec_user_id=stale&offset=0&max_time=old&count=20&a_bogus=expired"
            )
            douyin_dump.USE_F2_ABOGUS = True
            douyin_dump.F2ABogus = FakeABogus
            douyin_dump.F2BrowserFingerprintGenerator = FakeFingerprintGenerator
            douyin_dump.time.sleep = lambda seconds: None

            def fake_http_get_json(url, cookie):
                calls.append(url)
                if len(calls) == 1:
                    return {
                        "status_code": 0,
                        "followers": [{"unique_id": "new-1"}],
                        "max_time": "cursor-2",
                        "has_more": 1,
                    }
                return {
                    "status_code": 0,
                    "followers": [{"unique_id": "new-2"}],
                    "max_time": "cursor-3",
                    "has_more": 0,
                }

            douyin_dump.http_get_json = fake_http_get_json

            followers = fetch_followers("cookie", "target", max_pages=0)

            self.assertEqual(["new-1", "new-2"], followers)
            self.assertEqual(2, len(calls))
            self.assertIn("max_time=0", calls[0])
            self.assertIn("max_time=cursor-2", calls[1])
            self.assertNotIn("a_bogus=expired", "".join(calls))
        finally:
            douyin_dump.http_get_json = old_http_get_json
            douyin_dump.DOUYIN_SIGNED_URL = old_signed_url
            douyin_dump.time.sleep = old_sleep
            for name, old_value in (
                ("USE_F2_ABOGUS", old_use_f2),
                ("F2ABogus", old_abogus),
                ("F2BrowserFingerprintGenerator", old_fingerprint),
            ):
                if old_value is None:
                    delattr(douyin_dump, name)
                else:
                    setattr(douyin_dump, name, old_value)

    def test_fetch_followers_incremental_stops_after_more_than_two_seen_pages(self):
        old_http_get_json = douyin_dump.http_get_json
        old_template = douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE
        try:
            douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE = (
                "https://www.douyin.com/api?sec_user_id={target_id}&max_time={cursor}&count={count}"
            )
            responses = [
                {"status_code": 0, "followers": [{"unique_id": "new-1"}], "max_time": "a", "has_more": 1},
                {"status_code": 0, "followers": [{"unique_id": "old-1"}], "max_time": "b", "has_more": 1},
                {"status_code": 0, "followers": [{"unique_id": "new-2"}, {"unique_id": "old-2"}], "max_time": "c", "has_more": 1},
                {"status_code": 0, "followers": [{"unique_id": "old-3"}], "max_time": "d", "has_more": 1},
                {"status_code": 0, "followers": [{"unique_id": "new-after-stop"}], "max_time": "e", "has_more": 0},
            ]

            def fake_http_get_json(url, cookie):
                return responses.pop(0)

            douyin_dump.http_get_json = fake_http_get_json

            followers = fetch_followers(
                "cookie",
                "target",
                max_pages=0,
                stop_at_seen={"old-1", "old-2", "old-3"},
                seen_stop_pages=2,
            )

            self.assertEqual(["new-1", "old-1", "new-2", "old-2", "old-3"], followers)
            self.assertEqual(1, len(responses))
        finally:
            douyin_dump.http_get_json = old_http_get_json
            douyin_dump.DOUYIN_FOLLOWERS_URL_TEMPLATE = old_template

    def test_read_existing_follower_object_count_prefers_snapshot_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "douyin"
            out_dir.mkdir(parents=True)
            (out_dir / "followers.json").write_text(
                json.dumps({"count": 150, "identifier_count": 515}),
                encoding="utf-8",
            )

            self.assertEqual(150, read_existing_follower_object_count(out_dir))

    def test_read_existing_follower_object_count_accepts_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "douyin"
            out_dir.mkdir(parents=True)
            (out_dir / "followers.json").write_text(
                json.dumps({"count": 150, "identifier_count": 515}),
                encoding="utf-8-sig",
            )

            self.assertEqual(150, read_existing_follower_object_count(out_dir))

    def test_write_outputs_keeps_json_sorted_and_compact_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "douyin"

            write_outputs(out_dir, "target-sec-id", ["5", "4", "3", "2", "1"], generated_at=123)

            payload = json.loads((out_dir / "followers.json").read_text(encoding="utf-8"))
            self.assertEqual("douyin", payload["platform"])
            self.assertEqual("target-sec-id", payload["target_id"])
            self.assertEqual(5, payload["count"])
            self.assertEqual(["1", "2", "3", "4", "5"], payload["followers"])
            compact = (out_dir / "followers.compact.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(["5", "4", "3", "2", "1"], compact)

    def test_write_outputs_reports_follower_object_count_separately_from_identifier_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "douyin"

            write_outputs(
                out_dir,
                "target-sec-id",
                ["uid-1", "unique-1", "sec-1", "uid-2", "sec-2"],
                generated_at=123,
                follower_object_count=2,
            )

            payload = json.loads((out_dir / "followers.json").read_text(encoding="utf-8"))
            self.assertEqual(5, payload["count"])
            self.assertEqual(2, payload["follower_object_count"])
            self.assertEqual(5, payload["identifier_count"])
            self.assertEqual(["sec-1", "sec-2", "uid-1", "uid-2", "unique-1"], payload["followers"])

    def test_write_outputs_can_include_profile_names_without_changing_compact(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "douyin"

            write_outputs(
                out_dir,
                "target-sec-id",
                ["uid-1", "sec-1"],
                generated_at=123,
                profiles={"uid-1": "测试昵称", "sec-1": "测试昵称"},
            )

            payload = json.loads((out_dir / "followers.json").read_text(encoding="utf-8"))
            self.assertEqual({"name": "测试昵称"}, payload["profiles"]["uid-1"])
            self.assertEqual({"name": "测试昵称"}, payload["profiles"]["sec-1"])
            compact = (out_dir / "followers.compact.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(["uid-1", "sec-1"], compact)


if __name__ == "__main__":
    unittest.main()
