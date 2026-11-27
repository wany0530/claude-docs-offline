"""표와 목록 마크다운. Renderer 의 믹스인.

상태는 갖지 않는다. 셀과 항목의 내용은 inline(InlineMixin)과 blocks(BlockMixin)에 맡긴다.
"""
import re

from .syntax import HR, ITEM, indent_of


class StructureMixin:
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

        out = ["<div class=\"table-wrap\" tabindex=\"0\"><table><thead><tr>"]
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
