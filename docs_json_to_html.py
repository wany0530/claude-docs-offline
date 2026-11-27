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
import html
import json
import os
import re
import shutil
import sys
import urllib.parse
from posixpath import dirname as pdirname, relpath as prelpath

import docs_diff
from docs_common import ko_url, norm, setup_console, slug as url_slug

ALLOWED_TAGS = {
    "a", "b", "i", "u", "em", "strong", "code", "kbd", "sub", "sup", "br", "span", "img", "video", "source",
    "details", "summary", "div", "p", "table", "thead", "tbody", "tr", "th", "td", "ul", "ol", "li", "hr",
}
BLOCK_HTML = {"video", "img", "div", "details", "summary", "table", "iframe", "p", "ul", "ol", "hr",
              "thead", "tbody", "tfoot", "tr", "th", "td", "caption"}

FENCE = re.compile(r"^( {0,3})(`{3,}|~{3,})\s*(.*)$")
HEAD = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
HR = re.compile(r"^ {0,3}([-*_])(?:\s*\1){2,}\s*$")
ITEM = re.compile(r"^( *)([-*+]|\d{1,9}[.)])(?:\s+(.*))?$")
QUOTE = re.compile(r"^ {0,3}>")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
HTML_START = re.compile(r"^\s*<(/?)([a-zA-Z][\w-]*)\b|^\s*<!--")
TAG = re.compile(r"</?([a-zA-Z][\w-]*)((?:\s[^<>]*?)?)\s*/?>")
URL_ATTR = re.compile(r'\b(src|href|poster)="([^"]*)"')
CODE_SPAN = re.compile(r"(?<![\\`])(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.S)
IMAGE = re.compile(r'!\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+"([^"]*)")?\s*\)')
LINK = re.compile(r'\[((?:[^\[\]]|\[[^\]]*\])*)\]\(\s*([^)\s]+)(?:\s+"([^"]*)")?\s*\)')
BARE_URL = re.compile(r"(?<![\w/@=\"'>\x00])(https?://[^\s<>\x00]+)")
ESCAPED = re.compile(r"\\([!-/:-@\[-`{-~])")
STRONG = [re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S), re.compile(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)", re.S)]
EM = [re.compile(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])", re.S),
      re.compile(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)", re.S)]
DEL = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~", re.S)
MARKER = re.compile(r"^\[(tab|accordion|card)\](?:[ \t]+(.*))?$")  # Mintlify 컴포넌트: > [tab] 이름 / > [accordion] 제목 / > [card] [제목](주소)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def esc_text(s):  # 이미 있는 &entity; 는 보존
    return re.sub(r"&(?!#?\w+;)", "&amp;", s).replace("<", "&lt;").replace(">", "&gt;")


def attr(s):
    return html.escape(s, quote=True)


def heading_slug(text):
    text = re.sub(r"<[^>]+>", "", html.unescape(text)).strip().lower()
    return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", text))


def anchor_key(s):  # 앵커 비교용: URL 디코딩 + 소문자 + 영숫자만 (nav.js 의 anchorKey 와 같은 규칙)
    return re.sub(r"[\W_]", "", urllib.parse.unquote(s).lower())


def strip_banner(content):
    """모든 페이지 맨 위의 'Documentation Index' 안내문(> 로 시작하는 줄들)을 뺀 본문 줄 목록."""
    lines = content.replace("\r\n", "\n").split("\n")
    if lines and lines[0].startswith("> ## Documentation Index"):
        while lines and (lines[0].startswith(">") or not lines[0].strip()):
            lines.pop(0)
    return lines


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


class Renderer:
    """페이지 1개를 HTML 로 변환. slug 는 'en/agent-sdk/mcp' 형태."""

    def __init__(self, slug, targets, assets, hint=None):
        """hint: 같은 페이지 다른 언어판의 [(헤딩 레벨, id), ...]. 주면 헤딩 id 를 그대로 빌려 쓴다
        (공식 한국어판 본문의 링크도 영어판 앵커를 쓰기 때문). 레벨이 어긋나면 그 지점부터는 기본 규칙으로 돌아간다."""
        self.slug, self.targets = slug, targets
        self.assets = {k.replace("\\&", "&"): v for k, v in assets.items()}
        self.ids, self.used_ids = {}, set()
        self.links = []  # (대상 slug, 앵커) — 나중에 앵커 검사용
        self.heads = []  # (헤딩 글자, id) — 본문 검색 결과에서 해당 위치로 이동하기 위함
        self.head_ids = []  # (헤딩 레벨, id) — 다른 언어판이 id 를 빌려 가기 위함
        self.hint, self.hint_pos, self.tab_n, self.lead_done = (list(hint) if hint else None), 0, 0, False

    # ---------- 주소 ----------
    def rel(self, path):
        return prelpath(path, pdirname(self.slug + ".html") or ".")

    def fix_url(self, url):
        u = html.unescape(url).replace("\\&", "&")
        if u in self.assets:
            return self.rel(self.assets[u])
        m = re.match(r"(https://code\.claude\.com/docs/[^#?]*)(?:\?[^#]*)?(#.*)?$", u)
        if m:
            target = self.targets.get(norm(m.group(1)))
            if target:
                self.links.append((target, (m.group(2) or "")[1:]))
                return self.rel(target + ".html") + (m.group(2) or "")
        return u

    # ---------- 인라인 ----------
    def inline(self, text):
        text = text.replace("\x00", "")
        st = []

        def stash(h):
            st.append(h)
            return f"\x00{len(st) - 1}\x00"

        def code(m):
            body = m.group(2)
            if len(body) > 1 and body[0] == body[-1] == " " and body.strip():
                body = body[1:-1]
            return stash("<code>" + esc(body.replace("\n", " ")) + "</code>")

        text = CODE_SPAN.sub(code, text)
        text = re.sub(r"\\([<>])", lambda m: stash(esc(m.group(1))), text)  # \< \> 는 글자 그대로 (태그 처리·esc_text 전에)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        text = re.sub(r"<(https?://[^\s>]+)>",
                      lambda m: stash(f'<a href="{attr(self.fix_url(m.group(1)))}">{esc(m.group(1))}</a>'), text)

        def tag(m):
            if m.group(1).lower() not in ALLOWED_TAGS:
                return m.group(0)  # 허용 목록 밖: 아래 esc_text 에서 글자 그대로 표시됨
            raw = URL_ATTR.sub(lambda a: f'{a.group(1)}="{attr(self.fix_url(a.group(2)))}"', m.group(0))
            return stash(raw)

        text = TAG.sub(tag, text)
        text = esc_text(text)
        text = IMAGE.sub(lambda m: stash(
            f'<img src="{attr(self.fix_url(m.group(2)))}" alt="{attr(html.unescape(m.group(1)))}" loading="lazy">'), text)
        text = LINK.sub(lambda m: stash(f'<a href="{attr(self.fix_url(m.group(2)))}">') + m.group(1) + stash("</a>"), text)
        text = re.sub(r"\\\n", lambda m: stash("<br>\n"), text)
        text = ESCAPED.sub(lambda m: stash(esc(m.group(1))), text)

        def bare(m):
            url = m.group(1)
            tail = re.search(r"[.,;:!?)*_]+$|&amp;$", url)
            tail = tail.group(0) if tail else ""
            url = url[: len(url) - len(tail)]
            return stash(f'<a href="{attr(self.fix_url(url))}">{url}</a>') + tail

        text = BARE_URL.sub(bare, text)
        for r in STRONG:
            text = r.sub(r"<strong>\1</strong>", text)
        for r in EM:
            text = r.sub(r"<em>\1</em>", text)
        text = DEL.sub(r"<del>\1</del>", text)
        text = re.sub(r" {2,}\n", "<br>\n", text)
        while "\x00" in text:
            text = re.sub(r"\x00(\d+)\x00", lambda m: st[int(m.group(1))], text)
        return text

    # ---------- 블록 ----------
    def heading_id(self, text, level=0):
        if self.hint is not None:
            if self.hint_pos < len(self.hint) and self.hint[self.hint_pos][0] == level:
                hid = self.hint[self.hint_pos][1]
                self.hint_pos += 1
                self.used_ids.add(hid)
                self.head_ids.append((level, hid))
                return hid
            self.hint = None  # 어긋남: 나머지는 기본 규칙
        base = heading_slug(text) or "section"
        n = self.ids.get(base, -1) + 1
        self.ids[base] = n
        hid = base if n == 0 else f"{base}-{n}"
        self.used_ids.add(hid)
        self.head_ids.append((level, hid))
        return hid

    def tab_group(self, tabs):
        """[(이름, 본문 줄들), ...] -> 탭 UI. 첫 탭이 열려 있고 버튼으로 전환한다 (nav.js)."""
        self.tab_n += 1
        gid = f"tab{self.tab_n}"
        btns = "".join(
            f'<button type="button" class="tab-btn{" active" if k == 0 else ""}" role="tab" '
            f'aria-selected="{"true" if k == 0 else "false"}" data-tab="{gid}-{k}">{self.inline(name)}</button>'
            for k, (name, _) in enumerate(tabs))
        panels = "".join(f'<div class="tab-panel{" active" if k == 0 else ""}" role="tabpanel" id="{gid}-{k}">'
                         f"{self.blocks(body)}</div>" for k, (_, body) in enumerate(tabs))
        return f'<div class="tabs"><div class="tab-list" role="tablist">{btns}</div>{panels}</div>'

    @staticmethod
    def quote_run(lines, i):
        """lines[i] 부터 이어지는 > 인용 줄들을 접두어를 떼어 모으고 (줄 목록, 다음 위치)를 돌려준다."""
        inner = []
        while i < len(lines) and QUOTE.match(lines[i]):
            inner.append(re.sub(r"^ {0,3}> ?", "", lines[i]))
            i += 1
        return inner, i

    def next_marked(self, lines, i, kind):
        """빈 줄만 건너뛴 뒤 같은 종류(kind)의 [tab]/[card] 인용이 이어지면 (이름, 본문, 다음 위치), 아니면 None."""
        j = i
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and QUOTE.match(lines[j]):
            inner, k = self.quote_run(lines, j)
            m = MARKER.match(inner[0]) if inner else None
            if m and m.group(1) == kind:
                return m.group(2) or "", inner[1:], k
        return None

    def starts_block(self, lines, i, in_paragraph=False):
        line = lines[i]
        if FENCE.match(line) or HEAD.match(line) or HR.match(line) or QUOTE.match(line):
            return True
        m = ITEM.match(line)
        if m and (not in_paragraph or m.group(2) in "-*+" or m.group(2)[:-1] == "1"):
            return True
        if "|" in line and i + 1 < len(lines) and "|" in lines[i + 1] and TABLE_SEP.match(lines[i + 1]):
            return True
        h = HTML_START.match(line)
        return bool(h and (line.lstrip().startswith("<!--") or h.group(2).lower() in BLOCK_HTML))

    @staticmethod
    def split_row(line):
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|") and not line.endswith("\\|"):
            line = line[:-1]
        return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line)]

    def table(self, lines, i):
        head = self.split_row(lines[i])
        aligns = []
        for c in self.split_row(lines[i + 1]):
            aligns.append("center" if c.startswith(":") and c.endswith(":") else "right" if c.endswith(":")
                          else "left" if c.startswith(":") else "")
        i += 2
        rows = []
        while i < len(lines) and lines[i].strip() and "|" in lines[i]:
            rows.append(self.split_row(lines[i]))
            i += 1

        def cell(tag, text, k):
            a = f' style="text-align:{aligns[k]}"' if k < len(aligns) and aligns[k] else ""
            return f"<{tag}{a}>{self.inline(text)}</{tag}>"

        out = ["<div class=\"table-wrap\"><table><thead><tr>"]
        out += [cell("th", c, k) for k, c in enumerate(head)]
        out.append("</tr></thead><tbody>")
        for r in rows:
            out.append("<tr>" + "".join(cell("td", c, k) for k, c in enumerate(r)) + "</tr>")
        out.append("</tbody></table></div>")
        return "".join(out), i

    def list_block(self, lines, i):
        first = ITEM.match(lines[i])
        ind, ordered = len(first.group(1)), first.group(2)[0].isdigit()
        start = int(first.group(2)[:-1]) if ordered else 1
        items, loose, n = [], False, len(lines)
        while i < n:
            m = ITEM.match(lines[i])
            if not m or len(m.group(1)) != ind or m.group(2)[0].isdigit() != ordered or HR.match(lines[i]):
                break
            body, j = [m.group(3) or ""], i + 1
            while j < n:
                l = lines[j]
                if not l.strip():
                    k = j
                    while k < n and not lines[k].strip():
                        k += 1
                    if k < n and indent_of(lines[k]) > ind:
                        body.append("")
                        j += 1
                        continue
                    break
                if indent_of(l) > ind:
                    body.append(l)
                    j += 1
                else:
                    break
            cont = [l for l in body[1:] if l.strip()]
            cut = min((indent_of(l) for l in cont), default=0)
            body = [body[0]] + [l[cut:] if l.strip() else "" for l in body[1:]]
            # 항목 안에서 문단 사이에 빈 줄이 있으면 loose (맨 끝 빈 줄은 제외)
            if any(not l.strip() for l in body[1:]) and any(l.strip() for l in body[1:]):
                loose = True
            items.append(body)
            # 다음 항목이 같은 들여쓰기로 이어지는지 (빈 줄이 끼면 loose)
            k = j
            while k < n and not lines[k].strip():
                k += 1
            nxt = ITEM.match(lines[k]) if k < n else None
            if nxt and len(nxt.group(1)) == ind and nxt.group(2)[0].isdigit() == ordered:
                loose = loose or k > j
                i = k
            else:
                i = j
                break
        tag = "ol" if ordered else "ul"
        st = f' start="{start}"' if ordered and start != 1 else ""
        lis = "".join(f"<li>{self.blocks(b, tight=not loose)}</li>" for b in items)
        return f"<{tag}{st}>{lis}</{tag}>", i

    def blocks(self, lines, tight=False):
        out, i, n = [], 0, len(lines)
        while i < n:
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            m = FENCE.match(line)
            if m:
                indent, mark, info = len(m.group(1)), m.group(2), m.group(3)
                close = re.compile(r"^ {0,3}" + re.escape(mark[0]) + "{" + str(len(mark)) + r",}\s*$")
                i += 1
                code = []
                while i < n and not close.match(lines[i]):
                    code.append(lines[i][min(indent, indent_of(lines[i])):])
                    i += 1
                i += 1
                lang = info.split()[0] if info.split() and not info.startswith("{") else ""
                lang = re.sub(r"[^\w+#.-]", "", lang)
                cls = f' class="language-{lang}"' if lang else ""
                out.append(f'<pre data-lang="{lang}"><code{cls}>{esc(chr(10).join(code))}</code></pre>')
                continue
            m = HEAD.match(line)
            if m:
                level, text = len(m.group(1)), m.group(2)
                rendered = self.inline(text)
                hid = self.heading_id(rendered, level)
                self.heads.append((html.unescape(re.sub(r"<[^>]+>", "", rendered)).strip(), hid))
                out.append(f'<h{level} id="{hid}">{rendered}<a class="anchor" href="#{hid}" '
                           f'aria-label="Link to this section">#</a></h{level}>')
                i += 1
                continue
            if HR.match(line):
                out.append("<hr>")
                i += 1
                continue
            if QUOTE.match(line):
                inner, i = self.quote_run(lines, i)
                mk = MARKER.match(inner[0]) if inner else None
                if mk and mk.group(1) == "tab":  # 연속된 > [tab] 블록들은 하나의 탭 그룹
                    tabs = [(mk.group(2) or "", inner[1:])]
                    while (nxt := self.next_marked(lines, i, "tab")):
                        tabs.append(nxt[:2])
                        i = nxt[2]
                    out.append(self.tab_group(tabs))
                    continue
                if mk and mk.group(1) == "accordion":
                    out.append(f'<details class="accordion"><summary>{self.inline(mk.group(2) or "")}</summary>'
                               f"{self.blocks(inner[1:])}</details>")
                    continue
                if mk:  # card: 연속된 카드는 격자로 묶는다
                    cards = [(mk.group(2) or "", inner[1:])]
                    while (nxt := self.next_marked(lines, i, "card")):
                        cards.append(nxt[:2])
                        i = nxt[2]
                    out.append('<div class="cards">' + "".join(
                        f'<div class="card"><div class="card-title">{self.inline(t)}</div>{self.blocks(b)}</div>'
                        for t, b in cards) + "</div>")
                    continue
                co = re.match(r"^\s*\[!(NOTE|TIP|WARNING|CAUTION|IMPORTANT)\]\s*$", inner[0]) if inner else None
                if co:  # GitHub 식 콜아웃: > [!NOTE]
                    kind = co.group(1).lower()
                    out.append(f'<div class="callout {kind}"><p class="callout-title">{kind.capitalize()}</p>'
                               f"{self.blocks(inner[1:])}</div>")
                elif out and out[-1].startswith("<h1") and not self.lead_done:  # 제목 바로 아래의 > 설명문은 상자 없이 본문처럼
                    self.lead_done = True
                    out.append('<div class="lead">' + self.blocks(inner) + "</div>")
                else:
                    out.append("<blockquote>" + self.blocks(inner) + "</blockquote>")
                continue
            if ITEM.match(line):
                h, i = self.list_block(lines, i)
                out.append(h)
                continue
            if "|" in line and i + 1 < n and "|" in lines[i + 1] and TABLE_SEP.match(lines[i + 1]):
                h, i = self.table(lines, i)
                out.append(h)
                continue
            hm = HTML_START.match(line)
            if hm and (line.lstrip().startswith("<!--") or hm.group(2).lower() in BLOCK_HTML):
                buf = []
                while i < n and lines[i].strip():
                    buf.append(lines[i])
                    i += 1
                out.append(self.inline("\n".join(buf)))
                continue
            buf = [line.lstrip()]
            i += 1
            while i < n and lines[i].strip() and not self.starts_block(lines, i, in_paragraph=True):
                buf.append(lines[i].lstrip())
                i += 1
            text = self.inline("\n".join(buf))
            out.append(text if tight else f"<p>{text}</p>")
        return "\n".join(out)

    def render(self, content):
        return self.blocks(strip_banner(content))  # 모든 페이지 맨 위의 안내문은 제거


def plain_text(content):
    """본문 검색용 평문: 마크다운 기호·태그·링크 주소를 걷어내고 공백을 한 칸으로 줄인다 (코드는 내용만 남김)."""
    t = "\n".join(l for l in strip_banner(content) if not FENCE.match(l))
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"</?[a-zA-Z][^<>]*>", " ", t)
    t = re.sub(r"^ {0,3}(?:#{1,6}|>+)[ \t]?", "", t, flags=re.M)
    t = re.sub(r"^[ \t]*\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$", "", t, flags=re.M)
    t = re.sub(r"[`*|]+|~~", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


# ---------- 사이트 구성 ----------
LANGS = ("en", "ko")

# 화면(UI) 문구. 문서 본문 번역이 아니라 검색창·버튼 같은 사이트 부품의 글자다. 본문은 항상 공식 원문을 쓴다.
UI_TEXT = {
    "en": {"lang_name": "English", "search": "Search...", "filter": "Filter pages...", "toggle": "Toggle navigation",
           "copy_page": "Copy page", "copied": "Copied", "copy": "Copy", "snapshot": "snapshot", "source": "Source",
           "loading": "Loading search index...", "no_index": "Search index not found.",
           "n_match": "{n} page(s) match", "none": "No page contains all words",
           "fallback": "There is no official Korean version of this page, so the original English text is shown.",
           "close": "Close"},
    "ko": {"lang_name": "한국어", "search": "검색...", "filter": "페이지 필터...", "toggle": "메뉴 열기",
           "copy_page": "페이지 복사", "copied": "복사됨", "copy": "복사", "snapshot": "스냅샷", "source": "원문",
           "loading": "검색 색인을 불러오는 중...", "no_index": "검색 색인을 찾을 수 없습니다.",
           "n_match": "{n}개 페이지 일치", "none": "모든 단어를 포함한 페이지가 없습니다",
           "fallback": "이 페이지는 공식 한국어판이 없어 영어 원문을 표시합니다.",
           "close": "닫기"},
}
JS_UI_KEYS = ("filter", "copied", "copy", "loading", "no_index", "n_match", "none", "search", "close")


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


def build_nav(pages, lang, names):
    """상단 탭 -> 사이드바 그룹 -> 페이지 트리. 탭·그룹 이름은 한국어 공식 사이트의 같은 자리 이름(names)을 쓴다."""
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

PAGE = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} - Claude Code Docs (offline)</title>
<link rel="stylesheet" href="{root}style.css"></head>
<body data-root="{root}" data-slug="{slug}" data-lang="{lang}">
<div id="chrome">
<header id="top">
<button id="navtoggle" type="button" aria-label="{t_toggle}">&#9776;</button>
<a class="logo" href="{root}index.html"><span class="star">&#10059;</span>Claude Code Docs<span class="offline">offline</span></a>
<details class="lang"><summary>{t_lang}</summary><div class="menu"><a href="{en_href}">English</a><a href="{ko_href}">한국어</a></div></details>
<button id="searchbtn" type="button">{icon_search}<span>{t_search}</span><kbd>Ctrl K</kbd></button>
</header>
<nav id="tabs"></nav>
</div>
<div id="shell">
<aside id="nav"></aside>
<main><article>
<div class="crumbs">{crumbs}</div>
{notice}<button id="copypage" type="button">{icon_copy}<span>{t_copy_page}</span></button>
{body}
<footer>{t_source}: <a href="{url}">{url}</a> &middot; {t_snapshot} {fetched}</footer>
</article></main>
</div>
<script type="application/json" id="md-src">{md}</script>
<script src="{root}nav-data-{lang}.js"></script><script src="{root}nav.js"></script>
</body></html>
"""

CSS = """:root{--bg:#fcfbf7;--fg:#1c1b19;--mut:#6c6a64;--line:#e6e3d9;--side:#eae8e1;--acc:#d97757;--code:#efede5;--pre:#fff;--link:#1c1b19;
--serif:"Iowan Old Style","Palatino Linotype",Georgia,"Noto Serif KR","Batang",serif;
--sans:-apple-system,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif;
--mono:ui-monospace,"Cascadia Mono",Consolas,"D2Coding",monospace}
@media (prefers-color-scheme:dark){:root{--bg:#1a1917;--fg:#ece9e1;--mut:#a29f96;--line:#3a3833;--side:#2d2b27;--acc:#e8825e;--code:#2a2824;--pre:#22211e;--link:#ece9e1}}
*{box-sizing:border-box}html{scroll-padding-top:132px}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.75 var(--sans)}
button{font:inherit;color:inherit}
#chrome{position:sticky;top:0;z-index:20;background:var(--bg)}
#top{height:68px;display:flex;align-items:center;gap:22px;padding:0 20px}
.logo{display:flex;align-items:center;gap:8px;color:var(--fg);text-decoration:none;font:400 28px/1 var(--serif);white-space:nowrap;letter-spacing:-.01em}
.logo .star{color:var(--acc);font-size:30px}
.logo .offline{align-self:flex-end;margin:0 0 5px 2px;color:var(--mut);font:500 13px var(--sans);letter-spacing:.02em}
details.lang{position:relative;font-weight:500;font-size:15px}
details.lang summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:6px;padding:6px 4px;white-space:nowrap}
details.lang summary::-webkit-details-marker{display:none}
details.lang summary::after{content:"";width:7px;height:7px;border:solid var(--mut);border-width:0 1.5px 1.5px 0;transform:rotate(45deg) translateY(-2px)}
details.lang .menu{position:absolute;top:100%;left:0;min-width:130px;background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:6px;box-shadow:0 8px 24px rgba(0,0,0,.12)}
details.lang .menu a{display:block;padding:7px 12px;border-radius:8px;color:var(--fg);text-decoration:none;font-weight:500}
details.lang .menu a:hover{background:var(--side)}
#searchbtn{margin:0 auto;display:flex;align-items:center;gap:10px;width:min(380px,38vw);height:40px;padding:0 14px;border:1px solid var(--line);border-radius:999px;background:var(--bg);color:var(--mut);cursor:pointer;font-size:15px}
#searchbtn span{flex:1;text-align:left}#searchbtn:hover{border-color:var(--mut)}
kbd{font:600 12px var(--sans);color:var(--mut);border:1px solid var(--line);border-radius:6px;padding:1px 6px}
#navtoggle{display:none;background:none;border:1px solid var(--line);border-radius:8px;font-size:20px;line-height:1;padding:6px 10px;cursor:pointer}
#tabs{display:flex;gap:28px;height:48px;padding:0 20px;border-bottom:1px solid var(--line);overflow-x:auto;white-space:nowrap;scrollbar-width:none}
#tabs::-webkit-scrollbar{display:none}
#tabs a{display:block;line-height:46px;color:var(--mut);text-decoration:none;font-weight:500;font-size:15px;border-bottom:2px solid transparent}
#tabs a:hover{color:var(--fg)}#tabs a.active{color:var(--fg);font-weight:700;border-color:var(--fg)}
#shell{display:flex;align-items:flex-start}
#nav{position:sticky;top:116px;flex:none;width:286px;height:calc(100vh - 116px);overflow-y:auto;padding:20px 24px 48px 0;border-right:1px solid var(--line);font-size:15px;line-height:1.4}
#nav input{width:calc(100% - 14px);margin:0 0 4px 2px;padding:8px 12px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--fg);font-size:14px}
#nav .grp h5{margin:26px 0 8px;padding:0 16px;font-size:15px;font-weight:700}
#nav a.leaf{display:block;padding:9px 16px;margin:1px 0;color:var(--fg);opacity:.82;text-decoration:none;border-radius:12px}
#nav a.leaf:hover{background:var(--side);opacity:1}
#nav a.leaf[aria-current]{background:var(--side);opacity:1;font-weight:600}
#nav details.sub>summary{list-style:none;cursor:pointer;display:flex;justify-content:space-between;align-items:center;padding:9px 16px;border-radius:12px;opacity:.82}
#nav details.sub>summary::-webkit-details-marker{display:none}
#nav details.sub>summary::after{content:"\\203A";font-size:18px;color:var(--mut);transition:transform .12s}
#nav details.sub[open]>summary::after{transform:rotate(90deg)}
#nav details.sub>summary:hover{background:var(--side);opacity:1}
#nav .subbox{margin-left:12px;border-left:1px solid var(--line)}
main{flex:1;min-width:0;padding:34px 48px 96px}
article{position:relative;max-width:760px;margin:0 auto}
.crumbs{color:var(--fg);font-size:14px;font-weight:600;text-transform:uppercase;letter-spacing:.02em}
.notice{margin:.8em 0;padding:.6em 1em;border:1px solid var(--line);border-radius:12px;background:var(--side);color:var(--mut);font-size:14px}
#copypage{position:absolute;right:0;top:22px;display:flex;align-items:center;gap:8px;height:38px;padding:0 14px;border:1px solid var(--line);border-radius:12px;background:var(--bg);font-size:14px;font-weight:500;cursor:pointer}
#copypage:hover{border-color:var(--mut)}
h1,h2{font-family:var(--serif);font-weight:400;line-height:1.2;letter-spacing:-.01em}
h1{font-size:2.5rem;margin:.2em 0 .5em;padding-right:150px}h2{font-size:1.75rem;margin:2em 0 .7em}
h3{font-size:1.15rem;margin:1.8em 0 .5em}h4{font-size:1rem;margin:1.5em 0 .4em}h3,h4{line-height:1.35}
.anchor{margin-left:.4em;color:var(--mut);text-decoration:none;opacity:0;font-family:var(--sans)}
h1:hover .anchor,h2:hover .anchor,h3:hover .anchor,h4:hover .anchor{opacity:1}
article a{color:var(--link)}
article p a,article li a,article td a,article summary a,.card-title a{font-weight:600;text-decoration:underline;text-decoration-thickness:1.5px;text-underline-offset:3px}
article a.anchor{font-weight:400;text-decoration:none}
code{background:var(--code);padding:.12em .4em;border-radius:6px;font:.88em var(--mono)}
pre{position:relative;background:var(--pre);border:1px solid var(--line);padding:16px 18px;border-radius:16px;overflow:auto;line-height:1.55;margin:1.2em 0}
pre code{background:none;padding:0;font-size:.86em}
pre .copy{position:absolute;top:10px;right:10px;display:flex;align-items:center;gap:6px;padding:4px 6px;border:0;border-radius:8px;background:var(--pre);color:var(--mut);cursor:pointer;font-size:12px}
pre .copy:hover{color:var(--fg);background:var(--side)}
blockquote{margin:1em 0;padding:.1em 1em;border-left:4px solid var(--acc);background:var(--side);border-radius:0 12px 12px 0}
.callout{margin:1.2em 0;padding:.7em 1.1em;border:1px solid #bcd3fb;background:rgba(59,130,246,.08);border-radius:14px}
.callout>:last-child{margin-bottom:.3em}.callout-title{margin:.1em 0 .3em;font-weight:700;color:#3b82f6}
.callout.tip{border-color:#a7dfbd;background:rgba(22,163,74,.08)}.callout.tip .callout-title{color:#16a34a}
.callout.warning,.callout.caution{border-color:#f1cf9c;background:rgba(217,119,6,.09)}.callout.warning .callout-title,.callout.caution .callout-title{color:#d97706}
.callout.important{border-color:#d5b8f3;background:rgba(147,51,234,.08)}.callout.important .callout-title{color:#9333ea}
.tabs{margin:1.4em 0}
.tab-list{display:flex;flex-wrap:wrap;gap:0 26px;border-bottom:1px solid var(--line)}
.tab-btn{background:none;border:0;border-bottom:2px solid transparent;margin-bottom:-1px;padding:8px 0;color:var(--mut);font-size:15px;font-weight:600;cursor:pointer;white-space:nowrap}
.tab-btn:hover{color:var(--fg)}.tab-btn.active{color:var(--fg);border-color:var(--fg)}
.tab-panel{display:none;padding-top:.6em}.tab-panel.active{display:block}
details.accordion{margin:.8em 0;border:1px solid var(--line);border-radius:14px;padding:0 16px}
details.accordion>summary{cursor:pointer;padding:12px 0;font-weight:600;list-style:none;display:flex;justify-content:space-between;gap:12px}
details.accordion>summary::-webkit-details-marker{display:none}
details.accordion>summary::after{content:"+";color:var(--mut);font-size:20px;line-height:1.3}
details.accordion[open]>summary::after{content:"\\2212"}
details.accordion[open]{padding-bottom:6px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px;margin:1.2em 0}
.card{position:relative;border:1px solid var(--line);border-radius:16px;padding:16px 18px}.card:hover{border-color:var(--mut)}
.card-title{font-weight:700;margin-bottom:.2em}.card-title a{text-decoration:none!important}
.card-title a::after{content:"";position:absolute;inset:0}.card p{margin:.2em 0;color:var(--mut);font-size:15px}
.table-wrap{overflow-x:auto;margin:1.2em 0}table{border-collapse:collapse;width:100%}
th,td{border:1px solid var(--line);padding:7px 12px;text-align:left;vertical-align:top}th{background:var(--side)}
img,video{max-width:100%;height:auto;border-radius:10px}hr{border:0;border-top:1px solid var(--line);margin:2em 0}
footer{margin-top:4em;padding-top:1em;border-top:1px solid var(--line);color:var(--mut);font-size:13px}
mark{background:#fde68a;color:#1f1e1d;border-radius:2px;padding:0 1px}
#searchmodal{position:fixed;inset:0;z-index:50;background:rgba(20,19,17,.45);display:flex;justify-content:center;align-items:flex-start;padding-top:12vh}
#searchmodal[hidden]{display:none}
#searchmodal .panel{width:min(680px,92vw);max-height:72vh;display:flex;flex-direction:column;background:var(--bg);border:1px solid var(--line);border-radius:18px;box-shadow:0 20px 60px rgba(0,0,0,.3);overflow:hidden}
#searchmodal input{border:0;border-bottom:1px solid var(--line);padding:16px 20px;font-size:17px;background:transparent;color:var(--fg);outline:none}
#results{overflow-y:auto;padding:8px}
#results .hit{display:block;padding:10px 14px;margin:2px 0;border-radius:12px;color:var(--fg);text-decoration:none;font-size:14px;line-height:1.45}
#results .hit:hover,#results .hit:focus{background:var(--side);outline:none}#results .hit b{display:block;font-size:15px}#results .hit span{color:var(--mut)}
#results .info{color:var(--mut);font-size:13px;padding:6px 14px}
.tk-c{color:#6b7280;font-style:italic}.tk-s{color:#15803d}.tk-n{color:#b45309}.tk-k{color:#7c3aed;font-weight:600}.tk-key{color:#1d4ed8}
@media (prefers-color-scheme:dark){.tk-c{color:#9ca3af}.tk-s{color:#86efac}.tk-n{color:#fbbf24}.tk-k{color:#c4b5fd}.tk-key{color:#93c5fd}}
@media (max-width:1000px){main{padding:26px 22px 80px}h1{padding-right:0;font-size:2rem}#copypage{position:static;margin:.6em 0 0}}
@media (max-width:900px){#navtoggle{display:block}.logo .offline{display:none}.logo{font-size:22px}.logo .star{font-size:24px}#top{gap:12px;padding:0 12px}#tabs{padding:0 12px}
#searchbtn{width:auto;margin-left:auto;padding:0 12px}#searchbtn span,#searchbtn kbd{display:none}
#nav{position:fixed;top:116px;left:0;z-index:15;width:290px;background:var(--bg);padding-left:8px;transform:translateX(-100%);transition:transform .15s}
body.navopen #nav{transform:none;box-shadow:0 0 40px rgba(0,0,0,.25)}}
"""

JS = r"""(function(){
var B=document.body,root=B.dataset.root||"",cur=B.dataset.slug||"",lang=B.dataset.lang||"en",T=window.DOCS_UI||{};
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
function copyText(t,done){
 if(navigator.clipboard&&window.isSecureContext)navigator.clipboard.writeText(t).then(done);
 else{var x=document.createElement("textarea");x.value=t;document.body.appendChild(x);x.select();document.execCommand("copy");x.remove();done()}}
var tog=document.getElementById("navtoggle");if(tog)tog.onclick=function(){B.classList.toggle("navopen")};

/* ---- 상단 탭 + 사이드바 ---- */
var data=window.DOCS_NAV,tabsEl=document.getElementById("tabs"),nav=document.getElementById("nav");
function first(n){if(n.p)return n.p;for(var i=0;i<n.c.length;i++){var r=first(n.c[i]);if(r)return r}return ""}
function has(n,p){if(n.p)return n.p===p;return n.c.some(function(c){return has(c,p)})}
if(data&&nav){
 var curPath=cur+".html",active=null;
 data.tabs.forEach(function(t){if(!active&&has(t,curPath))active=t});
 if(!active)active=data.tabs[0];
 data.tabs.forEach(function(t){if(t.hidden)return;var a=el("a",t===active?"active":"",t.n);a.href=root+first(t);tabsEl.appendChild(a)});
 var box=el("input");box.type="search";box.placeholder=T.filter||"Filter pages...";nav.appendChild(box);
 var wrap=el("div","tree");nav.appendChild(wrap);
 function leaf(n){var a=el("a","leaf",n.t);a.href=root+n.p;if(n.p===curPath)a.setAttribute("aria-current","page");return a}
 function build(nodes,parent,depth){nodes.forEach(function(n){
  if(n.p){parent.appendChild(leaf(n));return}
  if(depth===0){var sec=el("section","grp");sec.appendChild(el("h5",null,n.g));build(n.c,sec,1);parent.appendChild(sec)}
  else{var d=el("details","sub");d.appendChild(el("summary",null,n.g));var inner=el("div","subbox");build(n.c,inner,depth+1);d.appendChild(inner);if(has(n,curPath))d.open=true;parent.appendChild(d)}})}
 build(active.c,wrap,0);
 function reset(){wrap.querySelectorAll("details.sub").forEach(function(d){d.open=!!d.querySelector("[aria-current]")})}
 var cl=wrap.querySelector("[aria-current]");if(cl)nav.scrollTop=Math.max(0,cl.getBoundingClientRect().top-nav.getBoundingClientRect().top+nav.scrollTop-nav.clientHeight/2);
 box.oninput=function(){var q=box.value.trim().toLowerCase();
  wrap.querySelectorAll("a.leaf").forEach(function(a){a.style.display=!q||a.textContent.toLowerCase().indexOf(q)>=0?"":"none"});
  wrap.querySelectorAll("details.sub,section.grp").forEach(function(d){var vis=!q||Array.prototype.some.call(d.querySelectorAll("a.leaf"),function(a){return a.style.display!=="none"});
   d.style.display=vis?"":"none";if(q&&d.tagName==="DETAILS")d.open=vis});
  if(!q)reset()}}

/* ---- 본문 탭, 앵커 이동 ---- */
function selectTab(b){var g=b.closest(".tabs");Array.prototype.forEach.call(g.children,function(c){
 if(c.classList.contains("tab-list")){Array.prototype.forEach.call(c.children,function(x){var on=x===b;x.classList.toggle("active",on);x.setAttribute("aria-selected",on?"true":"false")})}
 else if(c.classList.contains("tab-panel"))c.classList.toggle("active",c.id===b.dataset.tab)})}
document.addEventListener("click",function(e){var b=e.target.closest&&e.target.closest(".tab-btn");if(b)selectTab(b)});
function reveal(t){for(var e=t;e&&e!==B;e=e.parentElement){
 if(e.classList.contains("tab-panel")){var btn=e.parentElement.querySelector('.tab-btn[data-tab="'+e.id+'"]');if(btn)selectTab(btn)}
 if(e.tagName==="DETAILS")e.open=true}}
function anchorKey(s){try{s=decodeURIComponent(s)}catch(e){}return s.toLowerCase().replace(/[^\p{L}\p{N}]/gu,"")}
function goHash(){var h=location.hash.slice(1);if(!h)return;var t;try{t=document.getElementById(decodeURIComponent(h))}catch(e){}
 if(!t){var k=anchorKey(h),c=document.querySelectorAll("article [id]");for(var i=0;i<c.length;i++){if(anchorKey(c[i].id)===k){t=c[i];break}}}
 if(t){reveal(t);t.scrollIntoView()}}
window.addEventListener("hashchange",goHash);goHash();

/* ---- 페이지 복사, 코드 복사 ---- */
var cp=document.getElementById("copypage"),src=document.getElementById("md-src");
if(cp&&src){var lab=cp.querySelector("span"),orig=lab.textContent;
 cp.onclick=function(){copyText(JSON.parse(src.textContent),function(){lab.textContent=T.copied||"Copied";setTimeout(function(){lab.textContent=orig},1200)})}}
var ICON='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="3" width="8" height="4" rx="1"/><path d="M16 5h2a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2"/></svg>';
document.querySelectorAll("pre").forEach(function(pre){var b=el("button","copy");b.type="button";b.innerHTML=ICON;b.title=T.copy||"Copy";b.setAttribute("aria-label",T.copy||"Copy");
 b.onclick=function(){copyText(pre.querySelector("code").innerText,function(){b.textContent=T.copied||"Copied";setTimeout(function(){b.innerHTML=ICON},1200)})};
 pre.appendChild(b)});
})();

/* ---- 본문 검색 (Ctrl K 팝업). 색인은 처음 검색할 때만 불러온다 ---- */
(function(){
var B=document.body,root=B.dataset.root||"",lang=B.dataset.lang||"en",T=window.DOCS_UI||{},btn=document.getElementById("searchbtn");if(!btn)return;
var modal=document.createElement("div");modal.id="searchmodal";modal.hidden=true;
var panel=document.createElement("div");panel.className="panel";var box=document.createElement("input");box.type="search";box.placeholder=T.search||"Search...";
var res=document.createElement("div");res.id="results";panel.appendChild(box);panel.appendChild(res);modal.appendChild(panel);document.body.appendChild(modal);
var state="idle",docs=null;
function open(){modal.hidden=false;box.focus();box.select()}
function close(){modal.hidden=true}
btn.onclick=open;modal.addEventListener("mousedown",function(e){if(e.target===modal)close()});
document.addEventListener("keydown",function(e){if((e.ctrlKey||e.metaKey)&&(e.key==="k"||e.key==="K")){e.preventDefault();modal.hidden?open():close()}else if(e.key==="Escape"&&!modal.hidden)close()});
function load(cb){if(docs)return cb();if(state==="loading")return;state="loading";res.textContent=T.loading||"Loading...";
 var s=document.createElement("script");s.src=root+"search-data-"+lang+".js";
 s.onload=function(){docs=window.DOCS_SEARCH;docs.forEach(function(d){d.lt=d.t.toLowerCase();d.lx=d.x.toLowerCase()});state="ready";cb()};
 s.onerror=function(){state="idle";res.textContent=T.no_index||"Search index not found."};document.head.appendChild(s)}
function count(h,t){var n=0,i=0;while(n<20&&(i=h.indexOf(t,i))>=0){n++;i+=t.length}return n}
function mark(parent,text,terms){var low=text.toLowerCase(),pos=0;
 while(pos<text.length){var best=-1,bl=0;
  terms.forEach(function(t){var i=low.indexOf(t,pos);if(i>=0&&(best<0||i<best)){best=i;bl=t.length}});
  if(best<0){parent.appendChild(document.createTextNode(text.slice(pos)));break}
  if(best>pos)parent.appendChild(document.createTextNode(text.slice(pos,best)));
  var m=document.createElement("mark");m.textContent=text.slice(best,best+bl);parent.appendChild(m);pos=best+bl}}
function run(){var q=box.value.trim().toLowerCase();res.textContent="";if(q.length<2)return;
 var terms=q.split(/\s+/).filter(Boolean);
 load(function(){if(box.value.trim().toLowerCase()!==q)return;res.textContent="";var hits=[];
  docs.forEach(function(d){var score=0;
   for(var i=0;i<terms.length;i++){var t=terms[i],inT=d.lt.indexOf(t)>=0,inX=d.lx.indexOf(t)>=0,inH=d.h.some(function(h){return h[0].toLowerCase().indexOf(t)>=0});
    if(!inT&&!inX&&!inH)return;score+=(inT?100:0)+(inH?20:0)+count(d.lx,t)}
   hits.push({d:d,s:score})});
  hits.sort(function(a,b){return b.s-a.s});
  var info=document.createElement("div");info.className="info";info.textContent=hits.length?(T.n_match||"{n}").replace("{n}",hits.length):(T.none||"");res.appendChild(info);
  hits.slice(0,30).forEach(function(h){var d=h.d,a=document.createElement("a");a.className="hit";
   var head=d.h.filter(function(x){return terms.some(function(t){return x[0].toLowerCase().indexOf(t)>=0})})[0];
   a.href=root+d.p+(head?"#"+head[1]:"");var b=document.createElement("b");mark(b,d.t,terms);a.appendChild(b);
   var i=-1;terms.forEach(function(t){var k=d.lx.indexOf(t);if(k>=0&&(i<0||k<i))i=k});
   var sn=document.createElement("span");if(i>=0){var from=Math.max(0,i-50);sn.appendChild(document.createTextNode(from?"...":""));mark(sn,d.x.slice(from,i+110),terms);sn.appendChild(document.createTextNode("..."))}
   a.appendChild(sn);res.appendChild(a)})})}
var timer;box.addEventListener("input",function(){clearTimeout(timer);timer=setTimeout(run,150)});
})();

/* ---- 코드 구문 강조 (규칙 기반) ---- */
(function(){
var C={c:"#",kw:"if then else elif fi for while do done case esac in function return export local echo cd ls cat grep git npm npx pip python python3 node claude curl mkdir rm cp mv sudo exit set unset source alias read test true false"};
var JSK="const let var function return if else for while do switch case break continue new class extends import export from default async await try catch finally throw typeof instanceof in of this null undefined true false void yield static interface type enum implements public private readonly";
var L={bash:C,sh:C,shell:C,zsh:C,console:C,
 json:{kw:"true false null",key:1},jsonc:{c:"//",kw:"true false null",key:1},
 python:{c:"#",kw:"def class return if elif else for while in not and or is import from as with try except finally raise pass break continue lambda yield None True False async await self print",tq:1},
 yaml:{c:"#",kw:"true false null yes no"},yml:{c:"#",kw:"true false null yes no"},toml:{c:"#",kw:"true false"},
 powershell:{c:"#",kw:"if else elseif foreach for while function return param switch try catch finally throw $true $false $null"},
 javascript:{c:"//",kw:JSK,bt:1},js:{c:"//",kw:JSK,bt:1},typescript:{c:"//",kw:JSK,bt:1},ts:{c:"//",kw:JSK,bt:1},jsx:{c:"//",kw:JSK,bt:1},tsx:{c:"//",kw:JSK,bt:1}};
L.ps1=L.powershell;L.py=L.python;
function re(cfg){var cm=[];
 if(cfg.c==="#")cm.push("(?<![^\\s])#[^\\n]*");
 if(cfg.c==="//")cm.push("//[^\\n]*","/\\*[\\s\\S]*?\\*/");
 var Q3='"'+'"'+'"',S3="'"+"'"+"'",st=[];if(cfg.tq)st.push(Q3+"[\\s\\S]*?"+Q3,S3+"[\\s\\S]*?"+S3);
 st.push('"(?:[^"\\\\\\n]|\\\\.)*"',"'(?:[^'\\\\\\n]|\\\\.)*'");if(cfg.bt)st.push("`(?:[^`\\\\]|\\\\.)*`");
 return new RegExp("("+(cm.join("|")||"(?!)")+")|("+st.join("|")+")|(\\b\\d+(?:\\.\\d+)?\\b)|([$A-Za-z_][\\w$-]*)","g")}
function span(parent,cls,text){var s=document.createElement("span");s.className=cls;s.textContent=text;parent.appendChild(s)}
document.querySelectorAll("pre[data-lang]").forEach(function(pre){var cfg=L[(pre.dataset.lang||"").toLowerCase()],code=pre.querySelector("code");
 if(!cfg||!code)return;var text=code.textContent;if(text.length>30000)return;
 var kw={};cfg.kw.split(" ").forEach(function(w){kw[w]=1});var r=re(cfg),pos=0,m,out=document.createDocumentFragment();
 while((m=r.exec(text))){if(m.index>pos)out.appendChild(document.createTextNode(text.slice(pos,m.index)));
  if(m[1])span(out,"tk-c",m[0]);
  else if(m[2]){var isKey=cfg.key&&/^\\s*:/.test(text.slice(r.lastIndex,r.lastIndex+20));span(out,isKey?"tk-key":"tk-s",m[0])}
  else if(m[3])span(out,"tk-n",m[0]);
  else if(kw[m[0]])span(out,"tk-k",m[0]);else out.appendChild(document.createTextNode(m[0]));
  pos=r.lastIndex;if(m[0].length===0)r.lastIndex++}
 if(pos<text.length)out.appendChild(document.createTextNode(text.slice(pos)));
 code.textContent="";code.appendChild(out)});
})();
"""


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main(argv=None):
    """argv: 입력.json(.gz) [출력폴더] [에셋 원본 폴더]. 출력폴더에 assets/ 가 이미 있으면 에셋은 복사하지 않는다."""
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
    n_fallback = hint_full = hint_total = 0
    for p in pages:
        rest = rest_of(p)
        en_head_ids = None
        for lang in LANGS:  # en 을 먼저 렌더링해 헤딩 id 를 한국어판이 빌려 쓴다
            title, content, _, fallback = view(p, lang)
            use_hint = lang == "ko" and not fallback and en_head_ids is not None
            slug = f"{lang}/{rest}"
            r = Renderer(slug, targets[lang], p.get("assets", {}), hint=en_head_ids if use_hint else None)
            body = r.render(content)
            if lang == "en":
                en_head_ids = r.head_ids
            elif use_hint:
                hint_total += 1
                hint_full += r.hint is not None and r.hint_pos == len(en_head_ids) == len(r.head_ids)
            n_fallback += fallback
            page_ids[slug] = r.used_ids
            page_links += [(slug, t, f) for t, f in r.links]
            search[lang].append({"t": title, "p": slug + ".html", "h": [list(h) for h in r.heads if h[0]],
                                 "x": plain_text(content)})
            root = "../" * slug.count("/")
            ui = UI_TEXT[lang]
            url = norm(p["url"] if lang == "en" or fallback else ko_url(p["url"]))
            md = json.dumps("\n".join(strip_banner(content)), ensure_ascii=False).replace("<", "\\u003c")
            write_text(os.path.join(out, *(slug + ".html").split("/")), PAGE.format(
                lang=lang, title=esc(title), root=root, slug=slug, body=body, md=md,
                crumbs=esc(crumb_of(p, lang, names_ko)),
                notice=f'<div class="notice">{esc(ui["fallback"])}</div>\n' if fallback else "",
                en_href=f"{root}en/{rest}.html", ko_href=f"{root}ko/{rest}.html", url=attr(url),
                fetched=snap.get("fetched_at", ""), icon_search=ICON_SEARCH, icon_copy=ICON_COPY,
                t_lang=ui["lang_name"], t_toggle=ui["toggle"], t_search=ui["search"], t_copy_page=ui["copy_page"],
                t_source=ui["source"], t_snapshot=ui["snapshot"]))

    for lang in LANGS:
        ui = {k: UI_TEXT[lang][k] for k in JS_UI_KEYS}
        write_text(os.path.join(out, f"nav-data-{lang}.js"),
                   "window.DOCS_NAV=" + json.dumps({"tabs": build_nav(pages, lang, names_ko)}, ensure_ascii=False)
                   + ";\nwindow.DOCS_UI=" + json.dumps(ui, ensure_ascii=False) + ";\n")
        write_text(os.path.join(out, f"search-data-{lang}.js"),  # 첫 검색 때 지연 로드
                   "window.DOCS_SEARCH=" + json.dumps(search[lang], ensure_ascii=False, separators=(",", ":")) + ";\n")
    write_text(os.path.join(out, "style.css"), CSS)
    write_text(os.path.join(out, "nav.js"), JS)
    home = f"en/{rest_of(pages[0])}.html"  # 목차 맨 앞 페이지 (Overview)
    write_text(os.path.join(out, "index.html"),
               f'<!doctype html><meta charset="utf-8"><title>Claude Code Docs (offline)</title>'
               f'<meta http-equiv="refresh" content="0; url={home}"><a href="{home}">{home}</a>\n')

    # self-check: 변환된 내부 링크가 가리키는 파일과 앵커가 실제로 있는지
    # (앵커는 사이트 규칙과 구두점 처리가 달라, nav.js 의 폴백과 같이 영숫자만 비교)
    missing_files = [(s, t) for s, t, _ in page_links if not os.path.isfile(os.path.join(out, *(t + ".html").split("/")))]
    anchor_keys = {s: {anchor_key(i) for i in ids} for s, ids in page_ids.items()}
    bad_anchors = sorted({(s, t, f) for s, t, f in page_links if f and anchor_key(f) not in anchor_keys.get(t, ())})
    n_ko = sum(1 for p in pages if p.get("ko"))
    print(f"페이지 {len(pages)}개 x 2개 언어 (한국어판 {n_ko}개, 영어 원문 대체 {n_fallback}개) -> {out}", file=sys.stderr)
    print(f"한국어 헤딩 id: 영어판과 완전히 일치 {hint_full}/{hint_total}페이지", file=sys.stderr)
    print(f"내부 링크 {len(page_links)}개 변환, 없는 파일 {len(missing_files)}개, 없는 앵커 {len(bad_anchors)}개"
          f" (en {sum(s.startswith('en/') for s, _, _ in bad_anchors)}, ko {sum(s.startswith('ko/') for s, _, _ in bad_anchors)})",
          file=sys.stderr)
    for s, t, f in bad_anchors[:10]:
        print(f"  앵커 없음: {s} -> {t}#{f}", file=sys.stderr)
    return len(missing_files)


if __name__ == "__main__":
    setup_console()
    sys.exit(1 if main() else 0)
