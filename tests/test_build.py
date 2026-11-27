import gzip
import json
import os
import tempfile
import unittest
from unittest import mock

import _path  # noqa: F401
import build_docs_snapshot as b
import docs_diff


def page(slug, content, title=None, desc=""):
    return {"category": ["Docs"], "title": title or slug, "url": f"https://code.claude.com/docs/{slug}.md",
            "description": desc, "content": content}


def snap(date, *pages):
    return {"fetched_at": date, "pages": list(pages)}


def write_json(path, data, gz=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with (gzip.open(path, "wt", encoding="utf-8") if gz else open(path, "w", encoding="utf-8")) as f:
        json.dump(data, f)


class Sections(unittest.TestCase):
    def test_split_ignores_hash_in_code_fence(self):
        secs = b.split_sections("intro\n# A\ntext\n```\n# not heading\n```\n## B\nbody")
        self.assertEqual(list(secs), ["(intro)", "A", "B"])

    def test_duplicate_headings_numbered(self):
        self.assertEqual(list(b.split_sections("## X\na\n## X\nb")), ["(intro)", "X", "X (2)"])

    def test_summarize_change(self):
        out, n_add, n_rem = b.summarize_change("# A\nold line here\n", "# A\nnew line here\n## C\nfresh text\n")
        text = "\n".join(out)
        self.assertIn("새 섹션", text)
        self.assertIn("내용이 바뀐 섹션", text)
        self.assertEqual((n_add, n_rem), (3, 1))  # 추가: 'new line here', '## C', 'fresh text'


class MakeEntry(unittest.TestCase):
    def test_no_previous(self):
        lines, counts = b.make_entry(None, snap("2026-01-02"))
        self.assertIsNone(counts)

    def test_counts_added_removed_changed(self):
        with tempfile.TemporaryDirectory() as d:
            old = snap("2026-01-01", page("en/a", "same text"), page("en/b", "x\nold"), page("en/gone", "bye"))
            path = os.path.join(d, "2026-01-01.json.gz")
            write_json(path, old, gz=True)
            new = snap("2026-01-02", page("en/a", "same text"), page("en/b", "x\nnew"), page("en/fresh", "hello"))
            lines, counts = b.make_entry(path, new)
            self.assertEqual(counts, (1, 1, 1))
            self.assertIn("history/2026-01-01.json.gz", lines[0])


class History(unittest.TestCase):
    def test_find_previous_prefers_older_history(self):
        with tempfile.TemporaryDirectory() as d:
            for day in ("2026-01-01", "2026-01-05", "2026-01-09"):
                write_json(os.path.join(d, "history", day + ".json.gz"), snap(day), gz=True)
            # 같은 날 재실행: 오늘(01-09) 이력이 있어도 그 이전 것과 비교한다
            self.assertTrue(b.find_previous(d, "2026-01-09").endswith("2026-01-05.json.gz"))
            self.assertTrue(b.find_previous(d, "2026-01-10").endswith("2026-01-09.json.gz"))

    def test_find_previous_falls_back_to_snapshot_folder(self):
        with tempfile.TemporaryDirectory() as d:
            write_json(os.path.join(d, "2026-01-01", "docs.json"), snap("2026-01-01"))
            self.assertTrue(b.find_previous(d, "2026-01-02").replace("\\", "/").endswith("2026-01-01/docs.json"))
            self.assertTrue(b.find_previous(d, "2026-01-01").replace("\\", "/").endswith("2026-01-01/docs.json"))
            os.makedirs(os.path.join(d, "empty"))
            self.assertIsNone(b.find_previous(os.path.join(d, "empty"), "2026-01-01"))

    def test_save_history_and_diff(self):
        with tempfile.TemporaryDirectory() as d:
            old = snap("2026-01-01", page("en/a", "line1\nline2"))
            new = snap("2026-01-02", page("en/a", "line1\nLINE2"), page("en/n", "brand new"))
            prev = os.path.join(d, "history", "2026-01-01.json.gz")
            write_json(prev, old, gz=True)
            cur = os.path.join(d, "docs.json")
            write_json(cur, new)
            diff = b.save_history(d, "2026-01-02", cur, prev, new)
            self.assertTrue(os.path.isfile(os.path.join(d, "history", "2026-01-02.json.gz")))
            with open(diff, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("-line2", text)
            self.assertIn("+LINE2", text)
            self.assertIn("(새 페이지)", text)
            self.assertEqual(docs_diff.open_json(os.path.join(d, "history", "2026-01-02.json.gz"))["fetched_at"], "2026-01-02")

    def test_no_changes_writes_no_diff(self):
        with tempfile.TemporaryDirectory() as d:
            s = snap("2026-01-02", page("en/a", "same"))
            prev = os.path.join(d, "history", "2026-01-01.json.gz")
            write_json(prev, snap("2026-01-01", page("en/a", "same")), gz=True)
            cur = os.path.join(d, "docs.json")
            write_json(cur, s)
            self.assertIsNone(b.save_history(d, "2026-01-02", cur, prev, s))

    def test_prune_history_keeps_newest(self):
        with tempfile.TemporaryDirectory() as d:
            days = [f"2026-01-{i:02d}" for i in range(1, 6)]
            for day in days:
                write_json(os.path.join(d, "history", day + ".json.gz"), snap(day), gz=True)
                open(os.path.join(d, "history", day + ".diff"), "w").close()
            removed = b.prune_history(d, 3)
            self.assertEqual(removed, days[:2])
            self.assertEqual(b.history_dates(d), days[2:])
            self.assertFalse(os.path.exists(os.path.join(d, "history", days[0] + ".diff")))

    def test_remove_legacy_dirs_keeps_history_and_site(self):
        with tempfile.TemporaryDirectory() as d:
            for day in ("2026-01-01", "2026-01-02"):
                os.makedirs(os.path.join(d, day))
            for keep in ("history", "site"):  # 옛 날짜 폴더만 대상이다
                os.makedirs(os.path.join(d, keep))
            self.assertEqual(b.remove_legacy_dirs(d), ["2026-01-01", "2026-01-02"])
            self.assertTrue(os.path.isdir(os.path.join(d, "history")))
            self.assertTrue(os.path.isdir(os.path.join(d, "site")))
            self.assertFalse(os.path.exists(os.path.join(d, "2026-01-01")))


class LogSections(unittest.TestCase):
    def test_link_check_nav_warning_and_failures_are_logged(self):
        from datetime import datetime
        state = {"result": "성공", "name": "2026-01-01",
                 "links": {"counts": {"exact": 5, "key": 1, "strict": 1, "stale": 1}, "missing_files": 0,
                           "ko_heading_full": (3, 3), "ko_accordion_full": (1, 1),
                           "strict": [("en/a", "en/b", "delivery-mechanisms", "choose-a-delivery-mechanism")],
                           "stale": [("en/a", "en/b", "gone", ""), ("ko/a", "ko/b", "gone", "")],
                           "verify": {"counts": {"pages": 4, "links": 9, "anchors": 7, "stale": 2}, "problems": []},
                           "unreviewed": [("b#fresh", "fresh-long")], "ledger_changed": [("b#moved", "was", "now")],
                           "hints": [("en/a", "en/b", "gone-section", "gone-sections-new"), ("ko/a", "ko/b", "gone-section", "gone-sections-new")]},
                 "change_lines": ["추가 1개 · 삭제 0개 · 내용 변경 2개 · 변경 없음 3개", ""],
                 "nav_mismatch": ["상단 탭: 영어 8개, 한국어 7개라 짝짓지 못함"],
                 "failures": [("https://x/y.md", "HTTP Error 500 | boom")]}
        with tempfile.TemporaryDirectory() as d:
            path = b.write_log(d, datetime(2026, 1, 1), datetime(2026, 1, 1), d, state, "")
            with open(path, encoding="utf-8") as f:
                text = f.read()
        self.assertIn("## 링크 검증", text)
        self.assertIn("페이지 처음으로 연결 1", text)
        self.assertIn("영어판 고유 1건(링크한 페이지 기준 1곳)", text)
        self.assertIn("- en/b#gone (1곳)", text)
        self.assertNotIn("ko/b#gone", text)  # 목록은 영어판 기준 (한국어는 같은 링크)
        self.assertIn("→ #choose-a-delivery-mechanism", text)
        self.assertIn("독립 검사(결과 HTML 을 다시 읽음): 페이지 4개, 링크 9건(앵커 7건), 끊김 표시 2건 -> 위반 0건", text)
        self.assertIn("**검토 필요**", text)
        self.assertIn("새 보정: b#fresh → #fresh-long", text)
        self.assertIn("장부와 다름: b#moved 장부 #was / 이번 #now", text)
        self.assertIn("수동 확인 후보 1건", text)  # 영어판 기준 고유 건수 (한국어 중복은 세지 않음)
        self.assertIn("- en/b#gone-section ~ #gone-sections-new", text)
        order = [text.index(h) for h in ("## 수집 실패", "## 변경 요약", "## 링크 검증", "## 링크 상세", "## 이 로그 읽는 법")]
        self.assertEqual(order, sorted(order))  # 핵심인 변경 요약이 링크 검증보다 앞, 긴 목록은 뒤
        self.assertLess(len(text.split("## 링크 상세")[0].splitlines()), 40)  # 목록 없이도 앞부분이 한눈에 들어온다
        self.assertIn("## 경고: 한국어 메뉴 이름", text)
        self.assertIn("## 수집 실패", text)
        self.assertIn("| https://x/y.md | HTTP Error 500 / boom |", text)  # 표가 깨지지 않게 | 는 /


class SwapSite(unittest.TestCase):
    def make(self, root, name, text):
        os.makedirs(os.path.join(root, name))
        with open(os.path.join(root, name, "marker.txt"), "w") as f:
            f.write(text)
        return os.path.join(root, name)

    def read(self, path):
        with open(os.path.join(path, "marker.txt")) as f:
            return f.read()

    def test_replaces_existing_site(self):
        with tempfile.TemporaryDirectory() as d:
            self.make(d, "site", "old")
            new = self.make(d, "new", "new")
            final = b.swap_site(d, new)
            self.assertEqual(self.read(final), "new")
            self.assertFalse(os.path.exists(os.path.join(d, "site.old")))

    def test_first_build_without_site(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.read(b.swap_site(d, self.make(d, "new", "x"))), "x")

    def test_transient_lock_is_retried(self):
        # 브라우저·IDE 가 폴더를 잠깐 잡아 PermissionError 가 몇 번 나도 결국 교체된다
        with tempfile.TemporaryDirectory() as d:
            self.make(d, "site", "old")
            new = self.make(d, "new", "new")
            real, calls = os.replace, {"n": 0}

            def flaky(src, dst):
                calls["n"] += 1
                if calls["n"] <= 3:
                    raise PermissionError("locked")
                return real(src, dst)

            with mock.patch.object(b.os, "replace", flaky), mock.patch.object(b.time, "sleep") as sleep:
                final = b.swap_site(d, new)
            self.assertEqual(self.read(final), "new")
            self.assertEqual(sleep.call_count, 3)

    def test_persistent_lock_fails_with_a_helpful_message_and_keeps_old_site(self):
        with tempfile.TemporaryDirectory() as d:
            self.make(d, "site", "old")
            new = self.make(d, "new", "new")
            with mock.patch.object(b.os, "replace", side_effect=PermissionError("locked")), \
                    mock.patch.object(b.time, "sleep"):
                with self.assertRaises(PermissionError) as cm:
                    b.swap_site(d, new)
            self.assertIn("다른 프로그램", str(cm.exception))
            self.assertIn("기존 사이트는 그대로", str(cm.exception))
            self.assertEqual(self.read(os.path.join(d, "site")), "old")  # 첫 이름 변경에서 막혔으니 기존 사이트는 그대로

    def test_failure_restores_old_site(self):
        with tempfile.TemporaryDirectory() as d:
            self.make(d, "site", "old")
            with self.assertRaises(Exception):
                b.swap_site(d, os.path.join(d, "does-not-exist"))
            self.assertEqual(self.read(os.path.join(d, "site")), "old")


class DiffTool(unittest.TestCase):
    def test_korean_pages_compared_only_when_both_have_ko(self):
        def with_ko(slug, en, ko):
            p = page(slug, en)
            p["ko"] = {"title": "t", "description": "", "content": ko}
            return p
        old = snap("1", with_ko("en/a", "same", "옛 한글"))
        new = snap("2", with_ko("en/a", "same", "새 한글"))
        chunks = docs_diff.diff_snapshots(old, new)
        self.assertEqual(len(chunks), 1)
        self.assertIn("=== ko/a", chunks[0])
        # 옛 이력에 한국어 데이터가 없으면 한국어는 건너뛴다 (220개가 전부 '새 페이지'로 쏟아지지 않게)
        self.assertEqual(docs_diff.diff_snapshots(snap("1", page("en/a", "same")), new), [])
        self.assertEqual(len(docs_diff.diff_snapshots(old, new, "ko/a")), 1)
        self.assertEqual(docs_diff.diff_snapshots(old, new, "en/a"), [])

    def test_only_filter_and_removed_page(self):
        old = snap("1", page("en/a", "x"), page("en/b", "y"))
        new = snap("2", page("en/a", "x2"))
        self.assertEqual(len(docs_diff.diff_snapshots(old, new)), 2)
        only = docs_diff.diff_snapshots(old, new, "en/b")
        self.assertEqual(len(only), 1)
        self.assertIn("(삭제된 페이지)", only[0])


if __name__ == "__main__":
    unittest.main()
