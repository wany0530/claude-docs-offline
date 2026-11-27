#!/usr/bin/env python3
"""보관된 docs.json(.gz) 두 개를 비교해 페이지별 unified diff 를 만듭니다.

사용법:  python docs_diff.py 이전 이후 [페이지slug]
         이전/이후는 docs.json, docs.json.gz 경로이거나 output/history 안의 날짜(YYYY-MM-DD)입니다.
         예)  python docs_diff.py 2026-11-20 2026-11-27 en/hooks
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


def diff_snapshots(old, new, only=None):
    """두 스냅샷(dict)의 바뀐 페이지를 unified diff 문자열 목록으로 돌려준다. only 가 있으면 그 slug 만."""
    old_p = {page_key(p): p for p in old["pages"]}
    new_p = {page_key(p): p for p in new["pages"]}
    chunks = []
    for key in sorted(old_p.keys() | new_p.keys()):
        if only and key != only:
            continue
        a = (old_p[key]["content"] or "") if key in old_p else ""
        b = (new_p[key]["content"] or "") if key in new_p else ""
        if a == b:
            continue
        label = "(새 페이지)" if key not in old_p else "(삭제된 페이지)" if key not in new_p else ""
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
