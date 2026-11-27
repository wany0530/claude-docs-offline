"""수집기의 한국어판 처리와 메뉴 이름 짝짓기를 가짜 네트워크(_open 대체)로 검사한다. 실제 접속 없음."""
import io
import unittest
import urllib.error
from unittest import mock

import _path  # noqa: F401
import docs_fetch_json as f

EN = "https://code.claude.com/docs/en/"
KO = "https://code.claude.com/docs/ko/"


def entry(slug):
    return {"category": ["Docs"], "title": slug, "url": f"{EN}{slug}.md", "description": "", "content": "en"}


def fake_open(table):
    def _open(url):
        r = table[url]
        if isinstance(r, Exception):
            raise r
        return r
    return _open


class FetchKorean(unittest.TestCase):
    def run_fetch(self, pages, table):
        with mock.patch.object(f, "_open", fake_open(table)), mock.patch.object(f.time, "sleep"):
            f.fetch_korean(pages)

    def test_official_korean_markdown_is_stored_with_title_and_description(self):
        body = "> ## Documentation Index\n> x\n\n# 개요\n\n> 설명 문장입니다.\n\n본문"
        p = entry("overview")
        self.run_fetch([p], {KO + "overview.md": (KO + "overview.md", "text/markdown; charset=utf-8", body)})
        self.assertEqual(p["ko"]["title"], "개요")
        self.assertEqual(p["ko"]["description"], "설명 문장입니다.")
        self.assertEqual(p["ko"]["content"], body)  # 원문 그대로 (번역·가공 없음)
        self.assertNotIn("ko_error", p)

    def test_redirect_to_other_site_or_html_means_no_korean_version(self):
        a, b = entry("changelog"), entry("claude-tag")
        self.run_fetch([a, b], {
            KO + "changelog.md": ("https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md", "text/html", "<html>"),
            KO + "claude-tag.md": ("https://claude.com/docs/claude-tag/overview", "text/markdown", "# x"),
        })
        self.assertIsNone(a["ko"])
        self.assertIsNone(b["ko"])
        self.assertNotIn("ko_error", a)

    def test_404_means_no_korean_version_but_other_errors_are_recorded(self):
        a, b = entry("a"), entry("b")
        self.run_fetch([a, b], {
            KO + "a.md": urllib.error.HTTPError(KO + "a.md", 404, "Not Found", {}, io.BytesIO()),
            KO + "b.md": urllib.error.URLError("network down"),
        })
        self.assertIsNone(a["ko"])
        self.assertNotIn("ko_error", a)
        self.assertIsNone(b["ko"])
        self.assertIn("network down", b["ko_error"])


NAV_HTML = {
    "en": ('<a class="x nav-tabs-item group y">Getting started<svg></svg></a>'
           '<button class="nav-tabs-item group"><div>Plugins</div></button>'
           '<div class="sidebar-group-header z"><h5>Core concepts</h5></div>'
           '<li id="/en/overview" class="a" data-title="Overview"></li>'
           '<li data-title="Claude Code in the cloud" data-group-tag="" class="space-y-px">'),
    "ko": ('<a class="x nav-tabs-item group y">시작하기<div></div></a>'
           '<a class="nav-tabs-item group">플러그인</a>'
           '<div class="sidebar-group-header z"><h5>핵심 개념</h5></div>'
           '<li id="/ko/overview" class="a" data-title="개요"></li>'
           '<li data-title="클라우드의 Claude Code" data-group-tag="" class="space-y-px">'),
}


class NavNames(unittest.TestCase):
    def test_scan_nav_reads_tabs_buttons_groups_and_subgroups(self):
        with mock.patch.object(f, "_open", lambda url: (url, "text/html", NAV_HTML["en"])):
            labels, tabs, groups, subs = f.scan_nav(EN + "overview")
        self.assertEqual(tabs, ["Getting started", "Plugins"])  # 현재 탭은 button, 나머지는 a
        self.assertEqual(groups, ["Core concepts"])
        self.assertEqual(subs, ["Claude Code in the cloud"])
        self.assertEqual(labels["en/overview"], "Overview")

    def test_korean_names_pair_same_positions_without_translating(self):
        def scan(lang):
            with mock.patch.object(f, "_open", lambda url: (url, "text/html", NAV_HTML[lang])):
                return f.scan_nav(f"https://code.claude.com/docs/{lang}/overview")
        (en_l, en_t, en_g, en_s), (ko_l, ko_t, ko_g, ko_s) = scan("en"), scan("ko")
        names = f.korean_names(en_l, ko_l, en_t, ko_t, {"Getting started": en_g}, {"Getting started": ko_g},
                               {"Getting started": en_s}, {"Getting started": ko_s})
        self.assertEqual(names["Getting started"], "시작하기")
        self.assertEqual(names["Core concepts"], "핵심 개념")
        self.assertEqual(names["Claude Code in the cloud"], "클라우드의 Claude Code")
        self.assertEqual(names["Overview"], "개요")  # 같은 slug 의 메뉴 항목

    def test_unequal_lists_are_not_guessed(self):
        names = f.korean_names({}, {}, ["A", "B"], ["가"], {}, {}, {}, {})
        self.assertEqual(names, {})

    def test_skipped_pairings_are_reported_not_silent(self):
        problems = []
        f.korean_names({}, {}, ["A", "B"], ["가"], {"T": ["x", "y"]}, {"T": ["엑스"]}, {"T": ["s"]}, {"T": ["에스"]}, problems)
        self.assertEqual(len(problems), 2)
        self.assertIn("상단 탭", problems[0])
        self.assertIn("T 탭의 그룹", problems[1])
        ok = []
        f.korean_names({}, {}, ["A"], ["가"], {}, {}, {}, {}, ok)
        self.assertEqual(ok, [])

    def test_names_identical_in_both_languages_are_dropped(self):
        self.assertEqual(f.korean_names({}, {}, ["Agent SDK"], ["Agent SDK"], {}, {}, {}, {}), {})


if __name__ == "__main__":
    unittest.main()
