"""빌드 스크립트의 실패·부가 경로: 로그 파일 충돌, 정리 기록, 같은 날 재실행의 옛 diff 삭제, 변환 실패, 로그 쓰기 실패.

커버리지 측정에서 이 코드들이 한 번도 실행되지 않는 것이 드러났다. 모두 실제로 일어나는 상황이다.
"""
import io
import os
import tempfile
import unittest
from datetime import datetime
from unittest import mock

import _path  # noqa: F401
import build_docs_snapshot as b
import fixtures as fx
from harness import TODAY, RunCase


class TeeAndLogFile(unittest.TestCase):
    def test_tee_writes_to_both_streams_and_passes_other_attributes_through(self):
        buf, stream = io.StringIO(), io.StringIO()
        tee = b.Tee(stream, buf)
        self.assertEqual(tee.write("hi"), 2)
        tee.flush()
        self.assertEqual((buf.getvalue(), stream.getvalue()), ("hi", "hi"))
        self.assertEqual(tee.getvalue(), "hi")  # encoding, isatty 같은 속성은 원래 스트림 것을 쓴다

    def test_logs_written_in_the_same_second_never_overwrite_each_other(self):
        start = datetime(2026, 1, 1, 12, 0, 0)
        with tempfile.TemporaryDirectory() as d:
            paths = [b.write_log(d, start, start, d, {"result": "성공"}, "") for _ in range(3)]
        self.assertEqual([os.path.basename(p) for p in paths],
                         ["2026-01-01_120000.log", "2026-01-01_120000_2.log", "2026-01-01_120000_3.log"])

    def test_cleanup_and_reviewed_fixes_are_reported(self):
        state = {"result": "성공", "name": "2026-01-01", "removed": ["2025-01-01"], "removed_history": ["2020-01-01", "2020-01-02"],
                 "links": {"counts": {"exact": 1, "strict": 1}, "missing_files": 0, "ko_heading_full": (1, 1), "ko_accordion_full": (0, 0),
                           "strict": [("en/a", "en/b", "x", "y")], "stale": [], "unreviewed": [], "ledger_changed": [], "hints": []}}
        start = datetime(2026, 1, 1, 12, 0, 0)
        with tempfile.TemporaryDirectory() as d:
            with open(b.write_log(d, start, start, d, state, ""), encoding="utf-8") as f:
                text = f.read()
        self.assertIn("- 지운 옛 구조의 날짜 폴더: 2025-01-01", text)
        self.assertIn("- 지운 오래된 이력: 2020-01-01, 2020-01-02", text)
        self.assertIn("- 새 보정 없음", text)  # 단어 일치 보정이 있어도 전부 검토된 것이면 이렇게 말한다


def page(slug, content, title=None):
    return fx.page(slug, title or slug, content)


class ChangeSummaryLines(unittest.TestCase):
    def test_removed_sections_are_listed(self):
        out, n_add, n_rem = b.summarize_change("# A\n\n## Gone\ntext here\n\n## Keep\nkeep text\n", "# A\n\n## Keep\nkeep text\n")
        self.assertIn("  - 삭제된 섹션: `Gone`", out)
        self.assertEqual((n_add, n_rem), (0, 2))

    def test_added_pages_list_their_sections(self):
        with tempfile.TemporaryDirectory() as d:
            prev = fx.write_snapshot(os.path.join(d, "prev.json.gz"), [page("a", "# A\n\nsame")], fetched_at="2026-01-01")
            new = fx.snapshot([page("a", "# A\n\nsame"), page("n", "# New\n\n## Sec One\ntext\n", "New")], fetched_at="2026-01-02")
            lines, counts = b.make_entry(prev, new)
        self.assertEqual(counts, (1, 0, 0))
        self.assertTrue(any(l.startswith("  - 섹션:") and "`Sec One`" in l for l in lines), lines)


class StaleDiffFile(unittest.TestCase):
    """같은 날 다시 실행했더니 이번에는 바뀐 것이 없다면, 앞서 만든 diff 파일이 남아 거짓 정보를 주면 안 된다."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = d.name
        self.diff = os.path.join(d.name, "history", "2026-01-02.diff")
        os.makedirs(os.path.dirname(self.diff))
        with open(self.diff, "w", encoding="utf-8") as f:
            f.write("old diff from an earlier run today")
        self.snap = fx.snapshot([page("en/a", "# A\n\nsame")], fetched_at="2026-01-02")
        self.cur = fx.write_snapshot(os.path.join(d.name, "docs.json"), self.snap["pages"], fetched_at="2026-01-02")

    def test_removed_when_there_is_no_previous_snapshot(self):
        self.assertIsNone(b.save_history(self.dir, "2026-01-02", self.cur, None, self.snap))
        self.assertFalse(os.path.exists(self.diff))

    def test_removed_when_nothing_changed(self):
        prev = fx.write_snapshot(os.path.join(self.dir, "history", "2026-01-01.json.gz"), self.snap["pages"], fetched_at="2026-01-01")
        self.assertIsNone(b.save_history(self.dir, "2026-01-02", self.cur, prev, self.snap))
        self.assertFalse(os.path.exists(self.diff))


class SwapFirstBuild(unittest.TestCase):
    def test_a_failure_with_no_old_site_leaves_no_site_behind(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(OSError):
                b.swap_site(d, os.path.join(d, "does-not-exist"))
            self.assertFalse(os.path.exists(os.path.join(d, "site")))


class RunEdges(RunCase):
    def test_conversion_reporting_missing_files_aborts_and_keeps_the_old_site(self):
        before = self.make_old_site()
        with mock.patch.object(b.docs_json_to_html, "main", return_value=3):
            self.assertEqual(self.run_build(), 1)
        self.assertOldSiteUntouched(before)
        self.assertIn("HTML 에 없는 파일을 가리키는 링크가 있음", self.log())
        self.assertFalse(os.path.exists(os.path.join(self.out, "history", TODAY + ".json.gz")))

    def test_old_layout_folders_and_old_history_are_cleaned_up_and_reported(self):
        fx.write_snapshot(os.path.join(self.out, "2025-01-01", "docs.json"), [page("a", "# A\n\nx")])  # 이전 버전이 만든 날짜 폴더
        for day in ("2020-01-01", "2020-01-02"):
            fx.write_snapshot(os.path.join(self.out, "history", day + ".json.gz"), [page("a", "# A\n\nx")])
        with mock.patch.object(b, "KEEP_HISTORY", 1):
            self.assertEqual(self.run_build(), 0)
        self.assertFalse(os.path.exists(os.path.join(self.out, "2025-01-01")))
        self.assertEqual(b.history_dates(self.out), [TODAY])
        text = self.log()
        self.assertIn("- 지운 옛 구조의 날짜 폴더: 2025-01-01", text)
        self.assertIn("- 지운 오래된 이력: 2020-01-01, 2020-01-02", text)

    def test_a_log_that_cannot_be_written_does_not_change_the_result(self):
        with mock.patch.object(b, "write_log", side_effect=OSError("disk full")):
            self.assertEqual(self.run_build(), 0)  # 본 작업은 성공했으므로 종료 코드는 그대로
        self.assertTrue(os.path.isfile(os.path.join(self.out, "site", "en", "a.html")))


if __name__ == "__main__":
    unittest.main()
