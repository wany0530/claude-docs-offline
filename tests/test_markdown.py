import collections
import unittest

import _path  # noqa: F401
from docs_anchors import resolve_anchor, resolve_anchors
from docs_markdown import Renderer, anchor_key, plain_text

TARGETS = {"https://code.claude.com/docs/en/hooks": "en/hooks", "https://code.claude.com/docs/en/a/b": "en/a/b"}


def render(md, slug="en/page", assets=None):
    r = Renderer(slug, TARGETS, assets or {})
    return r.render(md), r


class Blocks(unittest.TestCase):
    def test_callout(self):
        html, _ = render("> [!NOTE]\n> Careful here")
        self.assertIn('class="callout note"', html)
        self.assertIn("Careful here", html)

    def test_plain_blockquote(self):
        html, _ = render("> just a quote")
        self.assertIn("<blockquote>", html)

    def test_table_alignment(self):
        html, _ = render("| a | b |\n|:--|--:|\n| 1 | 2 |")
        self.assertIn('<th style="text-align:left">a</th>', html)
        self.assertIn('<td style="text-align:right">2</td>', html)

    def test_nested_list(self):
        html, _ = render("- one\n  - inner\n- two")
        self.assertEqual(html.count("<ul>"), 2)
        self.assertIn("inner", html)

    def test_ordered_list_start(self):
        html, _ = render("3. x\n4. y")
        self.assertIn('<ol start="3">', html)

    def test_loose_list_wraps_paragraphs(self):
        html, _ = render("- a\n\n- b")
        self.assertIn("<li><p>a</p></li>", html)

    def test_code_fence_language_and_escape(self):
        html, _ = render("```bash\necho '<x>' && ls\n```")
        self.assertIn('data-lang="bash"', html)
        self.assertIn("&lt;x&gt;", html)

    def test_headings_get_unique_ids(self):
        html, r = render("# Title\n\n## Same\n\n## Same")
        self.assertIn('id="same"', html)
        self.assertIn('id="same-1"', html)
        self.assertEqual([h[1] for h in r.heads], ["title", "same", "same-1"])

    def test_documentation_index_banner_removed(self):
        html, _ = render("> ## Documentation Index\n> Fetch the full index\n\n# Real")
        self.assertNotIn("Documentation Index", html)
        self.assertIn("Real", html)


class Inline(unittest.TestCase):
    def test_code_span_and_emphasis(self):
        html, _ = render("use `a < b` and **bold** and *em*")
        self.assertIn("<code>a &lt; b</code>", html)
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn("<em>em</em>", html)

    def test_internal_link_becomes_relative(self):
        html, r = render("[hooks](https://code.claude.com/docs/en/hooks#setup)", slug="en/a/b")
        self.assertIn('href="../hooks.html#setup"', html)
        self.assertEqual(r.links, [("en/hooks", "setup")])

    def test_external_link_untouched(self):
        html, _ = render("[x](https://example.com/a)")
        self.assertIn('href="https://example.com/a"', html)

    def test_escaped_angle_brackets_are_literal(self):
        html, _ = render(r"type \<name\> here")
        self.assertIn("&lt;name&gt;", html)

    def test_bare_url_autolinked_without_trailing_punctuation(self):
        html, _ = render("see https://example.com/x.")
        self.assertIn('<a href="https://example.com/x">https://example.com/x</a>.', html)

    def test_asset_url_maps_to_local_file(self):
        url = "https://mintcdn.com/x/pic.png"
        html, _ = render(f"![alt]({url})", slug="en/a/b", assets={url: "assets/pic.png"})
        self.assertIn('src="../../assets/pic.png"', html)

    def test_disallowed_tag_is_escaped(self):
        html, _ = render("<script>alert(1)</script> hi")
        self.assertNotIn("<script>", html)


class Components(unittest.TestCase):
    def test_consecutive_tabs_form_one_group_and_nest(self):
        html, _ = render("> [tab] A\n>\n> outer\n>\n> > [tab] in1\n> >\n> > x\n>\n> > [tab] in2\n> >\n> > y\n\n> [tab] B\n>\n> second")
        self.assertEqual(html.count('class="tabs"'), 2)
        self.assertEqual(html.count("tab-btn"), 4)  # 바깥 A,B + 안쪽 in1,in2
        self.assertEqual(html.count('class="tab-panel active"'), 2)  # 그룹마다 첫 탭만 열림
        self.assertIn("second", html)

    def test_tabs_follow_the_wai_aria_pattern(self):
        html, _ = render("> [tab] A\n>\n> a\n\n> [tab] B\n>\n> b")
        self.assertIn('role="tab" id="tab1-0-tab" aria-controls="tab1-0" aria-selected="true" tabindex="0"', html)
        self.assertIn('role="tab" id="tab1-1-tab" aria-controls="tab1-1" aria-selected="false" tabindex="-1"', html)  # 화살표 키로만 이동
        self.assertIn('role="tabpanel" id="tab1-1" aria-labelledby="tab1-1-tab" tabindex="0"', html)

    def test_separate_tab_groups_do_not_merge(self):
        html, _ = render("> [tab] A\n>\n> a\n\ntext between\n\n> [tab] B\n>\n> b")
        self.assertEqual(html.count('class="tabs"'), 2)

    def test_accordion(self):
        html, _ = render("> [accordion] Title **x**\n>\n> hidden text")
        self.assertIn('<details class="accordion" id="title-x"><summary>Title <strong>x</strong></summary>', html)

    def test_accordion_id_does_not_collide_with_heading(self):
        html, r = render("## Same name\n\n> [accordion] Same name\n>\n> body\n\n> [accordion] Same name\n>\n> body")
        self.assertIn('<h2 id="same-name">', html)
        self.assertIn('<details class="accordion" id="same-name-1">', html)
        self.assertIn('<details class="accordion" id="same-name-2">', html)
        self.assertEqual(r.acc_ids, ["same-name-1", "same-name-2"])

    def test_cards_grouped_with_links(self):
        md = ("> [card] [One](https://code.claude.com/docs/en/hooks.md)\n>\n> desc one\n\n"
              "> [card] [Two](https://example.com)\n>\n> desc two")
        html, r = render(md, slug="en/x")
        self.assertEqual(html.count('class="cards"'), 1)
        self.assertEqual(html.count('class="card"'), 2)
        self.assertIn('<a href="hooks.html">One</a>', html)

    def test_only_the_first_quote_after_a_title_is_the_lead(self):
        html, _ = render("# A\n\n> first description\n\n# B\n\n> quote under a second title")
        self.assertEqual(html.count('<div class="lead">'), 1)  # 설명문 처리는 페이지당 한 번뿐
        self.assertEqual(html.count("<blockquote>"), 1)

    def test_description_after_title_is_plain_lead_not_blockquote(self):
        html, _ = render("# T\n\n> the description\n\nbody\n\n> a real quote")
        self.assertIn('<div class="lead">', html)
        self.assertEqual(html.count("<blockquote>"), 1)  # 본문 중간의 인용문은 그대로


class HeadingHint(unittest.TestCase):
    def test_ids_borrowed_from_other_language(self):
        _, en = render("# Title\n\n## Setup\n\n### Deep")
        ko = Renderer("ko/page", TARGETS, {}, hint=en.head_ids)
        html = ko.render("# 제목\n\n## 설정\n\n### 깊은")
        self.assertIn('id="setup"', html)
        self.assertIn('id="deep"', html)
        self.assertEqual(ko.hint_pos, 3)

    def test_level_mismatch_falls_back_to_own_slug(self):
        ko = Renderer("ko/page", TARGETS, {}, hint=[(1, "title"), (2, "setup")])
        html = ko.render("# 제목\n\n### 다른 레벨\n\n## 설정")
        self.assertIn('id="title"', html)
        self.assertNotIn('id="setup"', html)  # 어긋난 뒤로는 기본 규칙 (한국어 slug)


    def test_accordion_ids_borrowed_from_other_language(self):
        _, en = render("> [accordion] How it works\n>\n> a\n\n> [accordion] Limits\n>\n> b")
        ko = Renderer("ko/page", TARGETS, {}, acc_hint=en.acc_ids)
        html = ko.render("> [accordion] 작동 방식\n>\n> 가\n\n> [accordion] 한계\n>\n> 나")
        self.assertIn('id="how-it-works"', html)
        self.assertIn('id="limits"', html)
        self.assertEqual(ko.acc_pos, 2)

    def test_deferred_anchor_links_leave_a_marker_until_resolved(self):
        r = Renderer("en/x", TARGETS, {}, defer_anchors=True)
        html = r.render("[a](https://code.claude.com/docs/en/hooks.md#setup) [b](https://code.claude.com/docs/en/hooks.md)")
        self.assertIn('href="\x010\x01"', html)  # 앵커 있는 링크만 표시
        self.assertIn('href="hooks.html"', html)
        self.assertEqual(r.links, [("en/hooks", "setup"), ("en/hooks", "")])


class Anchor(unittest.TestCase):
    def test_anchor_key(self):
        self.assertEqual(anchor_key("What%27s-New.v2"), "whatsnewv2")


class ResolveAnchor(unittest.TestCase):
    IDS = {"choose-a-delivery-mechanism", "whats-new", "setup", "setup-1", "frontmatter-fields", "frontmatter-rules"}

    def test_exact(self):
        self.assertEqual(resolve_anchor("setup", self.IDS), ("exact", "setup"))

    def test_key_match_fixes_punctuation_and_case(self):
        self.assertEqual(resolve_anchor("What%27s-New", self.IDS), ("key", "whats-new"))

    def test_strict_needs_all_words_and_exactly_one_candidate(self):
        self.assertEqual(resolve_anchor("delivery-mechanisms", self.IDS), ("strict", "choose-a-delivery-mechanism"))
        self.assertEqual(resolve_anchor("frontmatter", self.IDS)[0], "stale")  # 두 섹션에 걸쳐 모호하면 고르지 않는다

    def test_unknown_is_stale_not_guessed(self):
        self.assertEqual(resolve_anchor("precedence-within-the-managed-tier", self.IDS), ("stale", ""))
        self.assertEqual(resolve_anchor("anything", set()), ("stale", ""))


class ResolveAnchors(unittest.TestCase):
    def run_resolve(self, body, links):
        rep = {"counts": collections.Counter(), "key": set(), "strict": set(), "stale": set(), "hint": set()}
        ids = {"en/b": {"real-one", "shorter-than-asked"}, "en/a": {"here"}}
        out = resolve_anchors("en/a", body, links, ids, "STALE TITLE", rep)
        return out, rep

    def test_cross_page_links_are_confirmed_or_marked_stale(self):
        body = '<a href="\x010\x01">x</a> <a href="\x011\x01">y</a>'
        out, rep = self.run_resolve(body, [("en/b", "real-one"), ("en/b", "gone-section")])
        self.assertIn('<a href="b.html#real-one">x</a>', out)
        self.assertIn('<a href="b.html" class="stale-anchor" title="STALE TITLE">y</a>', out)  # 앵커를 빼고 페이지 처음으로
        self.assertEqual(rep["counts"]["exact"], 1)
        self.assertEqual(rep["counts"]["stale"], 1)

    def test_stale_link_gets_a_hint_but_is_not_relinked(self):
        body = '<a href="\x010\x01">x</a>'
        out, rep = self.run_resolve(body, [("en/b", "enable-shorter-than-asked")])
        self.assertIn('class="stale-anchor"', out)
        self.assertNotIn("#shorter", out)  # 힌트일 뿐 링크는 바꾸지 않는다
        self.assertEqual(rep["hint"], {("en/a", "en/b", "enable-shorter-than-asked", "shorter-than-asked")})

    def test_same_page_anchor_links_are_checked_too(self):
        body = '<a href="#here">ok</a> <a href="#nope">bad</a> <h2 id="here">h<a class="anchor" href="#here">#</a></h2>'
        out, rep = self.run_resolve(body, [])
        self.assertIn('<a href="#here">ok</a>', out)
        self.assertIn('<a href="#" class="stale-anchor" title="STALE TITLE">bad</a>', out)
        self.assertEqual(rep["counts"]["exact"], 1)  # 헤딩 옆 # 링크는 세지 않는다

    def test_code_samples_with_href_text_are_not_touched(self):
        body = '<pre><code>&lt;a href="#nope"&gt;x&lt;/a&gt;</code></pre>'
        out, _ = self.run_resolve(body, [])
        self.assertEqual(out, body)


class PlainText(unittest.TestCase):
    def test_strips_markup_keeps_words(self):
        t = plain_text("> ## Documentation Index\n> x\n\n# Title\n\nSee [the **hook** guide](https://a/b) and `CLAUDE_CODE_X`.\n\n```bash\nclaude --help\n```")
        self.assertEqual(t, "Title See the hook guide and CLAUDE_CODE_X . claude --help")


if __name__ == "__main__":
    unittest.main()
