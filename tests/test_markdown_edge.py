"""마크다운 변환기의 경계 사례: 수평선, 문단에 붙은 표, 원시 HTML 블록, 표 셀의 파이프, 느슨한 목록.

기대값은 현재 출력을 베껴 쓴 것이 아니라 CommonMark/GFM 규칙에 맞는지 따져서 정했다 (커버리지 측정에서 이 코드들이 실행되지
않는 것이 드러났고, 모두 실제 문서에서 쓰이는 문법이다).
"""
import unittest

import _path  # noqa: F401
from docs_markdown import Renderer

TARGETS = {"https://code.claude.com/docs/en/hooks": "en/hooks"}


def render(md):
    return Renderer("en/page", TARGETS, {}).render(md)


class Blocks(unittest.TestCase):
    def test_horizontal_rules(self):
        self.assertEqual(render("a\n\n---\n\nb\n\n***\n\nc"), "<p>a</p>\n<hr>\n<p>b</p>\n<hr>\n<p>c</p>")

    def test_a_table_may_follow_a_paragraph_without_a_blank_line(self):
        html = render("text before\n| a | b |\n|---|---|\n| 1 | 2 |")
        self.assertTrue(html.startswith("<p>text before</p>\n"))
        self.assertIn("<th>a</th><th>b</th>", html)
        self.assertIn("<td>1</td><td>2</td>", html)

    def test_paragraph_lines_are_joined_and_kept_together(self):
        self.assertEqual(render("line one\nline two\nline three"), "<p>line one\nline two\nline three</p>")

    def test_html_block_is_passed_through_with_docs_links_made_relative(self):
        html = render('<div class="x"><a href="https://code.claude.com/docs/en/hooks.md#h">link</a></div>\n\nafter')
        self.assertEqual(html, '<div class="x"><a href="hooks.html#h">link</a></div>\n<p>after</p>')

    def test_disallowed_html_is_shown_as_text_never_executed(self):
        html = render("<script>alert(1)</script>\n\nok")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_html_comments_are_dropped(self):
        html = render("<!-- hidden -->\n\nvisible")
        self.assertNotIn("hidden", html)
        self.assertIn("<p>visible</p>", html)


class InlineCode(unittest.TestCase):
    def test_one_space_is_stripped_from_both_ends_of_a_code_span(self):  # CommonMark: 백틱을 담으려고 두는 공백
        self.assertEqual(render("`` `tick` `` and ` a ` and `  b  `"), "<p><code>`tick`</code> and <code>a</code> and <code> b </code></p>")


class Tables(unittest.TestCase):
    def test_escaped_pipe_stays_inside_the_cell_even_in_code(self):
        html = render("| a \\| b | c |\n|---|---|\n| `x \\| y` | z |")
        self.assertIn("<th>a | b</th><th>c</th>", html)
        self.assertIn("<td><code>x | y</code></td><td>z</td>", html)

    def test_outer_pipes_are_optional(self):
        html = render("a | b\n--|--\n1 | 2")
        self.assertIn("<th>a</th><th>b</th>", html)
        self.assertIn("<td>1</td><td>2</td>", html)

    def test_column_alignment_from_the_separator_row(self):
        html = render("| l | c | r |\n|:--|:-:|--:|\n| 1 | 2 | 3 |")
        self.assertIn('<th style="text-align:left">l</th>', html)
        self.assertIn('<th style="text-align:center">c</th>', html)
        self.assertIn('<th style="text-align:right">r</th>', html)


class Lists(unittest.TestCase):
    def test_a_rule_ends_the_list(self):
        self.assertEqual(render("- one\n- two\n---\nafter"), "<ul><li>one</li><li>two</li></ul>\n<hr>\n<p>after</p>")

    def test_a_spaced_rule_also_ends_the_list(self):
        self.assertEqual(render("- one\n- - -\nafter"), "<ul><li>one</li></ul>\n<hr>\n<p>after</p>")  # '- - -' 은 항목처럼 보이지만 수평선

    def test_blank_line_between_items_makes_the_list_loose(self):
        self.assertEqual(render("- one\n\n- two"), "<ul><li><p>one</p></li><li><p>two</p></li></ul>")

    def test_an_item_can_have_a_second_paragraph(self):
        self.assertEqual(render("- first\n\n  second para\n- next"),
                         "<ul><li><p>first</p>\n<p>second para</p></li><li><p>next</p></li></ul>")

    def test_ordered_list_keeps_its_start_number(self):
        self.assertEqual(render("3. three\n4. four"), '<ol start="3"><li>three</li><li>four</li></ol>')

    def test_changing_list_kind_starts_a_new_list(self):
        self.assertEqual(render("- a\n1. b"), "<ul><li>a</li></ul>\n<ol><li>b</li></ol>")


if __name__ == "__main__":
    unittest.main()
