"""브라우저 E2E 가 쓰는 고정 사이트(tests/e2e/build_fixture.py)가 올바른지 Node 없이 확인한다.

E2E 자체는 `npm test --prefix tests/e2e` 로 따로 돌린다(브라우저가 필요하다). 여기서는 E2E 의 전제 조건만 지킨다:
고정 사이트가 만들어지고, 독립 검증기를 통과하고, E2E 가 확인할 기능이 실제로 들어 있다.
"""
import os
import sys
import tempfile
import unittest

import _path  # noqa: F401
import docs_verify
from fixtures import read

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e"))
import build_fixture  # noqa: E402


class FixtureSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = os.path.join(cls.tmp.name, ".site")
        cls.missing, cls.report = build_fixture.build(cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def page(self, lang, name):
        return read(os.path.join(self.out, lang, name + ".html"))

    def test_builds_without_missing_files_and_passes_the_independent_check(self):
        self.assertEqual(self.missing, 0)
        r = docs_verify.check(self.out)
        self.assertEqual(r["problems"], [])
        self.assertEqual(r["counts"]["pages"], 14)  # 7쪽 x 2개 언어

    def test_contains_every_feature_the_e2e_tests_rely_on(self):
        en, ko = self.page("en", "guide"), self.page("ko", "guide")
        for html in (en, ko):
            self.assertIn('class="tabs"', html)  # 본문 탭
            self.assertIn('data-lang="json"', html)
            self.assertIn('data-lang="bash"', html)
            self.assertIn("<table>", html)
            self.assertIn('class="stale-anchor"', html)  # 사라진 섹션 링크
            self.assertEqual(html.count("<h2 id="), 7)  # 개요, 표, JSON + 긴 섹션 4
        self.assertIn('href="reference.html#how-it-works"', en)  # 아코디언을 가리키는 링크 (살아 있음)
        self.assertIn('<details class="accordion" id="how-it-works">', self.page("en", "reference"))
        self.assertIn('id="how-it-works"', self.page("ko", "reference"))  # 한국어 아코디언도 영어 id
        self.assertIn('id="windows-only-heading"', ko)  # 한국어 헤딩도 영어 id (탭 안의 제목)
        self.assertEqual(self.report["counts"]["stale"], 2)  # 영어 1 + 한국어 1

    def test_pages_without_korean_fall_back_with_a_notice(self):
        self.assertIn('class="notice"', self.page("ko", "nokorean"))
        self.assertNotIn('class="notice"', self.page("en", "nokorean"))

    def test_both_languages_have_search_data_with_the_search_words(self):
        self.assertIn("zebra stripes", read(os.path.join(self.out, "search-data-en.js")))
        self.assertIn("얼룩말 줄무늬", read(os.path.join(self.out, "search-data-ko.js")))


if __name__ == "__main__":
    unittest.main()
