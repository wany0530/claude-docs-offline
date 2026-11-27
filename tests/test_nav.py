"""사이드바 트리와 공식 사이트 순서 맞추기(docs_site.build_nav / rank_nav)를 작은 데이터로 확인한다."""
import unittest

import _path  # noqa: F401
import docs_site
from fixtures import page


def p(slug, *cat, ko=True):
    return page(slug, slug.upper(), f"# {slug}", category=("Tab", "Sec") + cat, ko=(slug, f"# {slug}") if ko else None)


def names(children):
    """트리 노드 목록 -> 읽기 쉬운 이름 목록 (그룹은 [이름, 자식...])."""
    return [[c["g"]] + names(c["c"]) if "g" in c else c["t"] for c in children]


def tree(pages, order=None, lang="en", ko_names=None):
    return names(docs_site.build_nav(pages, lang, ko_names or {}, order)[0]["c"])


class NavOrder(unittest.TestCase):
    def pages(self):
        # llms.txt 순서: 일반 페이지를 먼저, 하위 그룹은 뒤에 모인다
        return [p("a", "G"), p("b", "G"), p("c", "G"), p("d", "G"),
                p("s1x", "G", "S1"), p("s1y", "G", "S1"), p("s2x", "G", "S2")]

    def test_without_order_the_llms_order_is_kept(self):
        self.assertEqual(tree(self.pages()), [["G", "A", "B", "C", "D", ["S1", "S1X", "S1Y"], ["S2", "S2X"]]])
        self.assertEqual(tree(self.pages(), order={}), tree(self.pages()))
        self.assertEqual(tree(self.pages(), order={"Tab": []}), tree(self.pages()))

    def test_subgroups_are_interleaved_where_the_official_sidebar_puts_them(self):
        order = {"Tab": [["g", "G"], ["p", "en/a"], ["s", "S1"], ["p", "en/b"], ["s", "S2"], ["p", "en/c"], ["p", "en/d"]]}
        self.assertEqual(tree(self.pages(), order), [["G", "A", ["S1", "S1X", "S1Y"], "B", ["S2", "S2X"], "C", "D"]])

    def test_pages_missing_from_the_official_html_stay_right_after_their_predecessor(self):
        # c 는 공식 HTML 에 없다 (예: 숨겨진 페이지). llms.txt 에서 b 바로 뒤였으므로 b 바로 뒤에 둔다.
        order = {"Tab": [["g", "G"], ["p", "en/d"], ["p", "en/a"], ["p", "en/b"], ["s", "S2"], ["s", "S1"]]}
        self.assertEqual(tree(self.pages(), order), [["G", "D", "A", "B", "C", ["S2", "S2X"], ["S1", "S1X", "S1Y"]]])

    def test_top_level_groups_follow_the_official_order_too(self):
        pages = [p("a", "First"), p("b", "Second"), p("c", "Third")]
        order = {"Tab": [["g", "Third"], ["p", "en/c"], ["g", "First"], ["p", "en/a"], ["g", "Second"], ["p", "en/b"]]}
        self.assertEqual(tree(pages, order), [["Third", "C"], ["First", "A"], ["Second", "B"]])

    def test_order_that_matches_nothing_changes_nothing(self):
        order = {"Tab": [["g", "Nope"], ["p", "en/zzz"], ["s", "Nothing"]]}
        self.assertEqual(tree(self.pages(), order), tree(self.pages()))

    def test_a_subgroup_name_that_appears_twice_uses_the_one_after_its_parent_header(self):
        pages = [p("a1", "G1", "Troubleshooting"), p("b1", "G1"), p("a2", "G2", "Troubleshooting"), p("b2", "G2")]
        order = {"Tab": [["g", "G1"], ["p", "en/b1"], ["s", "Troubleshooting"],
                         ["g", "G2"], ["s", "Troubleshooting"], ["p", "en/b2"]]}
        self.assertEqual(tree(pages, order), [["G1", "B1", ["Troubleshooting", "A1"]], ["G2", ["Troubleshooting", "A2"], "B2"]])

    def test_each_tab_uses_only_its_own_order_and_korean_follows_the_english_order(self):
        pages = [p("a", "G"), p("b", "G"), p("c", "G", "S")]
        pages += [page("t2a", "T2A", "# t", category=("Other", "Sec", "H"), ko=None), page("t2b", "T2B", "# t", category=("Other", "Sec", "H"), ko=None)]
        order = {"Tab": [["g", "G"], ["s", "S"], ["p", "en/b"], ["p", "en/a"]], "Other": [["p", "en/t2b"], ["p", "en/t2a"]]}
        nav = docs_site.build_nav(pages, "ko", {"G": "지", "S": "에스"}, order)
        self.assertEqual(names(nav[0]["c"]), [["지", ["에스", "c"], "b", "a"]])  # 이름은 한국어, 순서는 영어 사이드바 기준
        self.assertEqual(names(nav[1]["c"]), [["H", "T2B", "T2A"]])

    def test_links_and_labels_are_not_touched_by_reordering(self):
        nav = docs_site.build_nav(self.pages(), "en", {}, {"Tab": [["g", "G"], ["p", "en/d"]]})
        leaves = {c["t"]: c["p"] for c in nav[0]["c"][0]["c"] if "p" in c}
        self.assertEqual(leaves["D"], "en/d.html")
        self.assertEqual(len(leaves), 4)


if __name__ == "__main__":
    unittest.main()
