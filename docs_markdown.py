"""마크다운 -> HTML 변환기(Mintlify 컴포넌트 포함)와 검색용 평문 변환. 표준 라이브러리만 사용.

Renderer 가 페이지 1개를 HTML 로 바꾸고, 헤딩·아코디언 id 와 링크 목록을 모아 둔다 (앵커 확정은 docs_anchors).
"""
import html
import re
import urllib.parse
from posixpath import dirname as pdirname, relpath as prelpath

from docs_common import norm

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


def anchor_key(s):
    """앵커 비교용: URL 디코딩 + 소문자 + 글자·숫자만. site_src/lib.js 의 anchorKey 와 같은 규칙이어야 한다
    (tests/test_anchor_sync.py 가 두 구현을 같은 입력으로 비교한다). JS 의 decodeURIComponent 는 깨진 %인코딩에서
    예외를 던져 원문을 그대로 쓰므로, 여기서도 엄격하게 디코딩하고 실패하면 원문을 쓴다."""
    try:
        s = urllib.parse.unquote(s, errors="strict")
    except UnicodeDecodeError:
        pass
    return re.sub(r"[\W_]", "", s.lower())


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

    def __init__(self, slug, targets, assets, hint=None, acc_hint=None, defer_anchors=False):
        """hint: 같은 페이지 다른 언어판의 [(헤딩 레벨, id), ...]. 주면 헤딩 id 를 그대로 빌려 쓴다
        (공식 한국어판 본문의 링크도 영어판 앵커를 쓰기 때문). 레벨이 어긋나면 그 지점부터는 기본 규칙으로 돌아간다.
        acc_hint: 같은 방식으로 빌려 쓰는 아코디언 id 목록 [id, ...] (헤딩과 따로 순서를 센다)."""
        self.slug, self.targets = slug, targets
        self.assets = {k.replace("\\&", "&"): v for k, v in assets.items()}
        self.ids, self.used_ids = {}, set()
        self.links = []  # (대상 slug, 앵커) — 나중에 앵커 검사용. 앵커가 있는 링크는 href 에 \x01번호\x01 표시가 들어가고 resolve_anchors 가 채운다
        self.heads = []  # (헤딩 글자, id) — 본문 검색 결과에서 해당 위치로 이동하기 위함
        self.head_ids = []  # (헤딩 레벨, id) — 다른 언어판이 id 를 빌려 가기 위함
        self.acc_ids = []  # 아코디언 id (문서 순서) — 다른 언어판이 빌려 가기 위함
        self.hint, self.hint_pos, self.tab_n, self.lead_done = (list(hint) if hint else None), 0, 0, False
        self.acc_hint, self.acc_pos = (list(acc_hint) if acc_hint else None), 0
        self.defer_anchors = defer_anchors  # True 면 앵커가 있는 링크를 \x01번호\x01 로 남겨 둔다 (resolve_anchors 용)

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
                frag = (m.group(2) or "")[1:]
                self.links.append((target, frag))
                if frag and self.defer_anchors:  # 앵커는 모든 페이지의 id 가 정해진 뒤 resolve_anchors 에서 실제 id 로 확정한다
                    return f"\x01{len(self.links) - 1}\x01"
                return self.rel(target + ".html") + (f"#{frag}" if frag else "")
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
        hid = self.unique_id(text)
        self.head_ids.append((level, hid))
        return hid

    def unique_id(self, text):
        """제목 글자 -> 페이지 안에서 겹치지 않는 id (헤딩과 아코디언이 같은 규칙·같은 번호 공간을 쓴다)."""
        base = heading_slug(text) or "section"
        n = self.ids.get(base, -1) + 1
        self.ids[base] = n
        hid = base if n == 0 else f"{base}-{n}"
        self.used_ids.add(hid)
        return hid

    def accordion_id(self, text):
        if self.acc_hint is not None:
            if self.acc_pos < len(self.acc_hint):
                hid = self.acc_hint[self.acc_pos]
                self.acc_pos += 1
                self.used_ids.add(hid)
                self.acc_ids.append(hid)
                return hid
            self.acc_hint = None  # 어긋남: 나머지는 기본 규칙
        hid = self.unique_id(text)
        self.acc_ids.append(hid)
        return hid

    def tab_group(self, tabs):
        """[(이름, 본문 줄들), ...] -> 탭 UI. 첫 탭이 열려 있고 버튼으로 전환한다 (nav.js)."""
        self.tab_n += 1
        gid = f"tab{self.tab_n}"
        # WAI-ARIA 탭 패턴: 탭마다 id·aria-controls, 패널은 aria-labelledby, 선택된 탭만 Tab 키로 들어가고 나머지는 화살표 키로 이동
        btns = "".join(
            f'<button type="button" class="tab-btn{" active" if k == 0 else ""}" role="tab" id="{gid}-{k}-tab" '
            f'aria-controls="{gid}-{k}" aria-selected="{"true" if k == 0 else "false"}" tabindex="{0 if k == 0 else -1}" '
            f'data-tab="{gid}-{k}">{self.inline(name)}</button>'
            for k, (name, _) in enumerate(tabs))
        panels = "".join(f'<div class="tab-panel{" active" if k == 0 else ""}" role="tabpanel" id="{gid}-{k}" '
                         f'aria-labelledby="{gid}-{k}-tab" tabindex="0">{self.blocks(body)}</div>'
                         for k, (_, body) in enumerate(tabs))
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
                    title = self.inline(mk.group(2) or "")
                    aid = self.accordion_id(title)  # 제목이 같은 slug 규칙의 id: 본문 링크(#제목)가 아코디언을 가리킨다
                    out.append(f'<details class="accordion" id="{aid}"><summary>{title}</summary>'
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
