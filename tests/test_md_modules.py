"""Renderer 를 나눈 모듈들의 경계: 서로 몰래 의존하지 않고, 믹스인이 겹치지 않고, 문서화한 상태만 쓴다."""
import os
import subprocess
import sys
import unittest

import _path  # noqa: F401
import docsnap.markdown as docs_markdown
from docsnap.markdown.blocks import BlockMixin
from docsnap.markdown.components import ComponentMixin
from docsnap.markdown.ids import IdMixin
from docsnap.markdown.inline import InlineMixin
from docsnap.markdown.structures import StructureMixin

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MODULES = ("docsnap.markdown.syntax", "docsnap.markdown.inline", "docsnap.markdown.ids", "docsnap.markdown.components", "docsnap.markdown.structures", "docsnap.markdown.blocks", "docsnap.markdown")
MIXINS = (InlineMixin, IdMixin, ComponentMixin, StructureMixin, BlockMixin)

# 이 이름들은 모듈 분리 전부터 docs_markdown 에서 import 하던 공개 이름이다 (바뀌면 소비자가 깨진다)
PUBLIC_API = {"Renderer", "ALLOWED_TAGS", "BLOCK_HTML", "anchor_key", "attr", "esc", "esc_text", "heading_slug", "indent_of",
              "plain_text", "strip_banner"}

# 각 믹스인이 만드는 것이 아니라 Renderer.__init__ 이 소유하는 상태 (믹스인 머리말에 적은 계약)
STATE = {"slug", "targets", "assets", "ids", "used_ids", "links", "heads", "head_ids", "acc_ids", "hint", "hint_pos",
         "tab_n", "lead_done", "acc_hint", "acc_pos", "defer_anchors"}


class Boundaries(unittest.TestCase):
    def test_every_module_imports_alone_in_a_fresh_interpreter(self):
        for name in MODULES:  # 파사드를 먼저 불러야만 동작하는 숨은 의존이 없다
            r = subprocess.run([sys.executable, "-B", "-c", f"import {name}"], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{name}: {r.stderr[-400:]}")

    def test_facade_keeps_the_public_names(self):
        self.assertEqual(set(docs_markdown.__all__), PUBLIC_API)
        for name in PUBLIC_API:
            self.assertTrue(hasattr(docs_markdown, name), name)

    def test_renderer_combines_all_mixins_and_methods_never_collide(self):
        for m in MIXINS:
            self.assertTrue(issubclass(docs_markdown.Renderer, m), m.__name__)
        seen = {}
        for m in MIXINS:
            for name in vars(m):
                if name.startswith("__"):
                    continue
                self.assertNotIn(name, seen, f"{name} 가 {seen.get(name)} 와 {m.__name__} 에 중복")
                seen[name] = m.__name__
        self.assertIn("quote_block", seen)  # blocks() 에서 추출한 인용 처리

    def test_a_fresh_renderer_owns_exactly_the_documented_state(self):
        r = docs_markdown.Renderer("en/x", {}, {})
        self.assertEqual(set(vars(r)), STATE)

    def test_mixins_hold_no_state_of_their_own(self):
        for m in MIXINS:
            data = [k for k, v in vars(m).items() if not k.startswith("__") and not callable(v) and not isinstance(v, staticmethod)]
            self.assertEqual(data, [], f"{m.__name__} 에 클래스 변수 {data}")


class IdMixinAlone(unittest.TestCase):
    """IdMixin 은 Renderer 없이 문서화한 상태만 있으면 동작한다."""

    def make(self, hint=None, acc_hint=None):
        class T(IdMixin):
            pass
        t = T()
        t.ids, t.used_ids, t.head_ids, t.acc_ids = {}, set(), [], []
        t.hint, t.hint_pos, t.acc_hint, t.acc_pos = hint, 0, acc_hint, 0
        return t

    def test_headings_and_accordions_share_one_numbering(self):
        t = self.make()
        self.assertEqual(t.heading_id("Same name", 2), "same-name")
        self.assertEqual(t.accordion_id("Same name"), "same-name-1")
        self.assertEqual(t.heading_id("Same name", 2), "same-name-2")
        self.assertEqual(t.heading_id("???", 2), "section")  # 글자가 없으면 기본 이름
        self.assertEqual(t.head_ids, [(2, "same-name"), (2, "same-name-2"), (2, "section")])

    def test_ids_are_borrowed_in_order_and_fall_back_on_a_level_mismatch(self):
        t = self.make(hint=[(1, "title"), (2, "setup")], acc_hint=["acc-one"])
        self.assertEqual(t.heading_id("제목", 1), "title")
        self.assertEqual(t.heading_id("다른 레벨", 3), "다른-레벨")  # 레벨이 어긋나면 자기 제목의 기본 규칙으로
        self.assertEqual(t.heading_id("설정", 2), "설정")  # 이후로는 계속 기본 규칙 (영어 id 의 "setup" 은 더 쓰지 않는다)
        self.assertIsNone(t.hint)
        self.assertEqual(t.accordion_id("아무거나"), "acc-one")
        self.assertEqual(t.accordion_id("둘째"), "둘째")  # 빌려 올 id 가 떨어지면 기본 규칙


class InlineMixinAlone(unittest.TestCase):
    def make(self, targets=None, assets=None, defer=False):
        class T(InlineMixin):
            pass
        t = T()
        t.slug, t.targets, t.assets, t.links, t.defer_anchors = "en/dir/page", targets or {}, assets or {}, [], defer
        return t

    def test_docs_links_become_relative_and_are_recorded(self):
        t = self.make({"https://code.claude.com/docs/en/other": "en/other", "https://code.claude.com/docs/en/dir/sub": "en/dir/sub"})
        self.assertEqual(t.fix_url("https://code.claude.com/docs/en/other.md#frag"), "../other.html#frag")
        self.assertEqual(t.fix_url("https://code.claude.com/docs/en/dir/sub.md"), "sub.html")
        self.assertEqual(t.fix_url("https://example.com/x"), "https://example.com/x")  # 그 밖의 주소는 그대로
        self.assertEqual(t.links, [("en/other", "frag"), ("en/dir/sub", "")])

    def test_deferred_anchor_leaves_a_numbered_marker(self):
        t = self.make({"https://code.claude.com/docs/en/other": "en/other"}, defer=True)
        self.assertEqual(t.fix_url("https://code.claude.com/docs/en/other.md#a"), "\x010\x01")
        self.assertEqual(t.fix_url("https://code.claude.com/docs/en/other.md"), "../other.html")  # 앵커 없는 링크는 바로

    def test_assets_use_the_site_relative_path(self):
        t = self.make(assets={"https://mintcdn.com/x/p.png": "assets/p.png"})
        self.assertEqual(t.fix_url("https://mintcdn.com/x/p.png"), "../../assets/p.png")

    def test_inline_markup(self):
        t = self.make()
        self.assertEqual(t.inline("**bold** and `a<b` and *it*"), "<strong>bold</strong> and <code>a&lt;b</code> and <em>it</em>")
        self.assertEqual(t.inline("[x](https://example.com)"), '<a href="https://example.com">x</a>')
        self.assertEqual(t.inline("a < b & c"), "a &lt; b &amp; c")


if __name__ == "__main__":
    unittest.main()


class TableFocusTest(unittest.TestCase):
    def test_table_wrapper_is_keyboard_focusable(self):
        # 좁은 화면에서 표가 가로로 스크롤되면 키보드로 닿을 수 있어야 한다(axe: scrollable-region-focusable)
        from docsnap.markdown import Renderer
        html = Renderer("a", {}, {}).render("| a | b |\n|---|---|\n| 1 | 2 |\n")
        self.assertIn('<div class="table-wrap" tabindex="0">', html)
