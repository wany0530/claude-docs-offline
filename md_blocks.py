"""블록 마크다운(문단·제목·코드 블록·목록·표·HTML 블록)의 순회. Renderer 의 믹스인.

상태는 갖지 않는다. 인용 덩어리는 quote_block(ComponentMixin), 인라인은 inline(InlineMixin), 헤딩 id 는 heading_id(IdMixin)에 맡기고,
읽고 쓰는 heads 는 Renderer 가 소유한다.
"""
import html
import re

from md_syntax import BLOCK_HTML, FENCE, HEAD, HR, HTML_START, ITEM, QUOTE, TABLE_SEP, esc, indent_of


class BlockMixin:
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
                i = self.quote_block(lines, i, out)
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
