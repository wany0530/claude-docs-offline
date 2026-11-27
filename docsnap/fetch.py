#!/usr/bin/env python3
"""Claude Code 공식 문서 전체(영어 + 공식 한국어판)를 하나의 JSON 파일로 저장합니다.

사용법:  python docs_fetch_json.py [출력파일.json [에셋폴더]]
저장 내용: 페이지별 분류(category) / 본문(content, 원문 그대로) / 좌측 메뉴 이름(nav_label) /
           공식 한국어판(ko: 제목·설명·본문·메뉴 이름. 번역이 아니라 /docs/ko/ 원문이며, 없으면 null) /
           본문 이미지·동영상(에셋폴더, 기본은 출력 JSON 옆 assets/) / 숨은 페이지(_unlisted) / 옛 링크 별칭(redirects)
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

from docsnap.common import ko_url, norm, setup_console, slug

INDEX_URL = "https://code.claude.com/docs/llms.txt"
LINK_RE = re.compile(r"-\s*\[([^\]]+)\]\((https://code\.claude\.com/docs/[^)\s]+?\.md)\)(?::\s*(.*))?")
HEAD_RE = re.compile(r"^(#{2,6})\s+(.*)")
LABEL_RE = re.compile(r'<li id="/((?:en|ko)/[^"]+)"[^>]*data-title="([^"]*)"')  # 사이트 HTML 좌측 메뉴
GROUP_RE = re.compile(r'<li[^>]*data-title="([^"]*)"[^>]*\bid="/((?:en|ko)/[^"]+)"')  # 접히는 그룹 제목 (id 가 뒤에 옴)
TAB_RE = re.compile(r'nav-tabs-item group[^>]*>(.*?)</(?:a|button)>', re.S)  # 상단 탭 이름 (현재 탭은 button, 나머지는 a)
SUB_RE = re.compile(r'<li data-title="([^"]*)" data-group-tag')  # 사이드바의 접히는 하위 그룹 (id 없음, 문서 순서로 짝지음)
GROUPH_RE = re.compile(r'sidebar-group-header[^>]*>(.*?)</div>', re.S)  # 사이드바 그룹 제목
DOC_LINK_RE =re.compile(r"\]\((https://code\.claude\.com/docs/[^)\s]+)")
ASSET_RE = re.compile(r"https://mintcdn\.com/[^\s)\"'<>]+")
UA = {"User-Agent": "docs-snapshot/1.0"}


def _open(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.geturl(), r.headers.get("content-type", ""), r.read().decode("utf-8")


def _retryable(e):
    """404 같은 4xx 는 다시 요청해도 같은 답이 오므로 재시도하지 않는다 (408·429 는 일시적이라 재시도)."""
    return not (isinstance(e, urllib.error.HTTPError) and 400 <= e.code < 500 and e.code not in (408, 429))


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
        except Exception as e:
            if attempt == retries - 1 or not _retryable(e):
                raise
            time.sleep(2 ** attempt)


def get_bytes(url, retries=3):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except Exception as e:
            if attempt == retries - 1 or not _retryable(e):
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


def _clean(x):
    return html.unescape(re.sub(r"<[^>]+>", "", x)).strip()


def parse_nav(page):
    """사이트 HTML 문자열 한 장에서 (메뉴 이름 {slug: 이름}, 상단 탭 이름들, 사이드바 그룹 제목들, 하위 그룹 이름들, 사이드바 순서)를 읽는다.

    사이드바 순서는 그룹 제목("g")·페이지("p", 'en/slug')·하위 그룹 헤더("s")를 문서에 나온 순서대로 [[종류, 이름], ...] 로 담는다.
    공식 사이트는 일반 페이지와 하위 그룹을 섞어 나열하는데 llms.txt 는 그렇지 않아서, 변환기가 형제 항목의 순서를 이것에 맞춘다.
    (접힌 하위 그룹의 자식 페이지는 HTML 에 없으므로 순서에도 없다.)"""
    labels, events = {}, []
    for m in LABEL_RE.finditer(page):
        labels[m.group(1)] = html.unescape(m.group(2))
        events.append((m.start(), "p", m.group(1)))
    for m in GROUP_RE.finditer(page):
        labels.setdefault(m.group(2), html.unescape(m.group(1)))
        events.append((m.start(), "p", m.group(2)))
    uniq = lambda xs: list(dict.fromkeys(x for x in map(_clean, xs) if x))
    for m in GROUPH_RE.finditer(page):
        if _clean(m.group(1)):
            events.append((m.start(), "g", _clean(m.group(1))))
    for m in SUB_RE.finditer(page):
        events.append((m.start(), "s", html.unescape(m.group(1))))
    order, seen = [], set()
    for _, kind, name in sorted(events):
        if (kind, name) not in seen:
            seen.add((kind, name))
            order.append([kind, name])
    subs = [html.unescape(x) for x in SUB_RE.findall(page)]
    return labels, uniq(TAB_RE.findall(page)), uniq(GROUPH_RE.findall(page)), subs, order


def scan_nav(url):
    """parse_nav 를 주소의 사이트 HTML 에 적용한다. 받지 못하면 빈 값."""
    try:
        _, _, page = _open(norm(url))
    except Exception:
        return {}, [], [], [], []
    return parse_nav(page)


def add_nav_labels(pages, lang="en"):
    """사이트 HTML 좌측 메뉴의 표시 이름을 nav_label 로 저장 (없으면 title).

    lang="ko" 이면 각 페이지의 ko 항목(있는 것만)에 저장한다.
    (메뉴 이름 {slug: 이름}, 상단 탭 이름들, {탭: 그룹 제목들}, {탭: 하위 그룹 이름들}, 이름을 못 찾은 제목들,
    {탭: 사이드바 순서})를 돌려준다.
    """
    def target(p):  # lang 별로 메뉴 이름을 저장할 dict
        return p if lang == "en" else p.get("ko")

    def page_url(p):
        return p["url"] if lang == "en" else ko_url(p["url"])

    labels, tabs, groups, subs, orders = {}, [], {}, {}, {}
    listed = [p for p in pages if p["category"][0] != "_unlisted" and target(p)]
    firsts = {}
    for p in listed:
        firsts.setdefault(p["category"][0], p)  # 대분류(상단 탭)마다 첫 페이지의 HTML 에 그 탭 메뉴 전체가 있음
    with ThreadPoolExecutor(max_workers=8) as ex:
        scans = list(ex.map(lambda p: scan_nav(page_url(p)), firsts.values()))
    for (tab, _), (lab, tb, gr, sb, od) in zip(firsts.items(), scans):
        labels.update(lab)
        tabs = tabs or tb
        groups[tab], subs[tab], orders[tab] = gr, sb, od
    for p in listed:  # 위에서 못 찾은 페이지는 자기 HTML 에서 직접 찾음
        if slug(page_url(p)) not in labels:
            labels.update(scan_nav(page_url(p))[0])
    fallback = []
    for p in pages:
        t = target(p)
        if not t:
            continue
        name = labels.get(slug(page_url(p)))
        if name is None:
            fallback.append(t["title"])
        t["nav_label"] = name or t["title"]
    return labels, tabs, groups, subs, fallback, orders


def nav_health(pages, tabs, labels, orders):
    """HTML 메뉴 읽기가 조용히 망가졌는지 llms.txt(독립된 출처)와 맞춰 본다. 문제 문장 목록을 돌려준다(없으면 빈 목록).

    공식 사이트가 CSS 클래스 이름만 바꿔도 정규식은 빈 결과를 내고 빌드는 성공하므로, 메뉴 이름·순서가 틀어진 사이트가 만들어진다."""
    listed = [p for p in pages if p["category"][0] != "_unlisted"]
    want = list(dict.fromkeys(p["category"][0] for p in listed))
    problems = []
    if set(want) - set(tabs):
        problems.append(f"사이트 HTML 에서 못 찾은 상단 탭: {sorted(set(want) - set(tabs))}")
    empty = [t for t in want if not any(k == "p" for k, _ in orders.get(t, []))]
    if empty:
        problems.append(f"사이드바 순서를 읽지 못한 탭: {empty}")
    named = sum(slug(p["url"]) in labels for p in listed)
    if listed and named < 0.9 * len(listed):
        problems.append(f"메뉴 이름을 찾은 페이지가 {named}/{len(listed)}개뿐")
    return problems


def fetch_korean(pages):
    """각 페이지의 공식 한국어판(/docs/ko/<slug>.md)을 받아 p["ko"] 에 저장한다 (번역이 아니라 공식 원문).

    한국어판이 없으면(공식 사이트가 다른 주소로 넘김, 404) p["ko"] = None. 그 밖의 네트워크 오류는 p["ko_error"] 에 기록한다.
    """
    def one(p):
        u = ko_url(p["url"])
        err = None
        for attempt in range(3):
            try:
                final, ctype, body = _open(u)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None, None
                err = str(e)
                if not _retryable(e):
                    break
            except Exception as e:
                err = str(e)
            else:
                if "text/html" in ctype or not final.startswith("https://code.claude.com/docs/ko/"):
                    return None, None  # 한국어판 없이 다른 주소(GitHub, claude.com)로 넘어감
                return body, None
            time.sleep(2 ** attempt)
        return None, err

    def work(p):
        body, err = one(p)
        p["ko"] = None
        if err:
            p["ko_error"] = err
        elif body is not None:
            m = re.search(r"^# (.+)\n\n> (.+)$", body, re.M)
            p["ko"] = {"title": m.group(1).strip() if m else p["title"],
                       "description": m.group(2).strip() if m else "", "content": body}

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(work, pages))


def korean_names(en_labels, ko_labels, en_tabs, ko_tabs, en_groups, ko_groups, en_subs, ko_subs, problems=None):
    """영어 메뉴 이름 -> 한국어 사이트가 쓰는 같은 자리의 이름. 탭·그룹·하위 그룹 이름을 번역 없이 공식 사이트에서 짝지어 얻는다.

    개수가 달라 짝짓지 못한 목록은 추측하지 않고 건너뛰며, 건너뛴 사실을 problems(리스트)에 문장으로 남긴다."""
    names = {}
    if len(en_tabs) == len(ko_tabs):
        names.update(zip(en_tabs, ko_tabs))
    elif problems is not None:
        problems.append(f"상단 탭: 영어 {len(en_tabs)}개, 한국어 {len(ko_tabs)}개라 짝짓지 못함")
    for kind, en_map, ko_map in (("그룹", en_groups, ko_groups), ("하위 그룹", en_subs, ko_subs)):  # 같은 탭의 첫 페이지에서 같은 순서로 나오는 이름끼리
        for tab, en_g in en_map.items():
            ko_g = ko_map.get(tab, [])
            if len(en_g) == len(ko_g):
                for a, b in zip(en_g, ko_g):
                    names.setdefault(a, b)
            elif problems is not None:
                problems.append(f"{tab} 탭의 {kind}: 영어 {len(en_g)}개, 한국어 {len(ko_g)}개라 짝짓지 못함")
    for key, en_name in en_labels.items():  # 같은 slug 의 메뉴 항목(하위 그룹 포함): en/X <-> ko/X
        ko_name = ko_labels.get("ko/" + key[3:])
        if ko_name:
            names.setdefault(en_name, ko_name)
    return {k: v for k, v in names.items() if k != v}


def _all_text(p):
    """에셋 수집용: 영어 본문과 (있으면) 한국어 본문."""
    return (p["content"] or "") + "\n" + ((p.get("ko") or {}).get("content") or "")


def download_assets(pages, assets_dir):
    """본문의 mintcdn 이미지·동영상을 받아 assets_dir 에 저장. 페이지에 {원격 URL: 'assets/파일'} 기록."""
    names = {}
    for p in pages:
        for u in ASSET_RE.findall(_all_text(p)):
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
        p["assets"] = {u: "assets/" + names[u] for u in dict.fromkeys(ASSET_RE.findall(_all_text(p)))
                       if u not in errors}
    return len(names), errors


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = argv[0] if argv else os.path.join(date.today().isoformat(), "docs.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    # 에셋 폴더: 두 번째 인자(예: 사이트의 assets/), 없으면 JSON 옆 assets/
    assets_dir = os.path.abspath(argv[1]) if len(argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(out)), "assets")

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
    fetch_korean(pages)
    en_labels, en_tabs, en_groups, en_subs, no_label, nav_order = add_nav_labels(pages)
    bad_nav = nav_health(pages, en_tabs, en_labels, nav_order)
    if bad_nav:
        raise RuntimeError("공식 사이트 메뉴 HTML 을 읽지 못했습니다(사이트 구조가 바뀐 듯함): " + "; ".join(bad_nav))
    ko_labels, ko_tabs, ko_groups, ko_subs, *_ = add_nav_labels(pages, "ko")
    nav_problems = []
    nav_names_ko = korean_names(en_labels, ko_labels, en_tabs, ko_tabs, en_groups, ko_groups, en_subs, ko_subs, nav_problems)
    n_assets, asset_errors = download_assets(pages, assets_dir)

    failed = [p["url"] for p in pages if p["content"] is None]
    ko_failed = {p["url"]: p["ko_error"] for p in pages if p.get("ko_error")}
    snapshot = {
        "source": INDEX_URL,
        "fetched_at": date.today().isoformat(),
        "page_count": len(pages),
        "languages": ["en", "ko"],  # ko = 공식 한국어판 원문(번역 아님). 한국어판이 없는 페이지는 p["ko"] 가 null
        "nav_names_ko": nav_names_ko,  # 영어 탭·그룹 이름 -> 한국어 사이트의 같은 이름
        "nav_order": nav_order,  # {탭: 공식 사이드바의 항목 순서}: 변환기가 형제 항목(페이지·하위 그룹)의 순서를 맞춘다
        "nav_name_mismatch": nav_problems,  # 개수가 달라 짝짓지 못한 메뉴 이름 목록 (있으면 한국어 메뉴에 영어 이름이 남음)
        "ko_errors": ko_failed,
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
    n_ko = sum(1 for p in pages if p.get("ko"))
    print(f"한국어판 {n_ko}개 수집, 없음(영어 원문 대체) {len(pages) - n_ko - len(ko_failed)}개, 실패 {len(ko_failed)}개, "
          f"탭·그룹 이름 {len(nav_names_ko)}개", file=sys.stderr)
    print(f"에셋 {n_assets}개 -> {assets_dir} (실패 {len(asset_errors)}개)", file=sys.stderr)
    for u in failed:
        print("  실패:", u, file=sys.stderr)
    for u, e in {**unresolved, **asset_errors}.items():
        print("  확인 필요:", u, "-", e, file=sys.stderr)
    for t in no_label:
        print("  메뉴 이름 없음:", t, file=sys.stderr)
    for msg in nav_problems:
        print("  경고: 한국어 메뉴 이름", msg, file=sys.stderr)
    for u, e in ko_failed.items():
        print("  한국어판 수집 실패:", u, "-", e, file=sys.stderr)
    for p in pages:
        if p.get("ko") is None and not p.get("ko_error"):
            print("  한국어판 없음:", slug(p["url"]), file=sys.stderr)


if __name__ == "__main__":
    setup_console()
    main()
