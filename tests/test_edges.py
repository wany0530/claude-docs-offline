"""변환기·사이트 모듈·검증기·앵커·수집기의 실패/부가 경로. 커버리지 측정에서 한 번도 실행되지 않는 것이 드러난 실제 동작들."""
import collections
import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

import _path  # noqa: F401
import docs_anchors
import docs_fetch_json as f
import docs_json_to_html as conv
import docs_site
import docs_verify
import fixtures as fx


class SiteParts(unittest.TestCase):
    def test_old_urls_that_redirect_to_a_collected_page_link_to_the_new_page(self):
        pages = [fx.page("new-page", "New", "# n")]
        redirects = {"https://code.claude.com/docs/en/old-name": "https://code.claude.com/docs/en/new-page.md",
                     "https://code.claude.com/docs/en/ghost": "https://code.claude.com/docs/en/not-collected.md"}
        t = docs_site.make_targets(pages, redirects, "ko")
        self.assertEqual(t["https://code.claude.com/docs/en/old-name"], "ko/new-page")
        self.assertEqual(t["https://code.claude.com/docs/ko/old-name"], "ko/new-page")  # 한국어 주소 형태도
        self.assertNotIn("https://code.claude.com/docs/en/ghost", t)  # 수집되지 않은 곳으로 가는 별칭은 무시

    def test_only_english_page_urls_are_accepted(self):
        with self.assertRaises(ValueError):
            docs_site.rest_of({"url": "https://code.claude.com/docs/ko/x.md"})


class Converter(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = d.name

    def test_standalone_run_copies_assets_found_next_to_the_json(self):
        os.makedirs(os.path.join(self.dir, "assets"))
        with open(os.path.join(self.dir, "assets", "p.png"), "wb") as fh:
            fh.write(b"png")
        src = fx.write_snapshot(os.path.join(self.dir, "docs.json"), [fx.page("a", "A", "# A")], assets_dir="assets")
        out = os.path.join(self.dir, "site")
        self.assertEqual(conv.main([src, out]), 0)
        self.assertTrue(os.path.isfile(os.path.join(out, "assets", "p.png")))

    def test_explicit_assets_folder_argument_is_used(self):
        other = os.path.join(self.dir, "elsewhere")
        os.makedirs(other)
        with open(os.path.join(other, "q.png"), "wb") as fh:
            fh.write(b"png")
        src = fx.write_snapshot(os.path.join(self.dir, "docs.json"), [fx.page("a", "A", "# A")], assets_dir="assets")
        out = os.path.join(self.dir, "site")
        self.assertEqual(conv.main([src, out, other]), 0)
        self.assertTrue(os.path.isfile(os.path.join(out, "assets", "q.png")))

    def test_a_fix_that_differs_from_the_reviewed_ledger_is_called_out_on_the_console(self):
        pages = [fx.page("a", "A", "# A\n\n[x](https://code.claude.com/docs/en/b.md#delivery-mechanisms)"),
                 fx.page("b", "B", "# B\n\n## Choose a delivery mechanism\ntext")]
        ledger = os.path.join(self.dir, "ledger.json")
        with open(ledger, "w", encoding="utf-8") as fh:
            json.dump({"pairs": {"b#delivery-mechanisms": "some-other-id"}}, fh)
        src = fx.write_snapshot(os.path.join(self.dir, "docs.json"), pages)
        err = io.StringIO()
        with mock.patch.object(docs_anchors, "LEDGER_PATH", ledger), contextlib.redirect_stderr(err):
            self.assertEqual(conv.main([src, os.path.join(self.dir, "site")]), 0)
        self.assertIn("검토 필요(장부와 다름): b#delivery-mechanisms 장부 #some-other-id / 이번 #choose-a-delivery-mechanism", err.getvalue())
        self.assertEqual(docs_anchors.REPORT["ledger_changed"], [("b#delivery-mechanisms", "some-other-id", "choose-a-delivery-mechanism")])


class LocalAnchors(unittest.TestCase):
    def test_same_page_links_are_corrected_like_cross_page_links(self):
        rep = {"counts": collections.Counter(), "key": set(), "strict": set(), "stale": set(), "hint": set()}
        ids = {"en/p": {"choose-a", "choose-a-delivery-mechanism"}}
        body = '<a href="#Choose-A">k</a> <a href="#delivery-mechanisms">s</a>'
        out = docs_anchors.resolve_anchors("en/p", body, [], ids, "STALE", rep)
        self.assertEqual(out, '<a href="#choose-a">k</a> <a href="#choose-a-delivery-mechanism">s</a>')
        self.assertEqual((rep["counts"]["key"], rep["counts"]["strict"]), (1, 1))


def article(body):
    return f'<html><body><article><h1 id="t">T</h1>{body}</article></body></html>'


class Verifier(unittest.TestCase):
    def site(self, body):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        os.makedirs(os.path.join(d.name, "en"))
        with open(os.path.join(d.name, "en", "a.html"), "w", encoding="utf-8") as fh:
            fh.write(article(body))
        return d.name

    def test_a_stale_link_must_still_point_to_an_existing_page(self):
        r = docs_verify.check(self.site('<a href="gone.html" class="stale-anchor" title="t">x</a>'))
        self.assertEqual([(k, d) for _, k, d in r["problems"]], [("없는 파일", "gone.html")])

    def test_anchors_into_pages_outside_the_language_folders_are_not_checked(self):
        d = self.site('<a href="../index.html#top">home</a>')
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
            fh.write("<html><body>root page</body></html>")  # en/ ko/ 밖의 페이지는 파싱 대상이 아니다
        r = docs_verify.check(d)
        self.assertEqual(r["problems"], [])
        self.assertEqual(r["counts"]["anchors"], 1)

    def test_the_command_line_lists_at_most_fifty_problems_and_counts_the_rest(self):
        links = "".join(f'<a href="missing{i}.html">m</a>' for i in range(60))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = docs_verify.main([self.site(links)])
        self.assertEqual(code, 1)
        self.assertIn("위반 60건", out.getvalue())
        self.assertIn("... 외 10건", out.getvalue())
        self.assertEqual(out.getvalue().count("없는 파일:"), 50)


class FetchFailures(unittest.TestCase):
    def test_a_link_that_fails_for_any_other_reason_is_unresolved(self):
        pages = [{"category": ["D"], "title": "O", "url": "https://code.claude.com/docs/en/o.md", "description": "",
                  "content": "[x](https://code.claude.com/docs/en/elsewhere)"}]
        with mock.patch.object(f, "_open", side_effect=OSError("net")):
            redirects, unresolved, endpoints = f.resolve_links(pages)
        self.assertEqual((redirects, endpoints), ({}, {}))
        self.assertEqual(unresolved, {"https://code.claude.com/docs/en/elsewhere": "net"})

    def test_a_korean_page_that_fails_with_a_server_error_is_recorded_not_dropped(self):
        p = {"category": ["D"], "title": "O", "url": "https://code.claude.com/docs/en/o.md", "description": "", "content": "x"}
        err = urllib.error.HTTPError("u", 500, "Server Error", {}, io.BytesIO())
        with mock.patch.object(f, "_open", side_effect=err), mock.patch.object(f.time, "sleep"):
            f.fetch_korean([p])
        self.assertIsNone(p["ko"])
        self.assertIn("500", p["ko_error"])

    def test_main_reports_every_kind_of_failure_and_still_writes_the_snapshot(self):
        en = "https://code.claude.com/docs/en/"
        index = f"# Docs\n## G\n- [Overview]({en}overview.md)\n- [Broken]({en}broken.md)\n"

        def fake_open(url):
            if url == f.INDEX_URL:
                return url, "text/markdown", index
            if url.endswith(".md"):
                if "/docs/ko/" in url:
                    raise urllib.error.HTTPError(url, 500, "Server Error", {}, io.BytesIO())
                if url.endswith("broken.md"):
                    raise OSError("connection reset")
                return url, "text/markdown", "# Overview\n\n![p](https://mintcdn.com/x/pic.png)"
            return url, "text/html", ""  # 사이트 HTML: 메뉴 정보 없음

        with tempfile.TemporaryDirectory() as d:
            out, err = os.path.join(d, "docs.json"), io.StringIO()
            with mock.patch.object(f, "_open", fake_open), mock.patch.object(f.time, "sleep"), \
                    mock.patch.object(f, "get_bytes", side_effect=OSError("asset down")), contextlib.redirect_stderr(err):
                f.main([out, os.path.join(d, "assets")])
            with open(out, encoding="utf-8") as fh:
                snap = json.load(fh)
        overview, broken = snap["pages"]
        self.assertIsNone(broken["content"])
        self.assertIn("connection reset", broken["error"])
        self.assertEqual(len(snap["ko_errors"]), 2)  # 두 페이지 모두 한국어판 서버 오류
        self.assertEqual(list(snap["asset_errors"].values()), ["asset down"])
        self.assertEqual(overview["assets"], {})  # 받지 못한 에셋은 매핑에 넣지 않는다
        text = err.getvalue()
        self.assertIn("  실패: " + en + "broken.md", text)
        self.assertIn("  확인 필요:", text)
        self.assertIn("  한국어판 수집 실패:", text)


if __name__ == "__main__":
    unittest.main()
