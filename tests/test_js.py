"""site_src/lib.js 의 Node 내장 테스트(tests/js/*.test.js)를 unittest 안에서 함께 실행한다.

Node 가 없으면 건너뛴다(도구 자체는 Node 없이 동작한다. 이 테스트는 개발용이다).
"""
import glob
import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class NodeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node 가 없어 JS 테스트를 건너뜀")
    def test_lib_js_node_tests_pass(self):
        files = sorted(glob.glob(os.path.join(HERE, "js", "*.test.js")))
        self.assertTrue(files, "tests/js/*.test.js 가 없음")
        out = subprocess.run(["node", "--test", *files], capture_output=True, text=True, encoding="utf-8", timeout=300)
        self.assertEqual(out.returncode, 0, out.stdout[-3000:] + out.stderr[-1000:])


if __name__ == "__main__":
    unittest.main()
