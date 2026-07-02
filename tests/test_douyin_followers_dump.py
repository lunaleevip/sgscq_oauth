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
    has_pagination_placeholder,
    merge_followers,
    next_cursor,
    page_items,
    should_continue,
    write_outputs,
)
from scripts import douyin_followers_dump as douyin_dump


class DouyinFollowersDumpTest(unittest.TestCase):
    def test_extract_follower_ids_accepts_common_douyin_identity_fields(self):
        item = {
            "uid": "uid-1",
            "unique_id": "unique-1",
            "short_id": "short-1",
            "sec_uid": "sec-1",
            "sec_user_id": "sec-user-1",
        }

        self.assertEqual(
            ["uid-1", "unique-1", "short-1", "sec-1", "sec-user-1"],
            extract_follower_ids(item),
        )

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
        try:
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


if __name__ == "__main__":
    unittest.main()
