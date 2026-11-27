"""마크다운 -> HTML 변환기(Mintlify 컴포넌트 포함)와 검색용 평문 변환. 표준 라이브러리만 사용.

Renderer 가 페이지 1개를 HTML 로 바꾸고, 헤딩·아코디언 id 와 링크 목록을 모아 둔다 (앵커 확정은 docs_anchors).
구현은 역할별 믹스인으로 나뉘어 있다:
  md_syntax      정규식과 상태 없는 함수 (esc, attr, anchor_key, strip_banner, plain_text ...)
  md_inline      InlineMixin     인라인(강조·코드·링크·이미지)과 주소 변환
  md_ids         IdMixin         헤딩·아코디언 id 와 다른 언어판 id 빌려 쓰기
  md_components  ComponentMixin  탭·아코디언·카드·콜아웃·인용
  md_structures  StructureMixin  표와 목록
  md_blocks      BlockMixin      문단·제목·코드 블록·HTML 블록과 블록 순회
이 모듈은 상태를 소유하고 믹스인을 묶는 파사드다. 기존 import(from docs_markdown import ...)는 그대로 동작한다.
"""
from .blocks import BlockMixin
from .components import ComponentMixin
from .ids import IdMixin
from .inline import InlineMixin
from .structures import StructureMixin
from .syntax import (ALLOWED_TAGS, BLOCK_HTML, anchor_key, attr, esc, esc_text, heading_slug, indent_of, plain_text,  # noqa: F401
                       strip_banner)

__all__ = ["Renderer", "ALLOWED_TAGS", "BLOCK_HTML", "anchor_key", "attr", "esc", "esc_text", "heading_slug", "indent_of",
           "plain_text", "strip_banner"]


class Renderer(InlineMixin, IdMixin, ComponentMixin, StructureMixin, BlockMixin):
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

    def render(self, content):
        return self.blocks(strip_banner(content))  # 모든 페이지 맨 위의 안내문은 제거
