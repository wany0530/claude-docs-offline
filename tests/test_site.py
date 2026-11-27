"""작은 JSON 으로 변환기를 끝까지 돌려 사이트 산출물(검색 색인, 링크 검사)을 확인한다. 네트워크 없음."""
import json
import os
import tempfile
import unittest

import _path  # noqa: F401
import docs_json_to_html as conv


def page(slug, title, content, category=("Docs", "x")):
    return {"category": list(category), "title": title, "url": f"https://code.claude.com/docs/{slug}.md",
            "description": "", "content": content, "assets": {}}


class Site(unittest.TestCase):
    def build(self, pages):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        src = os.path.join(d.name, "docs.json")
        with open(src, "w", encoding="utf-8") as f:
            json.dump({"source": "s", "fetched_at": "2026-01-01", "redirects": {}, "pages": pages}, f)
        out = os.path.join(d.name, "html")
        return conv.main([src, out]), out

    def test_search_index_and_files(self):
        missing, out = self.build([
            page("en/a", "Alpha", "# Alpha\n\n## Hooks setup\nUse the [b page](https://code.claude.com/docs/en/b).\n\n```bash\nclaude --help\n```"),
            page("en/b", "Beta", "# Beta\nzebra stripes"),
        ])
        self.assertEqual(missing, 0)
        for name in ("index.html", "style.css", "nav.js", "nav-data.js", "search-data.js", "en/a.html", "en/b.html"):
            self.assertTrue(os.path.isfile(os.path.join(out, name)), name)
        with open(os.path.join(out, "search-data.js"), encoding="utf-8") as f:
            text = f.read()
        data = json.loads(text[len("window.DOCS_SEARCH="):].rstrip().rstrip(";"))
        by_path = {d["p"]: d for d in data}
        self.assertEqual(set(by_path), {"en/a.html", "en/b.html"})
        self.assertIn(["Hooks setup", "hooks-setup"], by_path["en/a.html"]["h"])
        self.assertIn("zebra stripes", by_path["en/b.html"]["x"])
        self.assertNotIn("```", by_path["en/a.html"]["x"])

    def test_code_block_marks_language_for_highlighter(self):
        _, out = self.build([page("en/a", "A", "```json\n{\"k\": 1}\n```")])
        with open(os.path.join(out, "en", "a.html"), encoding="utf-8") as f:
            self.assertIn('data-lang="json"', f.read())

    def test_uncollected_docs_link_is_not_a_missing_file(self):
        # 수집되지 않은 docs 링크는 변환 대상이 아니므로 '없는 파일'로 세지 않는다
        missing, _ = self.build([page("en/a", "A", "[x](https://code.claude.com/docs/en/nope)")])
        self.assertEqual(missing, 0)


if __name__ == "__main__":
    unittest.main()
