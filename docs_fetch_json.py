#!/usr/bin/env python3
"""Claude Code 공식 문서 전체를 하나의 JSON 파일로 저장합니다.

사용법:  python docs_fetch_json.py [출력파일.json]
저장 내용: 페이지별 분류(category) / 본문(content, 원문 그대로) / 좌측 메뉴 이름(nav_label) /
           본문 이미지·동영상(출력 JSON 옆 assets/ 폴더) / 숨은 페이지(_unlisted) / 옛 링크 별칭(redirects)
외부 패키지 없이 표준 라이브러리만 사용합니다.
"""
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from docs_common import norm, setup_console, slug

INDEX_URL = "https://code.claude.com/docs/llms.txt"
LINK_RE = re.compile(r"-\s*\[([^\]]+)\]\((https://code\.claude\.com/docs/[^)\s]+?\.md)\)(?::\s*(.*))?")
HEAD_RE = re.compile(r"^(#{2,6})\s+(.*)")
LABEL_RE = re.compile(r'<li id="/(en/[^"]+)"[^>]*data-title="([^"]*)"')  # 사이트 HTML 좌측 메뉴
GROUP_RE = re.compile(r'<li[^>]*data-title="([^"]*)"[^>]*\bid="/(en/[^"]+)"')  # 접히는 그룹 제목 (id 가 뒤에 옴)
DOC_LINK_RE =re.compile(r"\]\((https://code\.claude\.com/docs/[^)\s]+)")
ASSET_RE = re.compile(r"https://mintcdn\.com/[^\s)\"'<>]+")
UA = {"User-Agent": "docs-snapshot/1.0"}


def _open(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.geturl(), r.headers.get("content-type", ""), r.read().decode("utf-8")


def get(url, retries=3):
    for attempt in range(retries):
        try:
            final, ctype, body = _open(url)
            if url.endswith(".md") and "text/html" in ctype:
                # 다른 경로로 리다이렉트되어 HTML이 온 경우: 최종 URL + ".md" 로 1회 재시도
                final, ctype, body = _open(final.rstrip("/") + ".md")
                if "text/html" in ctype:
                    raise ValueError("markdown 대신 HTML 반환: " + final)
            return body
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def get_bytes(url, retries=3):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def parse_index():
    seen, entries, stack = set(), [], []
    for line in get(INDEX_URL).splitlines():
        h = HEAD_RE.match(line)
        if h:  # ## 대분류 > ### 그룹 > #### 중분류 > ##### 하위그룹
            stack = stack[: len(h.group(1)) - 2] + [h.group(2).strip()]
            continue
        m = LINK_RE.match(line)
        if m and m.group(2) not in seen:
            seen.add(m.group(2))
            entries.append({"category": list(stack), "title": m.group(1), "url": m.group(2),
                            "description": (m.group(3) or "").strip()})
    return entries


def resolve_links(pages):
    """본문이 링크하지만 수집되지 않은 주소를 처리: 옛 주소면 redirects, 숨은 페이지면 추가."""
    have = {norm(p["url"]): p["url"] for p in pages}
    redirects, unresolved, endpoints = {}, {}, {}
    while True:
        missing = {norm(u) for p in pages if p["content"] for u in DOC_LINK_RE.findall(p["content"])}
        missing -= have.keys() | redirects.keys() | unresolved.keys() | endpoints.keys()
        if not missing:
            return redirects, unresolved, endpoints
        for link in sorted(missing):
            try:
                final, ctype, _ = _open(link)
                fn = norm(final)
                if fn in have:
                    redirects[link] = have[fn]
                elif fn.startswith("https://code.claude.com/docs/en/") and "text/html" in ctype:
                    body = get(fn + ".md")
                    m = re.search(r"^# (.+)\n\n> (.+)$", body, re.M)
                    pages.append({"category": ["_unlisted"], "title": m.group(1).strip() if m else slug(fn),
                                  "url": fn + ".md", "description": m.group(2).strip() if m else "",
                                  "content": body})
                    have[fn] = fn + ".md"
                else:
                    endpoints[link] = "docs 페이지가 아님: " + final  # 서버 응답이 405 대신 이렇게 올 때도 있음
            except urllib.error.HTTPError as e:
                if e.code == 405:  # GET 불가 = 페이지가 아닌 API/MCP 서버 엔드포인트 (예: /docs/mcp)
                    endpoints[link] = "HTTP 405: 문서 페이지가 아닌 엔드포인트"
                else:
                    unresolved[link] = str(e)
            except Exception as e:
                unresolved[link] = str(e)


def add_nav_labels(pages):
    """사이트 HTML 좌측 메뉴의 표시 이름을 nav_label 로 저장 (없으면 title)."""
    labels = {}

    def harvest(url):
        try:
            _, _, page = _open(norm(url))
        except Exception:
            return
        for s, label in LABEL_RE.findall(page):
            labels[s] = html.unescape(label)
        for label, s in GROUP_RE.findall(page):
            labels.setdefault(s, html.unescape(label))

    listed = [p for p in pages if p["category"][0] != "_unlisted"]
    firsts = {}
    for p in listed:
        firsts.setdefault(p["category"][0], p)  # 대분류(상단 탭)마다 첫 페이지의 HTML 에 그 탭 메뉴 전체가 있음
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(harvest, [p["url"] for p in firsts.values()]))
    for p in listed:  # 위에서 못 찾은 페이지는 자기 HTML 에서 직접 찾음
        if slug(p["url"]) not in labels:
            harvest(p["url"])
    fallback = [p["title"] for p in pages if slug(p["url"]) not in labels]
    for p in pages:
        p["nav_label"] = labels.get(slug(p["url"]), p["title"])
    return fallback


def download_assets(pages, assets_dir):
    """본문의 mintcdn 이미지·동영상을 받아 assets_dir 에 저장. 페이지에 {원격 URL: 'assets/파일'} 기록."""
    names = {}
    for p in pages:
        for u in ASSET_RE.findall(p["content"] or ""):
            base = re.sub(r"[^\w.\-]", "_", urllib.parse.unquote(urllib.parse.urlparse(u).path.rsplit("/", 1)[-1]))
            names[u] = hashlib.sha1(u.encode()).hexdigest()[:10] + "_" + base
    os.makedirs(assets_dir, exist_ok=True)
    errors = {}

    def save(item):
        u, name = item
        try:
            with open(os.path.join(assets_dir, name), "wb") as f:
                f.write(get_bytes(u.replace("\\&", "&")))  # markdown 이스케이프(\&)는 실제 주소에선 &
        except Exception as e:
            errors[u] = str(e)

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(save, names.items()))
    for p in pages:
        p["assets"] = {u: "assets/" + names[u] for u in dict.fromkeys(ASSET_RE.findall(p["content"] or ""))
                       if u not in errors}
    return len(names), errors


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = argv[0] if argv else os.path.join(date.today().isoformat(), "docs.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    assets_dir = os.path.join(os.path.dirname(os.path.abspath(out)), "assets")  # JSON 옆 assets/

    entries = parse_index()
    print(f"페이지 {len(entries)}개 발견", file=sys.stderr)

    def fetch(entry):
        try:
            entry["content"] = get(entry["url"])
        except Exception as e:
            entry["content"] = None
            entry["error"] = str(e)
        return entry

    with ThreadPoolExecutor(max_workers=8) as ex:
        pages = list(ex.map(fetch, entries))

    redirects, unresolved, endpoints = resolve_links(pages)
    no_label = add_nav_labels(pages)
    n_assets, asset_errors = download_assets(pages, assets_dir)

    failed = [p["url"] for p in pages if p["content"] is None]
    snapshot = {
        "source": INDEX_URL,
        "fetched_at": date.today().isoformat(),
        "page_count": len(pages),
        "redirects": redirects,  # 본문 링크(.md·# 제거) -> 실제 수집된 페이지 url
        "unresolved_links": unresolved,
        "non_page_links": endpoints,  # 문서 페이지가 아닌 링크(MCP 서버 등): 수집 대상 아님
        "assets_dir": os.path.basename(assets_dir),
        "asset_errors": asset_errors,
        "pages": pages,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"저장 완료: {out} (페이지 {len(pages)}개, 실패 {len(failed)}개)", file=sys.stderr)
    print(f"별칭 {len(redirects)}개, 숨은 페이지 {sum(p['category'][0] == '_unlisted' for p in pages)}개, "
          f"메뉴 이름 없음(title 사용) {len(no_label)}개, 미확인 링크 {len(unresolved)}개, "
          f"비문서 링크 {len(endpoints)}개", file=sys.stderr)
    print(f"에셋 {n_assets}개 -> {assets_dir} (실패 {len(asset_errors)}개)", file=sys.stderr)
    for u in failed:
        print("  실패:", u, file=sys.stderr)
    for u, e in {**unresolved, **asset_errors}.items():
        print("  확인 필요:", u, "-", e, file=sys.stderr)
    for t in no_label:
        print("  메뉴 이름 없음:", t, file=sys.stderr)


if __name__ == "__main__":
    setup_console()
    main()
