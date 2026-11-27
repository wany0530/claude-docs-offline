"""CLAUDE.md 불변 조건: Python 의 anchor_key 와 JS 상수 안의 anchorKey 는 같은 규칙이어야 한다."""
import re
import unittest

import _path  # noqa: F401
import docs_json_to_html as conv


class AnchorSync(unittest.TestCase):
    def test_js_anchor_key_rule(self):
        m = re.search(r"function anchorKey\(s\)\{(.*?)\}\n", conv.JS)
        self.assertIsNotNone(m, "JS 에서 anchorKey 를 찾을 수 없음")
        body = m.group(1)
        self.assertIn("decodeURIComponent", body)   # URL 디코딩
        self.assertIn("toLowerCase()", body)         # 소문자
        self.assertIn(r"/[^\p{L}\p{N}]/gu", body)    # 글자·숫자만 남김

    def test_python_anchor_key_rule(self):
        self.assertEqual(conv.anchor_key("A%20b-C_d.é"), "abcdé")


if __name__ == "__main__":
    unittest.main()
