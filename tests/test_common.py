import unittest

import _path  # noqa: F401
from docs_common import ko_url, norm, setup_console, slug


class NormSlug(unittest.TestCase):
    def test_norm_strips_fragment_query_slash_md(self):
        self.assertEqual(norm("https://code.claude.com/docs/en/hooks.md"), "https://code.claude.com/docs/en/hooks")
        self.assertEqual(norm("https://code.claude.com/docs/en/hooks/#x?y=1"), "https://code.claude.com/docs/en/hooks")

    def test_slug(self):
        self.assertEqual(slug("https://code.claude.com/docs/en/agent-sdk/mcp.md"), "en/agent-sdk/mcp")

    def test_ko_url_only_swaps_language_prefix(self):
        self.assertEqual(ko_url("https://code.claude.com/docs/en/a/b.md"), "https://code.claude.com/docs/ko/a/b.md")
        self.assertEqual(ko_url("https://code.claude.com/docs/mcp"), "https://code.claude.com/docs/mcp")

    def test_setup_console_is_safe(self):
        setup_console()  # 예외 없이 끝나야 한다 (캡처된 스트림에서도)


if __name__ == "__main__":
    unittest.main()
