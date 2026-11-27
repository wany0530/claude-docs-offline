"""Mintlify 컴포넌트(탭·아코디언·카드)와 GitHub 식 콜아웃·인용·제목 아래 설명문. Renderer 의 믹스인.

읽는/쓰는 상태: tab_n, lead_done. 다른 믹스인의 blocks / inline / accordion_id 를 self 로 호출한다.
"""
import re

from md_syntax import MARKER, QUOTE


class ComponentMixin:
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

    def quote_block(self, lines, i, out):
        """lines[i] 에서 시작하는 > 인용 덩어리 하나를 HTML 로 바꿔 out 에 덧붙이고 다음 위치를 돌려준다."""
        inner, i = self.quote_run(lines, i)
        mk = MARKER.match(inner[0]) if inner else None
        if mk and mk.group(1) == "tab":  # 연속된 > [tab] 블록들은 하나의 탭 그룹
            tabs = [(mk.group(2) or "", inner[1:])]
            while (nxt := self.next_marked(lines, i, "tab")):
                tabs.append(nxt[:2])
                i = nxt[2]
            out.append(self.tab_group(tabs))
            return i
        if mk and mk.group(1) == "accordion":
            title = self.inline(mk.group(2) or "")
            aid = self.accordion_id(title)  # 제목이 같은 slug 규칙의 id: 본문 링크(#제목)가 아코디언을 가리킨다
            out.append(f'<details class="accordion" id="{aid}"><summary>{title}</summary>'
                       f"{self.blocks(inner[1:])}</details>")
            return i
        if mk:  # card: 연속된 카드는 격자로 묶는다
            cards = [(mk.group(2) or "", inner[1:])]
            while (nxt := self.next_marked(lines, i, "card")):
                cards.append(nxt[:2])
                i = nxt[2]
            out.append('<div class="cards">' + "".join(
                f'<div class="card"><div class="card-title">{self.inline(t)}</div>{self.blocks(b)}</div>'
                for t, b in cards) + "</div>")
            return i
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
        return i
