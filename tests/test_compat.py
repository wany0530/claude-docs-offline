"""README 의 'Python 3.9 이상' 주장을 정적으로 지킨다.

이 PC 의 Python 은 3.12 이상이라 3.9 로 직접 돌려 볼 수 없다. 그래서 3.12 이상에서만 되는 f-string 문법
(식 안의 백슬래시, 식 안에서 바깥과 같은 따옴표 재사용)과 3.9 문법 위반을 소스 토큰으로 찾는다.
이 검사로 모든 3.10+ 문법을 잡지는 못한다. 실제 3.9 검증은 CI(.github/workflows/test.yml)의 3.9 작업이 한다.
"""
import ast
import glob
import io
import os
import tokenize
import unittest

import _path  # noqa: F401

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FSTRING_START = getattr(tokenize, "FSTRING_START", None)  # 3.12 이상에서만 f-string 을 토큰으로 나눈다


def sources():
    paths = glob.glob(os.path.join(ROOT, "*.py")) + glob.glob(os.path.join(ROOT, "docsnap", "**", "*.py"), recursive=True) + glob.glob(os.path.join(ROOT, "tests", "*.py"))
    for p in sorted(paths):
        with open(p, encoding="utf-8") as f:
            yield os.path.relpath(p, ROOT), f.read()


def py312_only_fstrings(src):
    """(줄, 이유) 목록. f-string 의 {…} 안에 STRING 토큰이 있는데 백슬래시를 쓰거나 바깥과 같은 따옴표를 쓰는 곳."""
    found, stack = [], []  # stack: f-string 마다 [여는 따옴표, 중괄호 깊이]
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == FSTRING_START:
            quote = tok.string.lstrip("rRbBfFuU")
            stack.append([quote, 0])
        elif tok.type == tokenize.FSTRING_END if hasattr(tokenize, "FSTRING_END") else False:
            stack.pop()
        elif stack and tok.type == tokenize.OP and tok.string == "{":
            stack[-1][1] += 1
        elif stack and tok.type == tokenize.OP and tok.string == "}":
            stack[-1][1] = max(0, stack[-1][1] - 1)
        elif stack and stack[-1][1] > 0 and tok.type == tokenize.STRING:
            body = tok.string
            if "\\" in body:
                found.append((tok.start[0], "f-string 식 안의 문자열에 백슬래시 (3.12 이상 전용)"))
            inner_quote = body.lstrip("rRbBfFuU")[:3] if body.lstrip("rRbBfFuU")[:3] in ('"""', "'''") else body.lstrip("rRbBfFuU")[:1]
            if inner_quote == stack[-1][0]:
                found.append((tok.start[0], "f-string 식 안에서 바깥과 같은 따옴표 재사용 (3.12 이상 전용)"))
    return found


class Python39Compat(unittest.TestCase):
    @unittest.skipIf(FSTRING_START is None, "이 Python(3.12 미만)은 f-string 을 토큰으로 나누지 않아 실제 파싱이 검사한다")
    def test_no_python312_only_fstring_syntax(self):
        problems = [f"{name}:{line}: {why}" for name, src in sources() for line, why in py312_only_fstrings(src)]
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_sources_parse_as_python39_grammar(self):
        for name, src in sources():
            try:
                ast.parse(src, filename=name, feature_version=(3, 9))
            except SyntaxError as e:
                self.fail(f"{name}: 3.9 문법이 아님: {e}")

    def test_detector_catches_known_bad_and_accepts_good(self):
        if FSTRING_START is None:
            self.skipTest("3.12 미만")
        bad_backslash = 'x = 1\ny = f"{\'a\\"b\' if x else 0}"\n'
        bad_quote = 'x = {"k": 1}\ny = f"{x["k"]}"\n'
        good = 'x = {"k": 1}\ny = f"{x[\'k\']} \\n {1 + 1}"\n'
        self.assertIn("백슬래시", py312_only_fstrings(bad_backslash)[0][1])
        self.assertIn("같은 따옴표", py312_only_fstrings(bad_quote)[0][1])
        self.assertEqual(py312_only_fstrings(good), [])


if __name__ == "__main__":
    unittest.main()
