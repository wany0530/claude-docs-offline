#!/usr/bin/env python3
"""docs_fetch_json.py 가 만든 JSON 을 오프라인에서 바로 열어볼 수 있는 정적 HTML 사이트로 변환합니다.

사용법:  python docs_json_to_html.py 입력.json [출력폴더]   (기본: 입력 JSON 옆의 html/)
결과:    출력폴더/index.html        전체 목차 (브라우저로 이 파일을 열면 됩니다)
         출력폴더/en/....html       페이지별 HTML (원문 주소 구조 그대로)
         출력폴더/assets/           이미지·동영상
         출력폴더/style.css, nav.js, nav-data.js   (사이드바·필터 등. 서버 없이 file:// 로 동작)
본문 마크다운 -> HTML 변환기를 직접 구현했고, docs 사이트 내부 링크는 상대 경로로 바꿉니다. 표준 라이브러리만 사용.
"""
import html
import json
import os
import re
import shutil
import sys
import urllib.parse
from posixpath import dirname as pdirname, relpath as prelpath

from docs_common import norm, slug as url_slug

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


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


class Renderer:
    """페이지 1개를 HTML 로 변환. slug 는 'en/agent-sdk/mcp' 형태."""

    def __init__(self, slug, targets, assets):
        self.slug, self.targets = slug, targets
        self.assets = {k.replace("\\&", "&"): v for k, v in assets.items()}
        self.ids, self.used_ids = {}, set()
        self.links = []  # (대상 slug, 앵커) — 나중에 앵커 검사용

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
    def heading_id(self, text):
        base = heading_slug(text) or "section"
        n = self.ids.get(base, -1) + 1
        self.ids[base] = n
        hid = base if n == 0 else f"{base}-{n}"
        self.used_ids.add(hid)
        return hid

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
                hid = self.heading_id(self.inline(text))
                out.append(f'<h{level} id="{hid}">{self.inline(text)}<a class="anchor" href="#{hid}" '
                           f'aria-label="Link to this section">#</a></h{level}>')
                i += 1
                continue
            if HR.match(line):
                out.append("<hr>")
                i += 1
                continue
            if QUOTE.match(line):
                inner = []
                while i < n and QUOTE.match(lines[i]):
                    inner.append(re.sub(r"^ {0,3}> ?", "", lines[i]))
                    i += 1
                co = re.match(r"^\s*\[!(NOTE|TIP|WARNING|CAUTION|IMPORTANT)\]\s*$", inner[0]) if inner else None
                if co:  # GitHub 식 콜아웃: > [!NOTE]
                    kind = co.group(1).lower()
                    out.append(f'<div class="callout {kind}"><p class="callout-title">{kind.capitalize()}</p>'
                               f"{self.blocks(inner[1:])}</div>")
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
        lines = content.replace("\r\n", "\n").split("\n")
        if lines and lines[0].startswith("> ## Documentation Index"):  # 모든 페이지 맨 위의 안내문은 제거
            while lines and (lines[0].startswith(">") or not lines[0].strip()):
                lines.pop(0)
        return self.blocks(lines)


# ---------- 사이트 구성 ----------
class Group:
    def __init__(self, name):
        self.name, self.children, self.idx = name, [], {}

    def sub(self, name):
        g = self.idx.get(name)
        if g is None:
            g = self.idx[name] = Group(name)
            self.children.append(g)
        return g

    def to_json(self):
        return {"g": self.name,
                "c": [c.to_json() if isinstance(c, Group) else {"t": c[0], "p": c[1]} for c in self.children]}


def build_tree(pages):
    root = Group("")
    for p in pages:
        cat = p["category"]
        g = root
        for f in [cat[0]] + cat[2:]:  # zip 변환기와 같은 규칙: ### 그룹은 대분류와 이름이 겹쳐 생략
            g = g.sub("Unlisted" if f == "_unlisted" else f)
        g.children.append((p.get("nav_label", p["title"]), url_slug(p["url"]) + ".html"))
    return root


def toc_html(group, depth=0):
    out = ["<ul>"]
    for c in group.children:
        if isinstance(c, Group):
            out.append(f"<li><strong>{esc(c.name)}</strong>{toc_html(c, depth + 1)}</li>")
        else:
            out.append(f'<li><a href="{attr(c[1])}">{esc(c[0])}</a></li>')
    out.append("</ul>")
    return "".join(out)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} - Claude Code Docs (offline)</title>
<link rel="stylesheet" href="{root}style.css"></head>
<body data-root="{root}" data-slug="{slug}">
<button id="navtoggle" aria-label="Toggle navigation">&#9776;</button>
<aside id="nav"><a class="home" href="{root}index.html">Claude Code Docs <span>offline</span></a></aside>
<main><article>
<div class="crumbs">{crumbs}</div>
{body}
<footer>Source: <a href="{url}">{url}</a> &middot; snapshot {fetched}</footer>
</article></main>
<script src="{root}nav-data.js"></script><script src="{root}nav.js"></script>
</body></html>
"""

CSS = """:root{--bg:#faf9f5;--fg:#1f1e1d;--mut:#6b6a68;--line:#e3e0d8;--side:#f2f0e8;--acc:#c4502a;--code:#efece3;--link:#1d4ed8}
@media (prefers-color-scheme:dark){:root{--bg:#1c1b19;--fg:#ece9e1;--mut:#a09d94;--line:#37352f;--side:#242320;--acc:#e8825e;--code:#2a2926;--link:#8ab4ff}}
*{box-sizing:border-box}html{scroll-padding-top:16px}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.65 -apple-system,"Segoe UI",system-ui,sans-serif}
#nav{position:fixed;inset:0 auto 0 0;width:300px;overflow:auto;padding:16px;background:var(--side);border-right:1px solid var(--line);font-size:14px}
#nav .home{display:block;font-weight:700;color:var(--fg);text-decoration:none;margin-bottom:12px}
#nav .home span{font-weight:400;color:var(--mut);font-size:12px}
#nav input{width:100%;padding:6px 8px;margin-bottom:10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}
#nav details{margin:2px 0}#nav details details{margin-left:10px}
#nav summary{cursor:pointer;padding:3px 0;font-weight:600}
#nav details details>summary{font-weight:500;color:var(--mut)}
#nav a.leaf{display:block;padding:3px 8px;margin-left:10px;color:var(--fg);text-decoration:none;border-radius:6px}
#nav a.leaf:hover{background:var(--line)}#nav a.leaf[aria-current]{background:var(--line);font-weight:600;color:var(--acc)}
main{margin-left:300px;padding:32px 24px 80px}article{max-width:820px;margin:0 auto}
.crumbs{color:var(--mut);font-size:13px;text-transform:uppercase;letter-spacing:.04em}
h1{font-size:2.1em;line-height:1.25;margin:.3em 0 .5em}h2{margin-top:2em;padding-top:.4em;border-top:1px solid var(--line)}
h1,h2,h3,h4{line-height:1.3}.anchor{margin-left:.4em;color:var(--mut);text-decoration:none;opacity:0}
h1:hover .anchor,h2:hover .anchor,h3:hover .anchor,h4:hover .anchor{opacity:1}
a{color:var(--link)}code{background:var(--code);padding:.1em .35em;border-radius:4px;font:.88em ui-monospace,Consolas,monospace}
pre{position:relative;background:var(--code);padding:14px 16px;border-radius:8px;overflow:auto;line-height:1.5}
pre code{background:none;padding:0;font-size:.85em}
pre .copy{position:absolute;top:6px;right:6px;font-size:12px;padding:2px 8px;border:1px solid var(--line);border-radius:5px;background:var(--bg);color:var(--mut);cursor:pointer;opacity:0}
pre:hover .copy{opacity:1}
blockquote{margin:1em 0;padding:.1em 1em;border-left:4px solid var(--acc);background:var(--side);border-radius:0 6px 6px 0}
.callout{margin:1em 0;padding:.6em 1em;border-left:4px solid #3b82f6;background:var(--side);border-radius:0 6px 6px 0}
.callout>:last-child{margin-bottom:.3em}.callout-title{margin:.1em 0 .3em;font-weight:700;color:#3b82f6}
.callout.tip{border-color:#16a34a}.callout.tip .callout-title{color:#16a34a}
.callout.warning,.callout.caution{border-color:#d97706}.callout.warning .callout-title,.callout.caution .callout-title{color:#d97706}
.callout.important{border-color:#9333ea}.callout.important .callout-title{color:#9333ea}
.table-wrap{overflow-x:auto;margin:1em 0}table{border-collapse:collapse;width:100%}
th,td{border:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}th{background:var(--side)}
img,video{max-width:100%;height:auto;border-radius:6px}hr{border:0;border-top:1px solid var(--line);margin:2em 0}
footer{margin-top:4em;padding-top:1em;border-top:1px solid var(--line);color:var(--mut);font-size:13px}
.toc ul{list-style:none;padding-left:1.2em}.toc>ul{padding-left:0}.toc li{margin:.2em 0}
#navtoggle{display:none;position:fixed;top:8px;left:8px;z-index:5;font-size:20px;background:var(--side);color:var(--fg);border:1px solid var(--line);border-radius:6px}
@media (max-width:900px){#nav{transform:translateX(-100%);z-index:4;transition:transform .15s}body.navopen #nav{transform:none}
main{margin-left:0;padding-top:56px}#navtoggle{display:block}}
"""

JS = """(function(){
var root=document.body.dataset.root||"",cur=document.body.dataset.slug||"",nav=document.getElementById("nav");
var tog=document.getElementById("navtoggle");if(tog)tog.onclick=function(){document.body.classList.toggle("navopen")};
function build(nodes,parent){nodes.forEach(function(n){
 if(n.p){var a=document.createElement("a");a.className="leaf";a.href=root+n.p;a.textContent=n.t;
  if(cur&&n.p===cur+".html")a.setAttribute("aria-current","page");parent.appendChild(a)}
 else{var d=document.createElement("details"),s=document.createElement("summary");s.textContent=n.g;d.appendChild(s);build(n.c,d);parent.appendChild(d)}})}
if(nav&&window.DOCS_NAV){
 var box=document.createElement("input");box.type="search";box.placeholder="Filter pages...";nav.appendChild(box);
 var wrap=document.createElement("div");nav.appendChild(wrap);build(window.DOCS_NAV.c,wrap);
 function reset(){wrap.querySelectorAll("details").forEach(function(d){d.open=!!d.querySelector("[aria-current]")})}
 reset();var cl=wrap.querySelector("[aria-current]");if(cl)cl.scrollIntoView({block:"center"});
 box.oninput=function(){var q=box.value.trim().toLowerCase();
  wrap.querySelectorAll("a.leaf").forEach(function(a){a.style.display=!q||a.textContent.toLowerCase().indexOf(q)>=0?"":"none"});
  wrap.querySelectorAll("details").forEach(function(d){var vis=!q||Array.prototype.some.call(d.querySelectorAll("a.leaf"),function(a){return a.style.display!=="none"});
   d.style.display=vis?"":"none";if(q)d.open=vis});
  if(!q)reset()}}
function anchorKey(s){try{s=decodeURIComponent(s)}catch(e){}return s.toLowerCase().replace(/[^\\p{L}\\p{N}]/gu,"")}
function goHash(){var h=location.hash.slice(1);if(!h)return;var t;try{t=document.getElementById(decodeURIComponent(h))}catch(e){}
 if(t)return;var k=anchorKey(h);
 var c=document.querySelectorAll("article [id]");for(var i=0;i<c.length;i++){if(anchorKey(c[i].id)===k){c[i].scrollIntoView();return}}}
window.addEventListener("hashchange",goHash);goHash();
document.querySelectorAll("pre").forEach(function(pre){var b=document.createElement("button");b.className="copy";b.textContent="Copy";
 b.onclick=function(){var t=pre.querySelector("code").innerText;
  function done(){b.textContent="Copied";setTimeout(function(){b.textContent="Copy"},1200)}
  if(navigator.clipboard&&window.isSecureContext)navigator.clipboard.writeText(t).then(done);
  else{var x=document.createElement("textarea");x.value=t;document.body.appendChild(x);x.select();document.execCommand("copy");x.remove();done()}};
 pre.appendChild(b)});
})();
"""


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    src = argv[0]
    out = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(src)), "html")
    snap = json.load(open(src, encoding="utf-8"))
    pages = snap["pages"]
    assert all(p["content"] is not None for p in pages), "content 가 없는 페이지가 있습니다 (fetch 실패)"

    targets = {norm(p["url"]): url_slug(p["url"]) for p in pages}
    for old, new in snap.get("redirects", {}).items():
        targets[norm(old)] = url_slug(new)

    os.makedirs(out, exist_ok=True)
    assets_src = os.path.join(os.path.dirname(os.path.abspath(src)), snap.get("assets_dir", ""))
    if snap.get("assets_dir") and os.path.isdir(assets_src):
        shutil.copytree(assets_src, os.path.join(out, "assets"), dirs_exist_ok=True)

    page_ids, page_links, tag_stats = {}, [], 0
    for p in pages:
        slug = url_slug(p["url"])
        r = Renderer(slug, targets, p.get("assets", {}))
        body = r.render(p["content"])
        page_ids[slug] = r.used_ids
        page_links += [(slug, t, f) for t, f in r.links]
        cat = p["category"]
        crumbs = " / ".join(esc("Unlisted" if c == "_unlisted" else c) for c in [cat[0]] + cat[2:])
        root = "../" * slug.count("/")
        path = os.path.join(out, *(slug + ".html").split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(PAGE.format(title=esc(p["title"]), root=root, slug=slug, crumbs=crumbs, body=body,
                                url=attr(norm(p["url"])), fetched=snap.get("fetched_at", "")))

    tree = build_tree(pages)
    with open(os.path.join(out, "nav-data.js"), "w", encoding="utf-8") as f:
        f.write("window.DOCS_NAV=" + json.dumps(tree.to_json(), ensure_ascii=False) + ";\n")
    for name, text in (("style.css", CSS), ("nav.js", JS)):
        with open(os.path.join(out, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    index_body = (f"<h1>Claude Code Docs <small>(offline snapshot)</small></h1>"
                  f"<p>Snapshot {snap.get('fetched_at', '')} &middot; {len(pages)} pages &middot; source "
                  f'<a href="{attr(snap.get("source", ""))}">{esc(snap.get("source", ""))}</a></p>'
                  f'<div class="toc">{toc_html(tree)}</div>')
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(PAGE.format(title="Index", root="", slug="", crumbs="", body=index_body, url=attr(snap.get("source", "")),
                            fetched=snap.get("fetched_at", "")))

    # self-check: 변환된 내부 링크가 가리키는 파일과 앵커가 실제로 있는지
    # (앵커는 사이트 규칙과 구두점 처리가 달라, nav.js 의 폴백과 같이 영숫자만 비교)
    missing_files = [(s, t) for s, t, _ in page_links if not os.path.isfile(os.path.join(out, *(t + ".html").split("/")))]
    anchor_keys = {s: {anchor_key(i) for i in ids} for s, ids in page_ids.items()}
    bad_anchors = sorted({(s, t, f) for s, t, f in page_links if f and anchor_key(f) not in anchor_keys.get(t, ())})
    print(f"페이지 {len(pages)}개 -> {out}")
    print(f"내부 링크 {len(page_links)}개 변환, 없는 파일 {len(missing_files)}개, 없는 앵커 {len(bad_anchors)}개")
    for s, t, f in bad_anchors[:10]:
        print(f"  앵커 없음: {s} -> {t}#{f}")
    return len(missing_files)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
