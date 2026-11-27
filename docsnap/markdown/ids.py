"""헤딩·아코디언 id 부여와, 다른 언어판의 id 를 순서대로 빌려 쓰는 규칙. Renderer 의 믹스인.

쓰는 상태: ids, used_ids, head_ids, acc_ids, hint, hint_pos, acc_hint, acc_pos.
"""
from .syntax import heading_slug


class IdMixin:
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
