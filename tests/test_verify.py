"""독립 검증기(docs_verify)와 검토 장부·힌트 보조 함수를 작은 사이트로 검사한다. 네트워크 없음."""
import json
import os
import tempfile
import unittest

import _path  # noqa: F401
import docsnap.site.anchors as anchors
import docsnap.site.verify as docs_verify


def article(body, h1=True):
    title = '<h1 id="t">T</h1>' if h1 else ""  # f-string 식 안에 따옴표·백슬래시를 두면 3.12 미만에서 문법 오류
    return ('<html><body><header><a href="nowhere.html#x">header link is outside the article</a></header>'
            f"<article>{title}{body}</article></body></html>")


class VerifySite(unittest.TestCase):
    def check(self, pages, files=()):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        for rel, html in pages.items():
            path = os.path.join(d.name, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
        for rel in files:
            path = os.path.join(d.name, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(b"x")
        return docs_verify.check(d.name)

    def kinds(self, result):
        return sorted(k for _, k, _ in result["problems"])

    def test_clean_site_passes_and_is_counted(self):
        r = self.check({
            "en/a.html": article('<a href="b.html#sec">x</a> <a href="#own">y</a><h2 id="own">O</h2>'
                                 '<a href="https://example.com/#nope">ext</a> <a href="vscode://settings/x">app</a>'),
            "en/b.html": article('<h2 id="sec">S<a class="anchor" href="#sec">#</a></h2>'),
        })
        self.assertEqual(r["problems"], [])
        self.assertEqual(r["counts"]["pages"], 2)
        self.assertEqual(r["counts"]["anchors"], 2)

    def test_dangling_anchor_and_missing_file_are_violations(self):
        r = self.check({"en/a.html": article('<a href="b.html#gone">x</a> <a href="missing.html">y</a>'),
                        "en/b.html": article("")})
        self.assertEqual(self.kinds(r), ["없는 앵커", "없는 파일"])

    def test_same_page_anchor_is_checked(self):
        r = self.check({"en/a.html": article('<a href="#nope">x</a>')})
        self.assertEqual(self.kinds(r), ["없는 앵커"])

    def test_percent_encoded_anchor_matches_raw_id(self):
        r = self.check({"ko/a.html": article('<a href="#%EC%84%A4%EC%A0%95">x</a><h2 id="설정">설정</h2>')})
        self.assertEqual(r["problems"], [])

    def test_duplicate_ids_and_h1_count(self):
        r = self.check({"en/a.html": article('<h2 id="d">1</h2><h2 id="d">2</h2>'),
                        "en/b.html": article("", h1=False),
                        "en/c.html": article('<h1 id="t2">second</h1>')})
        self.assertEqual(self.kinds(r), ["h1 개수", "h1 개수", "중복 id"])

    def test_control_characters_left_by_the_converter_are_caught(self):
        r = self.check({"en/a.html": article('<a href="\x01">leftover</a>')})
        self.assertIn("제어 문자 잔존", self.kinds(r))

    def test_stale_link_must_not_keep_an_anchor(self):
        r = self.check({"en/a.html": article('<a href="b.html" class="stale-anchor" title="t">ok</a>'
                                             '<a href="b.html#x" class="stale-anchor">bad</a>'
                                             '<a href="#" class="stale-anchor">ok too</a>'),
                        "en/b.html": article('<h2 id="x">x</h2>')})
        self.assertEqual(self.kinds(r), ["끊김 표시 링크에 앵커가 남음"])
        self.assertEqual(r["counts"]["stale"], 3)

    def test_code_sample_text_that_looks_like_markup_is_ignored(self):
        # 코드 예시 속 id="…" 와 href="#..." 는 태그가 아니라 글자다 (정규식 검사가 틀렸던 부분)
        r = self.check({"en/a.html": article('<pre><code>&lt;p id="dup"&gt; &lt;p id="dup"&gt; &lt;a href="#nope"&gt;</code></pre>')})
        self.assertEqual(r["problems"], [])

    def test_cli_exit_code_is_nonzero_only_when_there_are_violations(self):
        import contextlib
        import io
        for body, expected in (('<a href="#ok">x</a><h2 id="ok">o</h2>', 0), ('<a href="#bad">x</a>', 1)):
            d = tempfile.TemporaryDirectory()
            self.addCleanup(d.cleanup)
            os.makedirs(os.path.join(d.name, "en"))
            with open(os.path.join(d.name, "en", "a.html"), "w", encoding="utf-8") as f:
                f.write(article(body))
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = docs_verify.main([d.name])
            self.assertEqual(code, expected)
            self.assertIn("위반", out.getvalue())

    def test_missing_asset_reference_is_caught_and_present_one_passes(self):
        pages = {"en/a.html": article('<img src="../assets/ok.png"><video src="../assets/gone.mp4"></video>')}
        r = self.check(pages, files=["assets/ok.png"])
        self.assertEqual([d for _, _, d in r["problems"]], ["../assets/gone.mp4"])


class LedgerAndHints(unittest.TestCase):
    def test_ledger_key_drops_language_prefix(self):
        self.assertEqual(anchors.ledger_key("en/agent-sdk/mcp", "in-code"), "agent-sdk/mcp#in-code")
        self.assertEqual(anchors.ledger_key("ko/agent-sdk/mcp", "in-code"), "agent-sdk/mcp#in-code")

    def test_compare_reports_new_and_changed_but_not_reviewed(self):
        strict = {("en/a", "en/b", "old", "new-id"), ("ko/a", "ko/b", "old", "new-id"),   # 장부와 같음 (두 언어)
                  ("en/a", "en/b", "moved", "other"),                                     # 장부와 다른 id
                  ("en/a", "en/c", "fresh", "fresh-long")}                                # 장부에 없음
        ledger = {"b#old": "new-id", "b#moved": "was-here"}
        new, changed = anchors.compare_ledger(strict, ledger)
        self.assertEqual(new, [("c#fresh", "fresh-long")])
        self.assertEqual(changed, [("b#moved", "was-here", "other")])

    def test_load_ledger_reads_pairs_and_tolerates_missing_file(self):
        self.assertEqual(anchors.load_ledger("no-such-file.json"), {})
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"note": "x", "pairs": {"a#b": "c"}}, f)
            self.assertEqual(anchors.load_ledger(p), {"a#b": "c"})

    def test_repo_ledger_is_wellformed(self):
        pairs = anchors.load_ledger()
        self.assertGreaterEqual(len(pairs), 91)
        for k, v in pairs.items():
            self.assertRegex(k, r"^[^#/][^#]*#[^#]+$")
            self.assertTrue(v and "#" not in v)

    def test_nearest_id_scores_word_overlap_and_is_only_a_hint(self):
        ids = {"auto-mode-on-bedrock-agent-platform-or-foundry", "unrelated-section"}
        score, best = anchors.nearest_id("enable-auto-mode-on-bedrock-agent-platform-or-foundry", ids)
        self.assertEqual(best, "auto-mode-on-bedrock-agent-platform-or-foundry")
        self.assertGreaterEqual(score, anchors.HINT_MIN)
        self.assertEqual(anchors.nearest_id("zzz", ids), (0.0, ""))
        self.assertEqual(anchors.nearest_id("anything", set()), (0.0, ""))


if __name__ == "__main__":
    unittest.main()
