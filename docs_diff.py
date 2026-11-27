#!/usr/bin/env python3
"""보관된 docs.json(.gz) 두 개를 비교해 페이지별 unified diff 를 만듭니다.

사용법:  python docs_diff.py 이전 이후 [페이지slug]
         이전/이후는 docs.json, docs.json.gz 경로이거나 output/history 안의 날짜(YYYY-MM-DD)입니다.
         페이지 slug 는 영어판 en/hooks, 공식 한국어판 ko/hooks 처럼 언어 접두어를 붙입니다.
         예)  python docs_diff.py 2026-11-20 2026-11-27 ko/hooks
build_docs_snapshot.py 도 이 모듈의 diff_snapshots 로 매 빌드의 전체 diff 를 저장합니다. 표준 라이브러리만 사용.
"""
import difflib
import gzip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_HISTORY = os.path.join(HERE, "output", "history")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def open_json(path):
    """docs.json 또는 docs.json.gz(확장자로 구분)를 읽어 dict 로 돌려준다."""
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def page_key(page):
    return page["url"].split("/docs/", 1)[1].removesuffix(".md")


def texts(snap, with_ko=True):
    """스냅샷의 {'en/slug': 본문, 'ko/slug': 한국어 본문}. 한국어판이 없는 페이지는 ko/ 항목이 없다."""
    out = {}
    for p in snap["pages"]:
        key = page_key(p)
        out[key] = p["content"] or ""
        k = p.get("ko")
        if with_ko and k:
            out["ko/" + key.split("/", 1)[1]] = k["content"] or ""
    return out


def diff_snapshots(old, new, only=None):
    """두 스냅샷(dict)의 바뀐 페이지를 unified diff 문자열 목록으로 돌려준다. only 가 있으면 그 slug 만.

    한국어(ko/)는 두 스냅샷에 모두 한국어 데이터가 있을 때만 비교한다 (한국어 수집 이전의 옛 이력과는 영어만 비교).
    """
    both_ko = any(p.get("ko") for p in old["pages"]) and any(p.get("ko") for p in new["pages"])
    old_t, new_t = texts(old, both_ko), texts(new, both_ko)
    chunks = []
    for key in sorted(old_t.keys() | new_t.keys()):
        if only and key != only:
            continue
        a, b = old_t.get(key, ""), new_t.get(key, "")
        if a == b and (key in old_t) == (key in new_t):
            continue
        label = "(새 페이지)" if key not in old_t else "(삭제된 페이지)" if key not in new_t else ""
        lines = list(difflib.unified_diff(
            a.splitlines(), b.splitlines(), fromfile=f"{old.get('fetched_at', '?')}/{key}",
            tofile=f"{new.get('fetched_at', '?')}/{key}", lineterm="", n=2))
        chunks.append(f"=== {key} {label}".rstrip() + "\n" + "\n".join(lines) + "\n")
    return chunks


def resolve(arg, history_dir=DEFAULT_HISTORY):
    """날짜(YYYY-MM-DD)면 history 안의 파일 경로로, 아니면 그대로 경로로 취급한다."""
    if DATE_RE.match(arg):
        path = os.path.join(history_dir, arg + ".json.gz")
        if not os.path.exists(path):
            raise SystemExit(f"보관된 이력이 없습니다: {path}")
        return path
    return arg


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2:
        print(__doc__)
        return 2
    old, new = open_json(resolve(argv[0])), open_json(resolve(argv[1]))
    chunks = diff_snapshots(old, new, argv[2] if len(argv) > 2 else None)
    print("\n".join(chunks) if chunks else "변경된 페이지가 없습니다.")
    return 0


if __name__ == "__main__":
    from docs_common import setup_console
    setup_console()
    sys.exit(main())
