"""사이트 부품: 화면 문구, 메뉴 트리, 주소 표, 그리고 site_src/ 의 CSS·JS·HTML 틀.

CSS, JS, HTML 틀은 site_src/ 의 실제 파일이다 (파이썬 문자열 상수가 아님). 이 모듈이 읽어서 쓴다.
"""
import os

from string import Template

from docsnap.common import ko_url, norm, slug as url_slug

SITE_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "site_src")
JS_PARTS = ("lib.js", "app.js", "search.js", "highlight.js")  # 순서대로 이어 붙여 site/nav.js 가 된다 (lib.js 가 DocsLib 를 먼저 정의)


def read_src(name):
    with open(os.path.join(SITE_SRC, name), encoding="utf-8") as f:
        return f.read()


CSS = read_src("style.css")
JS = "\n".join(read_src(n) for n in JS_PARTS)
PAGE = Template(read_src("page.html"))  # $이름 자리 채우기 (CSS·JS 와 달리 중괄호 걱정이 없다)

# ---------- 사이트 구성 ----------
LANGS = ("en", "ko")

# 화면(UI) 문구. 문서 본문 번역이 아니라 검색창·버튼 같은 사이트 부품의 글자다. 본문은 항상 공식 원문을 쓴다.
UI_TEXT = {
    "en": {"lang_name": "English", "search": "Search...", "filter": "Filter pages...", "toggle": "Toggle navigation",
           "copy_page": "Copy page", "copied": "Copied", "copy": "Copy", "snapshot": "snapshot", "source": "Source",
           "loading": "Loading search index...", "no_index": "Search index not found.",
           "n_match": "{n} page(s) match", "none": "No page contains all words",
           "fallback": "There is no official Korean version of this page, so the original English text is shown.",
           "close": "Close", "toc": "On this page", "skip": "Skip to content", "sections": "Sections", "pages": "Pages", "changes": "What changed",
           "stale": "The section this link pointed to no longer exists in the source docs; it opens the top of the page."},
    "ko": {"lang_name": "한국어", "search": "검색...", "filter": "페이지 필터...", "toggle": "메뉴 열기",
           "copy_page": "페이지 복사", "copied": "복사됨", "copy": "복사", "snapshot": "스냅샷", "source": "원문",
           "loading": "검색 색인을 불러오는 중...", "no_index": "검색 색인을 찾을 수 없습니다.",
           "n_match": "{n}개 페이지 일치", "none": "모든 단어를 포함한 페이지가 없습니다",
           "fallback": "이 페이지는 공식 한국어판이 없어 영어 원문을 표시합니다.",
           "close": "닫기", "toc": "이 페이지에서", "skip": "본문으로 건너뛰기", "sections": "섹션", "pages": "페이지", "changes": "변경 내역",
           "stale": "이 링크가 가리키던 섹션이 공식 문서에서 이름이 바뀌었거나 사라져, 페이지 처음으로 이동합니다."},
}
JS_UI_KEYS = ("filter", "copied", "copy", "loading", "no_index", "n_match", "none", "search", "close", "toc")


class Group:
    def __init__(self, name, display=None):
        self.name, self.display, self.children, self.idx = name, display or name, [], {}

    def sub(self, name, display=None):
        g = self.idx.get(name)
        if g is None:
            g = self.idx[name] = Group(name, display)
            self.children.append(g)
        return g

    def to_json(self):
        return {"g": self.display,
                "c": [c.to_json() if isinstance(c, Group) else {"t": c[0], "p": c[1]} for c in self.children]}


def rest_of(page):
    """페이지의 언어 접두어 없는 경로. 'https://code.claude.com/docs/en/agent-sdk/mcp.md' -> 'agent-sdk/mcp'"""
    s = url_slug(page["url"])
    if not s.startswith("en/"):
        raise ValueError("영어 문서 주소가 아닙니다: " + page["url"])
    return s[3:]


def view(page, lang):
    """페이지의 lang 판 (제목, 본문, 메뉴 이름, 한국어판이 없어 영어로 대체했는지). 한국어는 공식 /docs/ko/ 원문이다."""
    k = page.get("ko") if lang == "ko" else None
    if k:
        return k["title"], k["content"], k.get("nav_label") or k["title"], False
    return page["title"], page["content"], page.get("nav_label") or page["title"], lang == "ko"


def make_targets(pages, redirects, lang):
    """docs 주소(영어·한국어 모두) -> 이 언어 사이트 안의 slug. 한국어판이 없는 페이지도 ko/ 쪽에 영어 원문으로 만들어 둔다."""
    by_norm = {norm(p["url"]): p for p in pages}
    t = {}
    for p in pages:
        dest = f"{lang}/{rest_of(p)}"
        t[norm(p["url"])] = dest
        t[norm(ko_url(p["url"]))] = dest
    for old, new in redirects.items():
        p = by_norm.get(norm(new))
        if p:
            dest = f"{lang}/{rest_of(p)}"
            t[norm(old)] = dest
            t[norm(ko_url(old))] = dest
    return t


def rank_nav(root, events, lang):
    """공식 사이드바의 항목 순서(events=[[종류, 이름], ...], 수집기의 parse_nav 결과)에 맞춰 root 아래 형제 항목을 재배열한다.

    공식 사이트는 일반 페이지와 하위 그룹을 섞어 나열하지만 llms.txt 는 하위 그룹을 뒤로 모은다. 순서에 없는 항목(접힌
    하위 그룹 안의 페이지, 숨은 페이지)은 llms.txt 에서 바로 앞에 있던 형제 바로 뒤에 둔다. 항목이 하나도 맞지 않으면 순서는 그대로다."""
    pages, groups = {}, {}
    for i, (kind, name) in enumerate(events):
        if kind == "p":
            pages.setdefault(name.split("/", 1)[-1], i)  # 'en/x' -> 'x' (두 언어가 같은 순서를 쓴다)
        else:
            groups.setdefault(name, []).append(i)  # 같은 이름이 여러 곳에 있으면 부모 헤더 뒤의 첫 것을 쓴다

    def own_rank(child, parent_rank):
        if isinstance(child, Group):
            return next((i for i in groups.get(child.name, []) if i > parent_rank), None)
        return pages.get(child[1][len(lang) + 1:-len(".html")])

    def sort(group, parent_rank):
        keyed, prev = [], parent_rank
        for child in group.children:
            r = own_rank(child, parent_rank)
            key = float(r) if r is not None else prev + 0.5
            keyed.append((key, child))
            prev = key
        keyed.sort(key=lambda t: t[0])  # 안정 정렬
        group.children = [c for _, c in keyed]
        for key, child in keyed:
            if isinstance(child, Group):
                sort(child, key)

    sort(root, -1)


def build_nav(pages, lang, names, order=None):
    """상단 탭 -> 사이드바 그룹 -> 페이지 트리. 탭·그룹 이름은 한국어 공식 사이트의 같은 자리 이름(names)을 쓴다.

    order: {탭 영어 이름: 공식 사이드바 항목 순서} (docs.json 의 nav_order). 없으면 llms.txt 순서 그대로."""
    tr = (lambda n: names.get(n, n)) if lang == "ko" else (lambda n: n)
    tabs = {}
    for p in pages:
        cat = p["category"]
        hidden = cat[0] == "_unlisted"
        root = tabs.get(cat[0])
        if root is None:
            root = tabs[cat[0]] = Group(cat[0], "Unlisted" if hidden else tr(cat[0]))
            root.hidden = hidden
        g = root
        for f in cat[2:]:  # cat[1] 은 llms.txt 의 사이드바 구역 이름이라 대분류와 겹쳐 생략
            g = g.sub(f, tr(f))
        g.children.append((view(p, lang)[2], f"{lang}/{rest_of(p)}.html"))
    for r in tabs.values():
        if order and order.get(r.name):
            rank_nav(r, order[r.name], lang)
    return [{"n": r.display, "hidden": r.hidden, "c": r.to_json()["c"]} for r in tabs.values()]


def crumb_of(page, lang, names):
    cat = page["category"]
    name = "Unlisted" if cat[0] == "_unlisted" else cat[2] if len(cat) > 2 else cat[0]
    return names.get(name, name) if lang == "ko" else name


ICON_SEARCH = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
               'stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>')
ICON_COPY = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8" y="3" width="8" height="4" rx="1"/>'
             '<path d="M16 5h2a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2"/></svg>')


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
