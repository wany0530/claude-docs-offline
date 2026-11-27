"""빌드 스크립트 전체(build_docs_snapshot.main)를 가짜 수집기로 임시 폴더에서 끝까지 돌린다. 네트워크 없음.

변환기와 독립 검증기와 이력 저장은 진짜를 쓰고, 인터넷 연결 확인과 수집(docs_fetch_json)만 가짜로 바꾼다.
핵심 약속인 "어디서 실패하든 기존 사이트는 바이트 그대로"를 실패 경로마다 확인한다.
"""
import contextlib
import glob
import io
import os
import tempfile
import unittest
import urllib.error
from datetime import date
from unittest import mock

import _path  # noqa: F401
import build_docs_snapshot as b
import fixtures as fx

TODAY = date.today().isoformat()


def good_pages(extra_a=""):
    return [
        fx.page("a", "Alpha", "# Alpha\n\n## Setup\nSee [b](https://code.claude.com/docs/en/b.md#how-it-works)." + extra_a,
                ko=("알파", "# 알파\n\n## 설정\n[b](https://code.claude.com/docs/ko/b.md#how-it-works)")),
        fx.page("b", "Beta", "# Beta\n\n> [accordion] How it works\n>\n> text", ko=("베타", "# 베타\n\n> [accordion] 작동 방식\n>\n> 내용")),
    ]


class Run(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.out, self.logs = os.path.join(d.name, "output"), os.path.join(d.name, "logs")

    def make_old_site(self):
        os.makedirs(os.path.join(self.out, "site", "en"))
        with open(os.path.join(self.out, "site", "en", "old.html"), "w", encoding="utf-8") as f:
            f.write("OLD SITE")
        with open(os.path.join(self.out, "site", "marker.txt"), "w", encoding="utf-8") as f:
            f.write("old")
        return fx.tree(os.path.join(self.out, "site"))

    def run_build(self, pages=None, offline=False, **extra):
        def fake_fetch(argv):  # 수집기 대신: docs.json 을 쓰고 에셋 폴더를 만든다
            fx.write_snapshot(argv[0], pages if pages is not None else good_pages(), **extra)
            os.makedirs(argv[1], exist_ok=True)

        get = mock.Mock(side_effect=urllib.error.URLError("down")) if offline else mock.Mock(return_value="")
        with mock.patch.object(b.docs_fetch_json, "get", get), mock.patch.object(b.docs_fetch_json, "main", fake_fetch), \
                mock.patch.object(b.time, "sleep"), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return b.main([self.out, self.logs])

    def log(self):
        files = sorted(glob.glob(os.path.join(self.logs, "*", "*.log")))
        self.assertTrue(files, "로그 파일이 없음")
        with open(files[-1], encoding="utf-8") as f:
            return f.read()

    def assertOldSiteUntouched(self, before):
        self.assertEqual(fx.tree(os.path.join(self.out, "site")), before)
        self.assertFalse(os.path.exists(os.path.join(self.out, "site.old")))
        self.assertFalse(os.path.exists(os.path.join(self.out, ".building")), ".building 이 정리되지 않음")

    # ---------- 성공 ----------
    def test_success_replaces_site_saves_history_and_logs_the_link_check(self):
        before = self.make_old_site()
        self.assertEqual(self.run_build(), 0)
        site = os.path.join(self.out, "site")
        self.assertNotIn("en/old.html", fx.tree(site))  # 옛 사이트는 통째로 교체됨
        for rel in ("en/a.html", "ko/a.html", "en/b.html", "ko/b.html", "nav.js", "style.css"):
            self.assertTrue(os.path.isfile(os.path.join(site, rel)), rel)
        self.assertIn('href="b.html#how-it-works"', fx.read(os.path.join(site, "en", "a.html")))
        self.assertTrue(os.path.isfile(os.path.join(self.out, "history", TODAY + ".json.gz")))
        self.assertIn("site/index.html", fx.read(os.path.join(self.out, "index.html")))
        self.assertFalse(os.path.exists(os.path.join(self.out, ".building")))
        text = self.log()
        self.assertIn("- 결과: 성공", text)
        self.assertIn("## 링크 검증", text)
        self.assertIn("독립 검사(결과 HTML 을 다시 읽음)", text)
        self.assertIn("위반 0건", text)
        self.assertNotEqual(fx.tree(site), before)

    def test_second_build_compares_with_older_history_and_writes_the_diff(self):
        old = os.path.join(self.out, "history", "2000-01-01.json.gz")
        fx.write_snapshot(old, good_pages())
        self.assertEqual(self.run_build(pages=good_pages(extra_a="\n\nA brand new paragraph.")), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "history", TODAY + ".diff")))
        text = self.log()
        self.assertIn("내용 변경 1개", text)
        self.assertIn("A brand new paragraph", fx.read(os.path.join(self.out, "history", TODAY + ".diff")))

    # ---------- 실패: 기존 사이트는 그대로 ----------
    def test_offline_fails_without_touching_anything(self):
        before = self.make_old_site()
        self.assertEqual(self.run_build(offline=True), 1)
        self.assertOldSiteUntouched(before)
        self.assertFalse(os.path.exists(os.path.join(self.out, "history")))
        self.assertIn("인터넷 연결 안 됨", self.log())

    def test_english_fetch_failure_keeps_old_site_and_lists_the_error(self):
        before = self.make_old_site()
        bad = fx.page("c", "Gamma", "x")
        bad["content"], bad["error"] = None, "HTTP Error 500: boom"
        self.assertEqual(self.run_build(pages=good_pages() + [bad]), 1)
        self.assertOldSiteUntouched(before)
        text = self.log()
        self.assertIn("## 수집 실패", text)
        self.assertIn("https://code.claude.com/docs/en/c.md | HTTP Error 500: boom", text)
        self.assertIn("실패: 수집 실패 페이지 1개", text)

    def test_korean_fetch_failure_keeps_old_site(self):
        before = self.make_old_site()
        url = "https://code.claude.com/docs/en/a.md"
        self.assertEqual(self.run_build(ko_errors={url: "timed out"}), 1)
        self.assertOldSiteUntouched(before)
        text = self.log()
        self.assertIn("한국어판 수집 실패", text)
        self.assertIn("timed out", text)

    def test_independent_check_violation_aborts_before_the_swap(self):
        before = self.make_old_site()
        bad = {"counts": {"pages": 4}, "problems": [("en/a.html", "없는 앵커", "b.html#x")]}
        with mock.patch.object(b.docs_verify, "check", return_value=bad):
            self.assertEqual(self.run_build(), 1)
        self.assertOldSiteUntouched(before)
        self.assertFalse(os.path.exists(os.path.join(self.out, "history", TODAY + ".json.gz")))  # 이력도 저장하지 않는다
        text = self.log()
        self.assertIn("독립 검사에서 링크·id 위반 1건", text)

    def test_lock_on_the_site_folder_keeps_old_site_and_explains(self):
        before = self.make_old_site()
        with mock.patch.object(b.os, "replace", side_effect=PermissionError("locked")):
            self.assertEqual(self.run_build(), 1)
        self.assertOldSiteUntouched(before)
        text = self.log()
        self.assertIn("오류: PermissionError", text)
        self.assertIn("다른 프로그램", text)
        self.assertFalse(os.path.exists(os.path.join(self.out, "history", TODAY + ".json.gz")))


if __name__ == "__main__":
    unittest.main()
