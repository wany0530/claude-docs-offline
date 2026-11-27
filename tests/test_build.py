import gzip
import json
import os
import tempfile
import unittest

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

    def test_prune_snapshots(self):
        with tempfile.TemporaryDirectory() as d:
            for day in ("2026-01-01", "2026-01-02", "2026-01-03"):
                os.makedirs(os.path.join(d, day))
            os.makedirs(os.path.join(d, "history"))  # 스냅샷 정리 대상이 아니다
            self.assertEqual(b.prune(d, 1), ["2026-01-01", "2026-01-02"])
            self.assertTrue(os.path.isdir(os.path.join(d, "history")))


class DiffTool(unittest.TestCase):
    def test_only_filter_and_removed_page(self):
        old = snap("1", page("en/a", "x"), page("en/b", "y"))
        new = snap("2", page("en/a", "x2"))
        self.assertEqual(len(docs_diff.diff_snapshots(old, new)), 2)
        only = docs_diff.diff_snapshots(old, new, "en/b")
        self.assertEqual(len(only), 1)
        self.assertIn("(삭제된 페이지)", only[0])


if __name__ == "__main__":
    unittest.main()
