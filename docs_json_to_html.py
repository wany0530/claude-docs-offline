#!/usr/bin/env python3
"""docs_fetch_json.py 가 만든 JSON 을 오프라인에서 바로 열어볼 수 있는 정적 HTML 사이트로 변환합니다.

사용법:  python docs_json_to_html.py 입력.json[.gz] [출력폴더 [에셋 원본 폴더]]   (기본 출력: 입력 JSON 옆의 site/)
결과:    출력폴더/index.html          영어 첫 페이지로 이동하는 바로가기
         출력폴더/en/....html, ko/....html   페이지별 HTML (영어판, 공식 한국어판. 원문 주소 구조 그대로)
         출력폴더/assets/             이미지·동영상 (이미 있으면 복사하지 않음)
         출력폴더/style.css, nav.js   공식 사이트 같은 레이아웃·탭·사이드바·구문 강조·검색 (서버 없이 file:// 로 동작)
         출력폴더/nav-data-{en,ko}.js, search-data-{en,ko}.js   메뉴 트리, 본문 검색 색인 (처음 검색할 때만 불러옴)
본문 마크다운 -> HTML 변환기를 직접 구현했고, docs 사이트 내부 링크는 상대 경로로 바꿉니다. 한국어는 번역이 아니라
공식 한국어판(/docs/ko/) 원문입니다. 표준 라이브러리만 사용.
"""
import collections
import json
import os
import shutil
import sys

import docs_diff
from docs_anchors import REPORT, compare_ledger, load_ledger, resolve_anchors
from docs_changes import changes_markdown
from docs_common import ko_url, norm, setup_console
from docs_markdown import Renderer, attr, esc, plain_text, strip_banner
from docs_site import (CSS, ICON_COPY, ICON_SEARCH, JS, JS_UI_KEYS, LANGS, PAGE, UI_TEXT, build_nav, crumb_of,
                       make_targets, rest_of, view, write_text)


def main(argv=None, changes=None):
    """argv: 입력.json(.gz) [출력폴더] [에셋 원본 폴더]. 출력폴더에 assets/ 가 이미 있으면 에셋은 복사하지 않는다.

    changes: docs_changes.change_data 결과. 주면 en/changes.html, ko/changes.html 을 만들고 모든 페이지 하단에서 링크한다."""
    argv = sys.argv[1:] if argv is None else argv
    src = argv[0]
    out = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(src)), "site")
    snap = docs_diff.open_json(src)
    pages = snap["pages"]
    assert all(p["content"] is not None for p in pages), "content 가 없는 페이지가 있습니다 (fetch 실패)"
    names_ko = snap.get("nav_names_ko", {})
    redirects = snap.get("redirects", {})

    os.makedirs(out, exist_ok=True)
    out_assets = os.path.join(out, "assets")
    if not os.path.isdir(out_assets):  # 수집기가 사이트의 assets/ 에 바로 저장했다면 복사할 필요 없음
        assets_src = argv[2] if len(argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(src)), snap.get("assets_dir", ""))
        if snap.get("assets_dir") and os.path.isdir(assets_src):
            shutil.copytree(assets_src, out_assets)

    targets = {lang: make_targets(pages, redirects, lang) for lang in LANGS}
    page_ids, page_links, search = {}, [], {lang: [] for lang in LANGS}
    n_fallback = hint_full = hint_total = acc_full = acc_total = 0
    rendered = []  # (페이지, 언어, slug, 제목, 본문 원문, 대체 여부, 렌더러, 본문 HTML) — 모든 페이지의 id 가 정해진 뒤 앵커를 확정한다
    for p in pages:
        rest = rest_of(p)
        en_head_ids = en_acc_ids = None
        for lang in LANGS:  # en 을 먼저 렌더링해 헤딩·아코디언 id 를 한국어판이 빌려 쓴다
            title, content, _, fallback = view(p, lang)
            use_hint = lang == "ko" and not fallback and en_head_ids is not None
            slug = f"{lang}/{rest}"
            r = Renderer(slug, targets[lang], p.get("assets", {}), hint=en_head_ids if use_hint else None,
                         acc_hint=en_acc_ids if use_hint else None, defer_anchors=True)
            body = r.render(content)
            if lang == "en":
                en_head_ids, en_acc_ids = r.head_ids, r.acc_ids
            elif use_hint:
                hint_total += 1
                hint_full += r.hint is not None and r.hint_pos == len(en_head_ids) == len(r.head_ids)
                if en_acc_ids or r.acc_ids:
                    acc_total += 1
                    acc_full += r.acc_pos == len(en_acc_ids) == len(r.acc_ids)
            n_fallback += fallback
            page_ids[slug] = r.used_ids
            page_links += [(slug, t, f) for t, f in r.links]
            search[lang].append({"t": title, "p": slug + ".html", "h": [list(h) for h in r.heads if h[0]],
                                 "x": plain_text(content)})
            rendered.append((p, lang, slug, title, content, fallback, r, body))

    def emit(lang, slug, rest, title, body, md_text, crumbs, notice, url):
        """페이지 틀(PAGE)에 채워 <출력폴더>/<slug>.html 로 쓴다. 일반 페이지와 변경 내역 페이지가 함께 쓴다."""
        ui = UI_TEXT[lang]
        root = "../" * slug.count("/")
        md = json.dumps(md_text, ensure_ascii=False).replace("<", "\\u003c")
        link = f' &middot; <a href="{root}{lang}/changes.html">{esc(ui["changes"])}</a>' if changes and slug != f"{lang}/changes" else ""
        write_text(os.path.join(out, *(slug + ".html").split("/")), PAGE.substitute(
            lang=lang, title=esc(title), root=root, slug=slug, body=body, md=md, crumbs=crumbs, notice=notice,
            en_href=f"{root}en/{rest}.html", ko_href=f"{root}ko/{rest}.html", url=attr(url),
            fetched=snap.get("fetched_at", ""), changes_link=link, icon_search=ICON_SEARCH, icon_copy=ICON_COPY,
            t_lang=ui["lang_name"], t_toggle=ui["toggle"], t_search=ui["search"], t_copy_page=ui["copy_page"],
            t_skip=ui["skip"], t_sections=ui["sections"], t_pages=ui["pages"], t_toc=ui["toc"],
            t_source=ui["source"], t_snapshot=ui["snapshot"]))

    report = {"counts": collections.Counter(), "key": set(), "strict": set(), "stale": set(), "hint": set()}
    for p, lang, slug, title, content, fallback, r, body in rendered:
        ui = UI_TEXT[lang]
        body = resolve_anchors(slug, body, r.links, page_ids, ui["stale"], report)
        url = norm(p["url"] if lang == "en" or fallback else ko_url(p["url"]))
        emit(lang, slug, rest_of(p), title, body, "\n".join(strip_banner(content)), esc(crumb_of(p, lang, names_ko)),
             f'<div class="notice">{esc(ui["fallback"])}</div>\n' if fallback else "", url)

    if changes:  # 직전 이력과 비교한 '변경 내역' 페이지 (사이드바·검색 색인에는 넣지 않는다)
        assert all(rest_of(p) != "changes" for p in pages), "'changes' 라는 문서 페이지가 있어 변경 내역 페이지와 겹칩니다"
        for lang in LANGS:
            md_text = changes_markdown(changes, lang)
            body = Renderer(f"{lang}/changes", targets[lang], {}).render(md_text)
            emit(lang, f"{lang}/changes", "changes", UI_TEXT[lang]["changes"], body, md_text, "", "", "https://code.claude.com/docs")

    for lang in LANGS:
        ui = {k: UI_TEXT[lang][k] for k in JS_UI_KEYS}
        write_text(os.path.join(out, f"nav-data-{lang}.js"),
                   "window.DOCS_NAV=" + json.dumps({"tabs": build_nav(pages, lang, names_ko, snap.get("nav_order"))}, ensure_ascii=False)
                   + ";\nwindow.DOCS_UI=" + json.dumps(ui, ensure_ascii=False) + ";\n")
        write_text(os.path.join(out, f"search-data-{lang}.js"),  # 첫 검색 때 지연 로드
                   "window.DOCS_SEARCH=" + json.dumps(search[lang], ensure_ascii=False, separators=(",", ":")) + ";\n")
    write_text(os.path.join(out, "style.css"), CSS)
    write_text(os.path.join(out, "nav.js"), JS)
    home = f"en/{rest_of(pages[0])}.html"  # 목차 맨 앞 페이지 (Overview)
    write_text(os.path.join(out, "index.html"),
               f'<!doctype html><meta charset="utf-8"><title>Claude Code Docs (offline)</title>'
               f'<meta http-equiv="refresh" content="0; url={home}"><a href="{home}">{home}</a>\n')

    # self-check: 변환된 내부 링크가 가리키는 파일이 실제로 있는지. 앵커는 위 resolve_anchors 가 확정했다
    missing_files = [(s, t) for s, t, _ in page_links if not os.path.isfile(os.path.join(out, *(t + ".html").split("/")))]
    n_ko = sum(1 for p in pages if p.get("ko"))
    c = report["counts"]
    stale = sorted(report["stale"])
    unreviewed, changed = compare_ledger(report["strict"], load_ledger())
    REPORT.clear()
    REPORT.update(counts=dict(c), strict=sorted(report["strict"]), stale=stale, missing_files=len(missing_files),
                  ko_heading_full=(hint_full, hint_total), ko_accordion_full=(acc_full, acc_total),
                  unreviewed=unreviewed, ledger_changed=changed, hints=sorted(report["hint"]))
    print(f"페이지 {len(pages)}개 x 2개 언어 (한국어판 {n_ko}개, 영어 원문 대체 {n_fallback}개) -> {out}", file=sys.stderr)
    print(f"한국어 id 빌려 쓰기: 헤딩 {hint_full}/{hint_total}페이지, 아코디언 {acc_full}/{acc_total}페이지가 영어판과 완전히 일치",
          file=sys.stderr)
    print(f"내부 링크 {len(page_links)}개 변환, 없는 파일 {len(missing_files)}개", file=sys.stderr)
    print(f"앵커 확정 {sum(c.values())}건: 그대로 {c['exact']}, 대소문자·구두점 보정 {c['key']}, 단어 일치 보정 {c['strict']}, "
          f"원문에서 사라져 페이지 처음으로 연결 {c['stale']} (고유 {len(stale)}건: "
          f"en {sum(s.startswith('en/') for s, *_ in stale)}, ko {sum(s.startswith('ko/') for s, *_ in stale)})", file=sys.stderr)
    print(f"검토 장부 대조: 장부에 없는 새 보정 {len(unreviewed)}건, 장부와 다르게 보정된 것 {len(changed)}건", file=sys.stderr)
    for k, got in unreviewed[:10]:
        print(f"  검토 필요(새 보정): {k} -> #{got}", file=sys.stderr)
    for k, want, got in changed[:10]:
        print(f"  검토 필요(장부와 다름): {k} 장부 #{want} / 이번 #{got}", file=sys.stderr)
    for s, t, f, _ in stale[:10]:
        print(f"  앵커 없음(페이지 처음으로): {s} -> {t}#{f}", file=sys.stderr)
    return len(missing_files)


if __name__ == "__main__":
    setup_console()
    sys.exit(1 if main() else 0)
