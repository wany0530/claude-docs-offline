"""build_docs_snapshot.main 을 가짜 수집기로 임시 폴더에서 돌리는 테스트 공용 틀 (test_run, test_build_edges 가 쓴다)."""
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
import docsnap.build as b
import fixtures as fx

TODAY = date.today().isoformat()


def good_pages(extra_a=""):
    return [
        fx.page("a", "Alpha", "# Alpha\n\n## Setup\nSee [b](https://code.claude.com/docs/en/b.md#how-it-works)." + extra_a,
                ko=("알파", "# 알파\n\n## 설정\n[b](https://code.claude.com/docs/ko/b.md#how-it-works)")),
        fx.page("b", "Beta", "# Beta\n\n> [accordion] How it works\n>\n> text", ko=("베타", "# 베타\n\n> [accordion] 작동 방식\n>\n> 내용")),
    ]


class RunCase(unittest.TestCase):
    """output/ 과 logs/ 가 임시 폴더인 빌드 1회 실행 틀. 하위 클래스가 시나리오를 정한다."""

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
