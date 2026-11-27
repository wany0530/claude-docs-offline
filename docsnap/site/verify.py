"""만들어진 사이트(en/, ko/ 의 HTML)를 변환기와 무관하게 다시 읽어 링크를 전수 검사합니다.

변환기가 앵커를 어떻게 확정했는지는 보지 않고 결과 HTML 만 봅니다 (html.parser 로 파싱하므로 코드 예시 속
`id="..."` 같은 글자는 태그가 아니라 무시됩니다). 이 검사는 "대상 id 가 실제로 있다"까지만 보장합니다.

사용: python docs_verify.py output/site      (위반이 있으면 종료 코드 1)
"""
import collections
import os
import sys
import urllib.parse
from html.parser import HTMLParser

from docsnap.common import setup_console

LANG_DIRS = ("en", "ko")


class _Page(HTMLParser):
    """<article> 안의 id, 링크, 파일 참조, h1 개수를 모은다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_article = False
        self.ids, self.dup_ids = set(), []
        self.links = []  # (href, 'anchor'|'stale'|'link')
        self.files = []  # img/video/source 의 src
        self.h1 = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "article":
            self.in_article = True
            return
        if not self.in_article:
            return
        if a.get("id"):
            if a["id"] in self.ids:
                self.dup_ids.append(a["id"])
            self.ids.add(a["id"])
        if tag == "h1":
            self.h1 += 1
        elif tag == "a" and "href" in a:
            cls = (a.get("class") or "").split()
            kind = "anchor" if "anchor" in cls else "stale" if "stale-anchor" in cls else "link"
            self.links.append((a["href"], kind))
        elif tag in ("img", "video", "source") and a.get("src"):
            self.files.append(a["src"])

    def handle_endtag(self, tag):
        if tag == "article":
            self.in_article = False


def _external(href):
    """스킴이 있는 주소(https:, mailto:, vscode://settings/... 같은 앱 딥링크 등)와 //호스트 는 사이트 파일이 아니다."""
    return bool(urllib.parse.urlparse(href).scheme) or href.startswith("//")


def _pages(site_dir):
    for lang in LANG_DIRS:
        for dp, _, fn in os.walk(os.path.join(site_dir, lang)):
            for f in sorted(fn):
                if f.endswith(".html"):
                    yield os.path.join(dp, f)


def check(site_dir):
    """사이트 폴더의 모든 페이지를 검사한다. {"counts": {...}, "problems": [(페이지, 종류, 내용), ...]} 를 돌려준다."""
    site_dir = os.path.abspath(site_dir)
    parsed, problems, counts = {}, [], collections.Counter()
    for path in _pages(site_dir):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        p = _Page()
        p.feed(text)
        p.close()
        key = os.path.normcase(os.path.normpath(path))
        parsed[key] = p
        rel = os.path.relpath(path, site_dir).replace(os.sep, "/")
        counts["pages"] += 1
        if "\x01" in text or "\x00" in text:
            problems.append((rel, "제어 문자 잔존", "\\x01/\\x00"))
        if p.h1 != 1:
            problems.append((rel, "h1 개수", f"{p.h1}개 (1개여야 함)"))
        for i in dict.fromkeys(p.dup_ids):
            problems.append((rel, "중복 id", i))

    for key, p in parsed.items():
        rel = os.path.relpath(key, os.path.normcase(site_dir)).replace(os.sep, "/")
        here = os.path.dirname(key)
        for src in p.files:
            if not _external(src) and not os.path.isfile(os.path.normpath(os.path.join(here, urllib.parse.unquote(src.split("?")[0])))):
                problems.append((rel, "없는 파일", src))
            counts["files"] += 1
        for href, kind in p.links:
            if kind == "anchor" or _external(href):
                continue
            target, _, frag = href.partition("#")
            if kind == "stale":
                counts["stale"] += 1
                if frag:
                    problems.append((rel, "끊김 표시 링크에 앵커가 남음", href))
                if target and not os.path.isfile(os.path.normpath(os.path.join(here, urllib.parse.unquote(target)))):
                    problems.append((rel, "없는 파일", href))
                continue
            counts["links"] += 1
            tpath = key if not target else os.path.normcase(os.path.normpath(os.path.join(here, urllib.parse.unquote(target))))
            if target and not os.path.isfile(tpath):
                problems.append((rel, "없는 파일", href))
                continue
            if frag:
                counts["anchors"] += 1
                tp = parsed.get(tpath)
                if tp is None:  # en/ ko/ 밖의 페이지(index.html 등): 앵커는 확인 대상이 아님
                    continue
                if urllib.parse.unquote(frag) not in tp.ids and frag not in tp.ids:
                    problems.append((rel, "없는 앵커", href))
    return {"counts": dict(counts), "problems": problems}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    site = argv[0] if argv else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "output", "site")
    r = check(site)
    c = r["counts"]
    print(f"독립 검사: 페이지 {c.get('pages', 0)}개, 링크 {c.get('links', 0)}건(앵커 {c.get('anchors', 0)}건), "
          f"끊김 표시 {c.get('stale', 0)}건, 파일 참조 {c.get('files', 0)}건 -> 위반 {len(r['problems'])}건")
    for page, kind, detail in r["problems"][:50]:
        print(f"  {kind}: {page} -> {detail}")
    if len(r["problems"]) > 50:
        print(f"  ... 외 {len(r['problems']) - 50}건")
    return 1 if r["problems"] else 0


if __name__ == "__main__":
    setup_console()
    sys.exit(main())
