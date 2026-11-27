"""인라인 마크다운(강조·코드·링크·이미지)과 주소 변환. Renderer 의 믹스인.

읽는 상태: slug, targets, assets, defer_anchors. 쓰는 상태: links.
"""
import html
import re
from posixpath import dirname as pdirname, relpath as prelpath

from docs_common import norm
from md_syntax import (ALLOWED_TAGS, BARE_URL, CODE_SPAN, DEL, EM, ESCAPED, IMAGE, LINK, STRONG, TAG, URL_ATTR, attr,
                       esc, esc_text)


class InlineMixin:
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
