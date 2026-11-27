"""CLAUDE.md 불변 조건: Python 의 anchor_key 와 JS(site_src/lib.js)의 anchorKey 는 같은 규칙이어야 한다.

예전에는 JS 소스에 특정 글자가 있는지만 확인했다. 지금은 같은 입력을 두 구현에 넣어 결과를 비교한다 (Node 필요).
"""
import json
import os
import shutil
import subprocess
import unittest

import _path  # noqa: F401
import docsnap.markdown as docs_markdown

LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site_src", "lib.js")

# 일반 케이스와 경계 케이스(깨진 %인코딩, 결합 문자, 전각, 위첨자, 이모지)
CASES = ["A%20b-C_d.é", "What%27s-New.v2", "%E0%A4%A", "%A", "%zz", "%ff", "%C3%A9", "설정-값", "%EC%84%A4%EC%A0%95",
         "a_b", "x²y", "ⅷ", "ａｂｃ１２３", "é", "a😀b", "100%", "%", "", "Hello World", "Q&A?", "Iowa's-Rule.v1.2"]


class AnchorSync(unittest.TestCase):
    def test_python_anchor_key_rule(self):
        self.assertEqual(docs_markdown.anchor_key("A%20b-C_d.é"), "abcdé")
        self.assertEqual(docs_markdown.anchor_key("%ff"), "ff")  # 깨진 인코딩은 디코딩하지 않는다 (JS 와 같게)

    @unittest.skipUnless(shutil.which("node"), "node 가 없어 JS 쪽 비교를 건너뜀")
    def test_python_and_js_agree_on_every_case(self):
        script = ("const L=require(require('path').resolve(process.argv[1]));"
                  "const c=JSON.parse(require('fs').readFileSync(0,'utf8'));"
                  "process.stdout.write(JSON.stringify(c.map(L.anchorKey)))")
        out = subprocess.run(["node", "-e", script, LIB], input=json.dumps(CASES), capture_output=True,
                             text=True, encoding="utf-8", timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        for case, js in zip(CASES, json.loads(out.stdout)):
            self.assertEqual(docs_markdown.anchor_key(case), js, f"입력 {case!r}")


if __name__ == "__main__":
    unittest.main()
