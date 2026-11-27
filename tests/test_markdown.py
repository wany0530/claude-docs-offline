import unittest

import _path  # noqa: F401
from docs_json_to_html import Renderer, anchor_key, plain_text

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

    def test_separate_tab_groups_do_not_merge(self):
        html, _ = render("> [tab] A\n>\n> a\n\ntext between\n\n> [tab] B\n>\n> b")
        self.assertEqual(html.count('class="tabs"'), 2)

    def test_accordion(self):
        html, _ = render("> [accordion] Title **x**\n>\n> hidden text")
        self.assertIn('<details class="accordion"><summary>Title <strong>x</strong></summary>', html)

    def test_cards_grouped_with_links(self):
        md = ("> [card] [One](https://code.claude.com/docs/en/hooks.md)\n>\n> desc one\n\n"
              "> [card] [Two](https://example.com)\n>\n> desc two")
        html, r = render(md, slug="en/x")
        self.assertEqual(html.count('class="cards"'), 1)
        self.assertEqual(html.count('class="card"'), 2)
        self.assertIn('<a href="hooks.html">One</a>', html)

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


class Anchor(unittest.TestCase):
    def test_anchor_key(self):
        self.assertEqual(anchor_key("What%27s-New.v2"), "whatsnewv2")


class PlainText(unittest.TestCase):
    def test_strips_markup_keeps_words(self):
        t = plain_text("> ## Documentation Index\n> x\n\n# Title\n\nSee [the **hook** guide](https://a/b) and `CLAUDE_CODE_X`.\n\n```bash\nclaude --help\n```")
        self.assertEqual(t, "Title See the hook guide and CLAUDE_CODE_X . claude --help")


if __name__ == "__main__":
    unittest.main()
