"""변경 내역: 두 스냅샷의 차이 계산(docs_changes), 사이트의 변경 내역 페이지, 로그 문장. 네트워크 없음."""
import os
import tempfile
import unittest

import _path  # noqa: F401
import docsnap.history.changes as dc
import docs_verify
import fixtures as fx


def snap(pages, date):
    return fx.snapshot(pages, fetched_at=date)


def pg(slug, title, en, ko=None):
    """ko 본문의 첫 줄('# 제목')이 공식 한국어판 제목이 된다 (실제 문서처럼 제목과 H1 이 같다)."""
    return fx.page(slug, title, en, ko=(ko.splitlines()[0][2:], ko) if ko is not None else None)


OLD = snap([
    pg("keep", "Keep", "# Keep\n\nsame text here", "# 유지\n\n같은 글"),
    pg("edit", "Edit", "# Edit\n\n## Old part\nold line here\n\n## Same\nsame body", "# 편집\n\n## 옛 부분\n옛 줄입니다\n\n## 같음\n같은 본문"),
    pg("lag", "Lag", "# Lag\n\nversion one text", "# 지연\n\n버전 하나 글"),
    pg("gone", "Gone", "# Gone\n\nremoved page", "# 사라짐\n\n지워진 페이지"),
    pg("noko", "NoKo", "# NoKo\n\nenglish only v1"),
], "2026-01-01")

NEW = snap([
    pg("keep", "Keep", "# Keep\n\nsame text here", "# 유지\n\n같은 글"),
    pg("edit", "Edit", "# Edit\n\n## New part\nnew line here\n\n## Same\nsame body changed", "# 편집\n\n## 새 부분\n새 줄입니다\n\n## 같음\n같은 본문 수정"),
    pg("lag", "Lag", "# Lag\n\nversion two text", "# 지연\n\n버전 하나 글"),  # 영어만 바뀌고 한국어판은 그대로
    pg("noko", "NoKo", "# NoKo\n\nenglish only v2"),
    pg("fresh", "Fresh", "# Fresh\n\n## Sec A\ntext\n## Sec B\ntext", "# 새글\n\n## 절 가\n글\n## 절 나\n글"),
], "2026-01-08")


class ChangeData(unittest.TestCase):
    def test_no_previous_snapshot_gives_minimal_data(self):
        d = dc.change_data(None, NEW)
        self.assertEqual(d, {"date": "2026-01-08", "prev": None, "prev_label": None})

    def test_added_removed_changed_and_unchanged_are_counted(self):
        d = dc.change_data(OLD, NEW, "history/2026-01-01.json.gz")
        self.assertEqual([p["slug"] for p in d["added"]], ["fresh"])
        self.assertEqual([p["slug"] for p in d["removed"]], ["gone"])
        self.assertEqual(sorted(c["slug"] for c in d["changed"]), ["edit", "lag", "noko"])
        self.assertEqual((d["unchanged"], d["prev"]), (1, "2026-01-01"))
        fresh = d["added"][0]
        self.assertEqual(fresh["sections"], {"en": ["Sec A", "Sec B"], "ko": ["절 가", "절 나"]})  # 언어별 본문의 섹션
        self.assertEqual(fresh["title"], {"en": "Fresh", "ko": "새글"})

    def test_each_language_sees_the_change_of_its_own_text(self):
        d = {c["slug"]: c for c in dc.change_data(OLD, NEW)["changed"]}
        edit = d["edit"]
        self.assertEqual(edit["en"]["new_sections"], ["New part"])
        self.assertEqual(edit["ko"]["new_sections"], ["새 부분"])  # 번역이 아니라 공식 한국어 본문의 변경
        self.assertEqual(edit["ko"]["gone_sections"], ["옛 부분"])
        self.assertEqual(edit["en"]["edited_sections"], ["Same"])

    def test_english_only_change_is_not_a_korean_change_until_the_korean_page_catches_up(self):
        lag = {c["slug"]: c for c in dc.change_data(OLD, NEW)["changed"]}["lag"]
        self.assertIsNotNone(lag["en"])
        self.assertIsNone(lag["ko"])

    def test_pages_without_a_korean_version_show_the_english_change_in_korean_too(self):
        noko = {c["slug"]: c for c in dc.change_data(OLD, NEW)["changed"]}["noko"]
        self.assertIs(noko["ko"], noko["en"])  # 한국어 사이트가 영어 원문을 보여 주므로

    def test_page_changes_counts_lines_and_chars(self):
        d = dc.page_changes("# A\nold line here\nkeep line\n", "# A\nkeep line\nnew line here\nanother new\n")
        self.assertEqual((d["add_n"], d["rem_n"]), (2, 1))
        self.assertEqual(d["added"], ["new line here", "another new"])
        self.assertEqual(d["removed"], ["old line here"])
        self.assertEqual(d["delta"], len("# A\nkeep line\nnew line here\nanother new\n") - len("# A\nold line here\nkeep line\n"))
        many = dc.page_changes("", "\n".join(f"line number {i}" for i in range(10)), keep=2)
        self.assertEqual((many["add_n"], len(many["added"])), (10, 2))  # 대표 줄은 keep 개까지만, 개수는 전체


class ChangesMarkdown(unittest.TestCase):
    def test_no_previous_says_so_in_each_language(self):
        data = dc.change_data(None, NEW)
        self.assertIn("There is no earlier snapshot", dc.changes_markdown(data, "en"))
        self.assertIn("비교할 이전 스냅샷이 없어", dc.changes_markdown(data, "ko"))

    def test_english_page_lists_everything_with_links(self):
        md = dc.changes_markdown(dc.change_data(OLD, NEW, "history/2026-01-01.json.gz"), "en")
        self.assertTrue(md.startswith("# What changed\n"))
        self.assertIn("Compared with the snapshot of 2026-01-01 (history/2026-01-01.json.gz). This snapshot: 2026-01-08.", md)
        self.assertIn("1 added · 1 removed · 3 changed · 1 unchanged", md)
        self.assertIn("- [Fresh](https://code.claude.com/docs/en/fresh.md)", md)
        self.assertIn("  - Sections: `Sec A`, `Sec B`", md)
        self.assertIn("- **Gone** (`gone`)", md)  # 삭제된 페이지는 링크 없이
        self.assertIn("  - New sections: `New part`", md)
        self.assertIn("  - Added: `new line here`", md)
        self.assertIn("  - Removed: `old line here`", md)

    def test_korean_page_uses_korean_text_titles_and_omits_pages_whose_korean_did_not_change(self):
        md = dc.changes_markdown(dc.change_data(OLD, NEW), "ko")
        self.assertTrue(md.startswith("# 변경 내역\n"))
        self.assertIn("- [편집](https://code.claude.com/docs/ko/edit.md)", md)
        self.assertIn("  - 새 섹션: `새 부분`", md)
        self.assertIn("  - 추가: `새 줄입니다`", md)
        self.assertNotIn("/docs/ko/lag.md", md)  # 영어만 바뀐 페이지는 한국어 변경 내역에 없다
        self.assertIn("/docs/ko/noko.md", md)  # 한국어판이 없는 페이지는 영어 변경이 보인다
        self.assertIn("추가 1개 · 삭제 1개 · 변경 2개 · 변경 없음 1개", md)

    def test_nothing_changed(self):
        md = dc.changes_markdown(dc.change_data(NEW, NEW, "x"), "en")
        self.assertIn("0 added · 0 removed · 0 changed · 5 unchanged", md)
        self.assertIn("Nothing changed.", md)

    def test_code_spans_survive_backticks_and_long_lists_are_capped(self):
        self.assertEqual(dc.code("plain"), "`plain`")
        self.assertEqual(dc.code("use `x` here"), "`` use `x` here ``")
        self.assertEqual(dc.code("a\nb"), "`a b`")
        t = dc.TEXT["en"]
        text = dc._names([f"s{i}" for i in range(10)], t)
        self.assertTrue(text.endswith("and 2 more"))
        self.assertEqual(text.count("`s"), 8)
        self.assertIn(r"\[x\]", dc._link("[x]", "en", "p"))  # 제목의 대괄호가 링크를 깨지 않는다


class ChangesPageInSite(unittest.TestCase):
    def build(self, changes):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        out = os.path.join(d.name, "site")
        import docs_json_to_html as conv
        src = fx.write_snapshot(os.path.join(d.name, "docs.json"), NEW["pages"], fetched_at="2026-01-08")
        self.assertEqual(conv.main([src, out], changes=changes), 0)
        return out

    def test_pages_footer_links_and_independent_check(self):
        out = self.build(dc.change_data(OLD, NEW, "history/2026-01-01.json.gz"))
        en, ko = fx.read(os.path.join(out, "en", "changes.html")), fx.read(os.path.join(out, "ko", "changes.html"))
        self.assertIn('<h1 id="what-changed">', en)
        self.assertIn('<a href="fresh.html">Fresh</a>', en)  # 사이트 안 상대 링크로 바뀐다
        self.assertIn('<a href="fresh.html">새글</a>', ko)
        self.assertNotIn("Gone</a>", en)  # 삭제된 페이지는 링크가 아니라 글자
        self.assertIn("<strong>Gone</strong>", en)
        self.assertIn('<a href="../ko/changes.html">한국어</a>', en)  # 언어 전환 대상도 변경 내역
        for lang, page_name, label in (("en", "keep", "What changed"), ("ko", "keep", "변경 내역")):
            html = fx.read(os.path.join(out, lang, page_name + ".html"))
            self.assertIn(f'&middot; <a href="../{lang}/changes.html">{label}</a></footer>', html)  # 모든 페이지 하단
        self.assertNotIn("changes.html", fx.read(os.path.join(out, "en", "changes.html")).split("<footer>", 1)[1])  # 자기 자신은 링크하지 않음
        r = docs_verify.check(out)
        self.assertEqual(r["problems"], [])

    def test_changes_page_is_not_in_the_sidebar_or_search_index(self):
        out = self.build(dc.change_data(OLD, NEW))
        self.assertNotIn("changes", fx.read(os.path.join(out, "nav-data-en.js")))
        self.assertNotIn("changes.html", fx.read(os.path.join(out, "search-data-en.js")))

    def test_without_change_data_there_is_no_page_and_no_link(self):
        out = self.build(None)
        self.assertFalse(os.path.exists(os.path.join(out, "en", "changes.html")))
        self.assertNotIn("changes.html", fx.read(os.path.join(out, "en", "keep.html")))

    def test_first_build_shows_the_no_earlier_snapshot_page(self):
        out = self.build(dc.change_data(None, NEW))
        self.assertIn("There is no earlier snapshot", fx.read(os.path.join(out, "en", "changes.html")))


if __name__ == "__main__":
    unittest.main()
