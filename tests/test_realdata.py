"""실제로 수집해 둔 최신 이력(output/history/*.json.gz)으로 변환기를 끝까지 돌려 데이터 불변식을 확인한다.

기본은 건너뛴다: output/ 은 git 에 올라가지 않아 새로 받은 저장소에는 없고, 에셋 복사 때문에 몇 초 걸린다.
실행:  DOCS_REAL=1 python -m unittest discover tests -p "test_realdata.py"      (PowerShell: $env:DOCS_REAL=1)
업스트림 문서가 바뀌어 장부에 없는 새 보정이 생기면 이 테스트가 실패한다. 그건 오류가 아니라 '검토 필요' 신호다.
"""
import glob
import json
import os
import tempfile
import unittest

import _path  # noqa: F401
import docs_anchors
import docs_diff
import docs_json_to_html as conv
import docs_verify

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HISTORY = sorted(glob.glob(os.path.join(ROOT, "output", "history", "*.json.gz")))
ASSETS = os.path.join(ROOT, "output", "site", "assets")


def limits():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "real_data_limits.json"), encoding="utf-8") as f:
        return json.load(f)


@unittest.skipUnless(os.environ.get("DOCS_REAL") == "1", "DOCS_REAL=1 일 때만 실제 데이터로 실행")
@unittest.skipUnless(HISTORY and os.path.isdir(ASSETS), "output/history 와 output/site/assets 가 없음")
class RealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = os.path.join(cls.tmp.name, "site")
        cls.missing = conv.main([HISTORY[-1], cls.out, ASSETS])
        cls.report = dict(docs_anchors.REPORT)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_link_points_to_a_missing_file(self):
        self.assertEqual(self.missing, 0)

    def test_independent_check_finds_no_violation(self):
        r = docs_verify.check(self.out)
        self.assertEqual(r["problems"], [], r["problems"][:5])
        self.assertGreaterEqual(r["counts"]["pages"], 2 * limits()["min_pages"])

    def test_korean_pages_reuse_every_english_heading_and_accordion_id(self):
        for key in ("ko_heading_full", "ko_accordion_full"):
            got, total = self.report[key]
            self.assertGreater(total, 0, key)
            self.assertEqual(got, total, f"{key}: 영어판 id 를 다 빌려 쓰지 못한 페이지가 있음")

    def test_every_word_match_fix_has_been_reviewed(self):
        self.assertEqual(self.report["unreviewed"], [], "장부(reviewed_anchors.json)에 없는 새 보정: 대상 제목을 확인하고 추가")
        self.assertEqual(self.report["ledger_changed"], [], "장부와 다른 id 로 보정된 것")

    def test_sidebar_follows_the_official_order_stored_in_the_snapshot(self):
        snap = docs_diff.open_json(HISTORY[-1])
        order = snap.get("nav_order")
        if not order:
            self.skipTest("이 이력에는 nav_order 가 없음 (옛 형식)")
        with open(os.path.join(self.out, "nav-data-en.js"), encoding="utf-8") as f:
            text = f.read()
        nav = json.loads(text[len("window.DOCS_NAV="):text.index(";" + chr(10) + "window.DOCS_UI")])
        wrong = []

        def check(children, pos, depth, where):
            ranks = [(pos[k], k[1]) for k in (("p", c["p"][:-5]) if "p" in c else ("g" if depth == 0 else "s", c["g"]) for c in children)
                     if k in pos]
            if [r for r, _ in ranks] != sorted(r for r, _ in ranks):
                wrong.append(where)
            for c in children:
                if "g" in c:
                    check(c["c"], pos, depth + 1, where + " > " + c["g"])

        for tab in nav["tabs"]:
            if tab["n"] in order:
                check(tab["c"], {tuple(x): i for i, x in enumerate(order[tab["n"]])}, 0, tab["n"])
        self.assertEqual(wrong, [], "공식 사이드바와 형제 순서가 다른 그룹")

    def test_stale_and_fixed_link_counts_stay_within_limits(self):
        stale = {(t, f) for s, t, f, _ in self.report["stale"] if s.startswith("en/")}
        strict = {(t, f) for s, t, f, _ in self.report["strict"] if s.startswith("en/")}
        self.assertLessEqual(len(stale), limits()["max_stale_unique_en"], "끊긴 링크가 크게 늘었음: 공식 문서가 개편됐을 수 있음")
        self.assertLessEqual(len(strict), limits()["max_strict_unique_en"])


if __name__ == "__main__":
    unittest.main()
