"""수집기의 한국어판 처리와 메뉴 이름 짝짓기를 가짜 네트워크(_open 대체)로 검사한다. 실제 접속 없음."""
import contextlib
import io
import json
import os
import tempfile
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


LLMS = f"""# Claude Code Docs

## Getting started
### Core concepts
- [Overview]({EN}overview.md): What it is
- [Quickstart]({EN}quickstart.md)
#### Sub group
- [Overview]({EN}overview.md): duplicate of an earlier entry
- [Hooks]({EN}hooks.md): Hooks ref
## Reference
- [CLI]({EN}cli-reference.md)
- [Not docs](https://example.com/x.md)
"""


class ParseIndex(unittest.TestCase):
    def test_categories_follow_heading_levels_duplicates_and_foreign_links_are_dropped(self):
        with mock.patch.object(f, "get", lambda url: LLMS):
            entries = f.parse_index()
        self.assertEqual([e["url"] for e in entries],
                         [EN + "overview.md", EN + "quickstart.md", EN + "hooks.md", EN + "cli-reference.md"])
        by = {e["title"]: e for e in entries}
        self.assertEqual(by["Overview"]["category"], ["Getting started", "Core concepts"])
        self.assertEqual(by["Overview"]["description"], "What it is")  # 첫 등장 항목이 남는다
        self.assertEqual(by["Hooks"]["category"], ["Getting started", "Core concepts", "Sub group"])
        self.assertEqual(by["CLI"]["category"], ["Reference"])  # ## 가 나오면 하위 분류가 초기화됨
        self.assertEqual(by["Quickstart"]["description"], "")


class ResolveLinks(unittest.TestCase):
    def test_every_class_of_unlisted_link_is_sorted_out_and_new_pages_are_followed(self):
        body = (f"[a]({EN}old-name#x) [b]({EN}hidden) [c](https://code.claude.com/docs/mcp) [d]({EN}gone) "
                f"[e]({EN}offsite) [self]({EN}overview)")
        pages = [{"category": ["Docs"], "title": "Overview", "url": EN + "overview.md", "description": "", "content": body}]

        def http(url, code):
            return urllib.error.HTTPError(url, code, "x", {}, io.BytesIO())

        opened = {
            EN + "old-name": (EN + "overview", "text/html", ""),  # 옛 주소: 수집된 페이지로 넘어감
            EN + "hidden": (EN + "hidden", "text/html", ""),  # 목차에 없는 문서 페이지
            "https://code.claude.com/docs/mcp": http("m", 405),  # 문서가 아닌 엔드포인트
            EN + "gone": http("g", 404),
            EN + "gone2": http("g2", 404),  # 숨은 페이지 본문에서 새로 발견됨 (반복해서 따라간다)
            EN + "offsite": ("https://example.com/x", "text/html", ""),
        }

        def fake_open(url):
            r = opened[url]
            if isinstance(r, Exception):
                raise r
            return r

        hidden_md = "# Hidden page\n\n> About hidden\n\n[f](" + EN + "gone2)"
        with mock.patch.object(f, "_open", fake_open), mock.patch.object(f, "get", lambda url: hidden_md), \
                mock.patch.object(f.time, "sleep"):
            redirects, unresolved, endpoints = f.resolve_links(pages)
        self.assertEqual(redirects, {EN + "old-name": EN + "overview.md"})
        self.assertEqual(sorted(unresolved), [EN + "gone", EN + "gone2"])
        self.assertEqual(sorted(endpoints), sorted(["https://code.claude.com/docs/mcp", EN + "offsite"]))
        self.assertIn("docs 페이지가 아님: https://example.com/x", endpoints[EN + "offsite"])
        self.assertIn("405", endpoints["https://code.claude.com/docs/mcp"])
        hidden = pages[-1]
        self.assertEqual((hidden["category"], hidden["title"], hidden["description"], hidden["url"]),
                         (["_unlisted"], "Hidden page", "About hidden", EN + "hidden.md"))
        self.assertEqual(len(pages), 2)


class AddNavLabels(unittest.TestCase):
    def pages(self):
        def p(tab, slug, ko=None):
            return {"category": [tab, "S", "G"], "title": slug.upper(), "url": f"{EN}{slug}.md", "description": "",
                    "content": "x", "ko": ko}
        return [p("Tab1", "a", {"title": "가"}), p("Tab1", "b"), p("Tab2", "c"), p("_unlisted", "d")]

    def test_scans_each_tabs_first_page_once_then_only_pages_it_missed(self):
        pages, calls = self.pages(), []
        table = {
            EN + "a.md": ({"en/a": "Label A", "en/c": "Label C"}, ["Tab1", "Tab2"], ["G"], ["Sub"]),
            EN + "c.md": ({"en/c": "Label C"}, ["Tab1", "Tab2"], ["G2"], []),
            EN + "b.md": ({"en/b": "Label B"}, [], [], []),
        }

        def fake_scan(url):
            calls.append(url)
            return table[url]

        with mock.patch.object(f, "scan_nav", fake_scan):
            labels, tabs, groups, subs, fallback = f.add_nav_labels(pages)
        self.assertEqual(sorted(calls), [EN + "a.md", EN + "b.md", EN + "c.md"])  # 탭당 첫 페이지 + 이름을 못 찾은 b
        self.assertEqual([p["nav_label"] for p in pages[:3]], ["Label A", "Label B", "Label C"])
        self.assertEqual(pages[3]["nav_label"], "D")  # 목차에 없는 숨은 페이지는 제목을 쓴다
        self.assertEqual(fallback, ["D"])
        self.assertEqual(tabs, ["Tab1", "Tab2"])
        self.assertEqual((groups, subs), ({"Tab1": ["G"], "Tab2": ["G2"]}, {"Tab1": ["Sub"], "Tab2": []}))

    def test_korean_labels_go_to_the_ko_entry_and_pages_without_ko_are_skipped(self):
        pages, calls = self.pages(), []

        def fake_scan(url):
            calls.append(url)
            return ({"ko/a": "라벨 A", "ko/b": "x"}, ["탭1"], ["그룹"], []) if "/docs/ko/a" in url else ({}, [], [], [])

        with mock.patch.object(f, "scan_nav", fake_scan):
            f.add_nav_labels(pages, "ko")
        self.assertEqual(pages[0]["ko"]["nav_label"], "라벨 A")
        self.assertEqual(calls, [KO + "a.md"])  # ko 가 있는 페이지의 한국어 주소만 읽는다
        self.assertNotIn("nav_label", pages[1])  # 영어 항목은 건드리지 않는다


class DownloadAssets(unittest.TestCase):
    def test_hashed_names_shared_by_both_languages_and_failures_are_recorded(self):
        ok, bad = "https://mintcdn.com/x/pic one.png", "https://mintcdn.com/x/broken.mp4"
        amp = "https://mintcdn.com/x/a.png?w=1\\&h=2"
        pages = [{"content": f"![a]({ok.replace(' ', '')}) ![b]({bad}) ![c]({amp})",
                  "ko": {"content": f"![가]({bad}) ![나]({ok.replace(' ', '')})"}},
                 {"content": "no assets", "ko": None}]
        fetched = []

        def fake_bytes(url):
            fetched.append(url)
            if "broken" in url:
                raise OSError("boom")
            return b"data:" + url.encode()

        with tempfile.TemporaryDirectory() as d, mock.patch.object(f, "get_bytes", fake_bytes):
            n, errors = f.download_assets(pages, os.path.join(d, "assets"))
            saved = sorted(os.listdir(os.path.join(d, "assets")))
        self.assertEqual(n, 3)  # 고유 에셋 3개 (한국어 본문과 겹치는 것은 한 번만)
        self.assertEqual(list(errors), [bad])
        self.assertEqual(len(saved), 3)  # 실패한 것도 파일 이름은 잡히지만 내용은 없을 수 있음
        mapping = pages[0]["assets"]
        self.assertEqual(sorted(mapping), sorted([ok.replace(" ", ""), amp]))  # 실패한 에셋은 매핑에서 빠진다
        for url, rel in mapping.items():
            self.assertRegex(rel, r"^assets/[0-9a-f]{10}_[\w.\-]+$")
        self.assertIn("https://mintcdn.com/x/a.png?w=1&h=2", fetched)  # markdown 의 \& 는 실제 주소에선 &
        self.assertEqual(pages[1]["assets"], {})


NAV_EN = NAV_HTML["en"]
NAV_KO = NAV_HTML["ko"]


class FetchMain(unittest.TestCase):
    """수집기 전체(main)를 가짜 사이트로 끝까지 돌린다: 목차 읽기 -> 영어 -> 한국어 -> 메뉴 이름 -> 에셋 -> JSON."""

    def site(self, ko_nav=NAV_KO):
        pic = "https://mintcdn.com/x/pic.png"
        table = {
            f.INDEX_URL: LLMS_SMALL,
            EN + "overview.md": ("# Overview\n\n> d\n\n![pic](" + pic + ")"),
            EN + "quickstart.md": "# Quickstart\n\n> q",
            KO + "overview.md": "# 개요\n\n> 설명\n\n![그림](" + pic + ")",
            KO + "quickstart.md": urllib.error.HTTPError(KO + "quickstart.md", 404, "nf", {}, io.BytesIO()),
            EN + "overview": NAV_EN, EN + "quickstart": NAV_EN, KO + "overview": ko_nav,
        }

        def fake_open(url):
            r = table[url]
            if isinstance(r, Exception):
                raise r
            if url.endswith(".md") or url == f.INDEX_URL:
                return url, "text/markdown; charset=utf-8", r
            return url, "text/html", r
        return fake_open

    def run_main(self, fake_open):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        out = os.path.join(d.name, "docs.json")
        err = io.StringIO()
        with mock.patch.object(f, "_open", fake_open), mock.patch.object(f.time, "sleep"), \
                mock.patch.object(f, "get_bytes", lambda u: b"png"), contextlib.redirect_stderr(err):
            f.main([out, os.path.join(d.name, "site", "assets")])
        with open(out, encoding="utf-8") as fh:
            return json.load(fh), err.getvalue(), os.path.join(d.name, "site", "assets")

    def test_snapshot_has_english_korean_menu_names_and_shared_assets(self):
        snap, err, assets = self.run_main(self.site())
        self.assertEqual((snap["page_count"], snap["languages"]), (2, ["en", "ko"]))
        ov, qs = snap["pages"]
        self.assertEqual((ov["title"], ov["nav_label"]), ("Overview", "Overview"))
        self.assertEqual((ov["ko"]["title"], ov["ko"]["description"], ov["ko"]["nav_label"]), ("개요", "설명", "개요"))
        self.assertIsNone(qs["ko"])  # 한국어판 404 = 없음 (오류가 아님)
        self.assertEqual(snap["ko_errors"], {})
        self.assertEqual(snap["nav_names_ko"]["Core concepts"], "핵심 개념")
        self.assertEqual(snap["nav_names_ko"]["Getting started"], "시작하기")
        self.assertEqual(snap["nav_name_mismatch"], [])
        self.assertEqual(len(os.listdir(assets)), 1)  # 영어·한국어 본문이 같은 에셋을 가리키면 한 번만 저장
        self.assertEqual(ov["assets"], {"https://mintcdn.com/x/pic.png": next("assets/" + n for n in os.listdir(assets))})
        self.assertIn("저장 완료", err)
        self.assertIn("한국어판 없음: en/quickstart", err)

    def test_menu_that_cannot_be_paired_is_reported_not_guessed(self):
        ko_without_groups = NAV_KO.replace('<div class="sidebar-group-header z"><h5>핵심 개념</h5></div>', "")
        snap, err, _ = self.run_main(self.site(ko_nav=ko_without_groups))
        self.assertEqual(len(snap["nav_name_mismatch"]), 1)
        self.assertIn("그룹", snap["nav_name_mismatch"][0])
        self.assertNotIn("Core concepts", snap["nav_names_ko"])
        self.assertIn("경고: 한국어 메뉴 이름", err)


LLMS_SMALL = f"""# Docs
## Getting started
### Core concepts
- [Overview]({EN}overview.md): What it is
- [Quickstart]({EN}quickstart.md)
"""


if __name__ == "__main__":
    unittest.main()
