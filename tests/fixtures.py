"""테스트 공용 도우미: 작은 docs.json 스냅샷을 만들고 변환기로 사이트를 만든다. 네트워크 없음.

단위 테스트(test_site, test_run)와 브라우저 E2E 의 고정 사이트(tests/e2e/build_fixture.py)가 함께 쓴다.
"""
import gzip
import json
import os

import _path  # noqa: F401

EN = "https://code.claude.com/docs/en/"


def page(slug, title, content, category=("Docs", "x", "Group"), ko=None, description=""):
    """수집기가 만드는 페이지 1개와 같은 모양. ko 는 (제목, 본문) 또는 None(공식 한국어판 없음)."""
    p = {"category": list(category), "title": title, "url": f"{EN}{slug}.md",
         "description": description, "content": content, "assets": {}}
    p["ko"] = ({"title": ko[0], "description": "", "content": ko[1], "nav_label": ko[0]} if ko else None)
    return p


def snapshot(pages, **extra):
    return {"source": "s", "fetched_at": "2026-01-01", "redirects": {}, "pages": pages, **extra}


def write_snapshot(path, pages, **extra):
    """docs.json 을 path 에 쓴다 (.gz 로 끝나면 압축)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "wt", encoding="utf-8") as f:
        json.dump(snapshot(pages, **extra), f, ensure_ascii=False)
    return path


def build_site(pages, out_dir, work_dir, gz=False, changes=None, **extra):
    """pages 로 변환기를 끝까지 돌려 out_dir 에 사이트를 만든다. (없는 파일 링크 수)를 돌려준다."""
    import docs_json_to_html as conv
    src = write_snapshot(os.path.join(work_dir, "docs.json.gz" if gz else "docs.json"), pages, **extra)
    return conv.main([src, out_dir], changes=changes)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def tree(path):
    """폴더 안 모든 파일의 {상대 경로: 내용 바이트}. 폴더가 그대로인지 바이트 단위로 비교할 때 쓴다."""
    out = {}
    for dp, _, fn in os.walk(path):
        for name in fn:
            full = os.path.join(dp, name)
            with open(full, "rb") as f:
                out[os.path.relpath(full, path).replace(os.sep, "/")] = f.read()
    return out
