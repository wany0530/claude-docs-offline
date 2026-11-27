"""작은 JSON 으로 변환기를 끝까지 돌려 두 언어 사이트 산출물(색인, 메뉴, 링크 검사)을 확인한다. 네트워크 없음."""
import gzip
import json
import os
import tempfile
import unittest

import _path  # noqa: F401
import docsnap.site.anchors as docs_anchors
import docs_json_to_html as conv
from fixtures import build_site, page, read


class Site(unittest.TestCase):
    def build(self, pages, gz=False, **extra):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        out = os.path.join(d.name, "site")
        return build_site(pages, out, d.name, gz=gz, **extra), out

    def two_pages(self):
        return [
            page("a", "Alpha", "# Alpha\n\n## Hooks setup\nUse the [b page](https://code.claude.com/docs/en/b).\n\n```bash\nclaude --help\n```",
                 ko=("알파", "# 알파\n\n## 훅 설정\n[b 페이지](https://code.claude.com/docs/ko/b.md#beta)를 보세요.")),
            page("b", "Beta", "# Beta\n## Beta\nzebra stripes", ko=("베타", "# 베타\n## 베타\n얼룩말 줄무늬")),
        ]

    def test_files_for_both_languages(self):
        missing, out = self.build(self.two_pages())
        self.assertEqual(missing, 0)
        for name in ("index.html", "style.css", "nav.js", "nav-data-en.js", "nav-data-ko.js", "search-data-en.js",
                     "search-data-ko.js", "en/a.html", "en/b.html", "ko/a.html", "ko/b.html"):
            self.assertTrue(os.path.isfile(os.path.join(out, name)), name)
        self.assertIn("en/a.html", read(os.path.join(out, "index.html")))
        for lang in ("en", "ko"):  # 헤더 로고 뒤에 offline 표시
            self.assertIn('Claude Code Docs<span class="offline">offline</span>', read(os.path.join(out, lang, "a.html")))
            self.assertIn('<aside id="toc" aria-label=', read(os.path.join(out, lang, "a.html")))  # 우측 목차 자리
        self.assertIn('"toc": "이 페이지에서"', read(os.path.join(out, "nav-data-ko.js")))

    def test_landmarks_skip_link_favicon_and_names_in_both_languages(self):
        _, out = self.build(self.two_pages())
        expect = {"en": ("Skip to content", "Sections", "Pages", "On this page", "<span>Search...</span>"),
                  "ko": ("본문으로 건너뛰기", "섹션", "페이지", "이 페이지에서", "<span>검색...</span>")}
        for lang, words in expect.items():
            html = read(os.path.join(out, lang, "a.html"))
            self.assertIn(f'<a class="skip" href="#content">{words[0]}</a>', html)  # 첫 포커스 대상: 본문으로 건너뛰기
            self.assertIn('<main id="content" tabindex="-1">', html)  # 건너뛰기 링크의 도착 지점
            self.assertIn(f'<nav id="tabs" aria-label="{words[1]}">', html)  # 같은 역할의 랜드마크는 이름이 서로 달라야 한다
            self.assertIn(f'<nav id="nav" aria-label="{words[2]}">', html)
            self.assertIn(f'<aside id="toc" aria-label="{words[3]}">', html)
            self.assertIn(words[4], html)  # 검색 버튼의 이름은 보이는 글자 그대로다 (좁은 화면에서는 글자를 시각적으로만 숨김)
            self.assertNotIn('id="searchbtn" type="button" aria-label', html)  # 보이는 글자와 다른 이름을 따로 달면 WCAG 2.5.3 위반
            self.assertIn('aria-controls="nav" aria-expanded="false"', html)
            self.assertIn('<link rel="icon" href="data:image/svg+xml', html)  # favicon.ico 요청(404)이 없다

    def test_korean_page_uses_official_korean_text_and_borrowed_ids(self):
        _, out = self.build(self.two_pages())
        ko = read(os.path.join(out, "ko", "a.html"))
        self.assertIn("알파", ko)
        self.assertIn('id="hooks-setup"', ko)  # 영어판 헤딩 id 를 빌려 씀 (한국어 제목이어도)
        self.assertIn('href="b.html#beta"', ko)  # 한국어 본문의 링크는 ko 사이트 안으로
        self.assertIn('href="../en/a.html"', ko)  # 언어 전환
        self.assertNotIn("notice", ko)

    def test_search_and_nav_data_per_language(self):
        _, out = self.build(self.two_pages(), nav_names_ko={"Group": "그룹", "Docs": "문서"})
        data = json.loads(read(os.path.join(out, "search-data-ko.js"))[len("window.DOCS_SEARCH="):].rstrip().rstrip(";"))
        by = {d["p"]: d for d in data}
        self.assertEqual(set(by), {"ko/a.html", "ko/b.html"})
        self.assertIn("얼룩말", by["ko/b.html"]["x"])
        self.assertIn(["훅 설정", "hooks-setup"], by["ko/a.html"]["h"])
        nav = read(os.path.join(out, "nav-data-ko.js"))
        self.assertIn('"n": "문서"', nav)
        self.assertIn('"g": "그룹"', nav)
        self.assertIn('"t": "알파"', nav)
        self.assertIn('"t": "Alpha"', read(os.path.join(out, "nav-data-en.js")))

    def test_missing_korean_falls_back_to_english_with_notice(self):
        pages = [page("a", "Alpha", "# Alpha\nenglish only", ko=None)]
        _, out = self.build(pages)
        ko = read(os.path.join(out, "ko", "a.html"))
        self.assertIn("english only", ko)
        self.assertIn('class="notice"', ko)
        self.assertIn("공식 한국어판이 없어", ko)
        self.assertNotIn('class="notice"', read(os.path.join(out, "en", "a.html")))

    def test_gz_input_and_assets_shared_once(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        src = os.path.join(d.name, "docs.json.gz")
        url = "https://mintcdn.com/x/pic.png"
        p = page("a", "A", f"![alt]({url})", ko=("가", f"![그림]({url})"))
        p["assets"] = {url: "assets/pic.png"}
        with gzip.open(src, "wt", encoding="utf-8") as f:
            json.dump({"source": "s", "fetched_at": "x", "redirects": {}, "pages": [p]}, f)
        out = os.path.join(d.name, "site")
        os.makedirs(os.path.join(out, "assets"))  # 수집기가 사이트 assets/ 에 바로 저장한 상태
        with open(os.path.join(out, "assets", "pic.png"), "wb") as f:
            f.write(b"png")
        self.assertEqual(conv.main([src, out]), 0)
        self.assertIn('src="../assets/pic.png"', read(os.path.join(out, "ko", "a.html")))
        self.assertIn('src="../assets/pic.png"', read(os.path.join(out, "en", "a.html")))
        self.assertEqual(os.listdir(os.path.join(out, "assets")), ["pic.png"])

    def test_links_to_accordions_and_renamed_sections_are_settled_at_build_time(self):
        a = page("a", "Alpha", "# Alpha\n\n[acc](https://code.claude.com/docs/en/b.md#how-it-works) "
                 "[long](https://code.claude.com/docs/en/b.md#delivery-mechanisms) "
                 "[gone](https://code.claude.com/docs/en/b.md#removed-section)",
                 ko=("알파", "# 알파\n\n[acc](https://code.claude.com/docs/ko/b.md#how-it-works) "
                     "[gone](https://code.claude.com/docs/ko/b.md#removed-section)"))
        b = page("b", "Beta", "# Beta\n\n## Choose a delivery mechanism\n\n> [accordion] How it works\n>\n> text",
                 ko=("베타", "# 베타\n\n## 배달 방식 고르기\n\n> [accordion] 작동 방식\n>\n> 내용"))
        missing, out = self.build([a, b])
        self.assertEqual(missing, 0)
        en, ko = read(os.path.join(out, "en", "a.html")), read(os.path.join(out, "ko", "a.html"))
        self.assertIn('href="b.html#how-it-works"', en)  # 아코디언 제목을 가리키는 링크가 이제 살아 있음
        self.assertIn('href="b.html#choose-a-delivery-mechanism"', en)  # 제목이 길어진 섹션 (단어 일치 보정)
        self.assertIn('href="b.html" class="stale-anchor"', en)  # 사라진 섹션: 페이지 처음으로 + 표시
        self.assertIn('href="b.html#how-it-works"', ko)
        self.assertIn('id="how-it-works"', read(os.path.join(out, "ko", "b.html")))  # 한국어 아코디언도 영어 id 를 빌려 씀
        self.assertIn("페이지 처음으로 이동", ko)  # 안내 문구는 UI 문구(언어별)
        self.assertIn("no longer exists", en)
        rep = docs_anchors.REPORT
        self.assertEqual(rep["counts"]["stale"], 2)  # 영어 1 + 한국어 1
        self.assertEqual(rep["counts"]["strict"], 1)
        self.assertEqual(len(rep["stale"]), 2)

    def test_code_block_marks_language_for_highlighter(self):
        _, out = self.build([page("a", "A", "```json\n{\"k\": 1}\n```")])
        self.assertIn('data-lang="json"', read(os.path.join(out, "en", "a.html")))

    def test_uncollected_docs_link_is_not_a_missing_file(self):
        missing, _ = self.build([page("a", "A", "[x](https://code.claude.com/docs/en/nope)")])
        self.assertEqual(missing, 0)

    def test_copy_page_markdown_embedded_without_banner(self):
        _, out = self.build([page("a", "A", "> ## Documentation Index\n> x\n\n# A\n\nbody </script> text")])
        html = read(os.path.join(out, "en", "a.html"))
        raw = html.split('id="md-src">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(raw), "# A\n\nbody </script> text")


if __name__ == "__main__":
    unittest.main()
