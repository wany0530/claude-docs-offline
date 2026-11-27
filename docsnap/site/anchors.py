"""링크의 #앵커를 모든 페이지의 id 가 정해진 뒤 실제 id 로 확정하고, 검토 장부·수동 확인 힌트를 만든다.

exact -> key(구두점만 다름) -> strict(단어가 하나의 id 에만 모두 들어 있음) -> stale(페이지 처음으로 연결).
결과 집계는 REPORT 에 담기며 빌드 스크립트가 로그로 옮긴다. 표준 라이브러리만 사용.
"""
import json
import os
import re
import urllib.parse
from posixpath import dirname as pdirname, relpath as prelpath

from docsnap.markdown import anchor_key, attr


def _tokens(s):
    """앵커·id 를 단어 집합으로 (소문자, 끝의 복수 s 만 정규화). 단어 일치 보정에 쓴다."""
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in re.findall(r"\w+", urllib.parse.unquote(s).lower())}


def resolve_anchor(frag, ids):
    """링크의 앵커 frag 를 대상 페이지의 실제 id 집합 ids 에 맞춰 확정한다. (분류, 쓸 앵커)를 돌려준다.

    exact: 그대로 있음 / key: 구두점·대소문자만 달라 실제 id 로 바꿈 /
    strict: 앵커의 모든 단어를 포함하는 id 가 **정확히 하나**일 때만 그 id (업스트림 제목이 길어진 경우) /
    stale: 어느 것도 아님 (원문에서 이름이 바뀌었거나 사라진 섹션. 페이지 처음으로 연결한다)."""
    if frag in ids or urllib.parse.unquote(frag) in ids:
        return "exact", frag
    key = anchor_key(frag)
    same = sorted(i for i in ids if anchor_key(i) == key)
    if same:
        return "key", same[0]
    want = _tokens(frag)
    if want:
        cand = sorted(i for i in ids if want <= _tokens(i))
        if len(cand) == 1:
            return "strict", cand[0]
    return "stale", ""


HINT_MIN = 0.6  # 끊김 링크의 최근접 후보를 로그에 힌트로 보여 줄 최소 단어 겹침(자카드)


def nearest_id(frag, ids):
    """frag 와 단어가 가장 많이 겹치는 id 를 (겹침 비율, id) 로 돌려준다. 링크를 바꾸지 않고 사람이 볼 힌트로만 쓴다."""
    want = _tokens(frag)
    best = (0.0, "")
    for i in sorted(ids):
        t = _tokens(i)
        if want and t:
            j = len(want & t) / len(want | t)
            if j > best[0]:
                best = (j, i)
    return best


LEDGER_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "reviewed_anchors.json")


def ledger_key(target, frag):
    """'en/agent-sdk/mcp' + 'in-code' -> 'agent-sdk/mcp#in-code' (언어 접두어를 뗀다: 두 언어가 같은 앵커를 쓴다)."""
    return target.split("/", 1)[1] + "#" + frag


def load_ledger(path=None):
    """사람이 확인한 단어 일치 보정 장부 {키: 연결한 id}. 파일이 없으면 빈 장부."""
    path = LEDGER_PATH if path is None else path
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("pairs", {})


def compare_ledger(strict, ledger):
    """strict: {(출처, 대상, 앵커, 연결한 id)} -> (장부에 없는 새 보정, 장부와 다른 id 로 보정된 것). 둘 다 고유 목록."""
    new, changed = set(), set()
    for _, target, frag, got in strict:
        k = ledger_key(target, frag)
        want = ledger.get(k)
        if want is None:
            new.add((k, got))
        elif want != got:
            changed.add((k, want, got))
    return sorted(new), sorted(changed)


DEFERRED = re.compile(r'href="\x01(\d+)\x01"')
LOCAL_ANCHOR = re.compile(r'(<a\s[^>]*?)href="#([^"]+)"')  # 같은 페이지 안의 #앵커 링크 (코드 예시 속 글자는 &lt;a 라 걸리지 않음)


def resolve_anchors(slug, body, links, page_ids, stale_title, report):
    """본문의 앵커 링크를 실제 id 로 확정한다 (다른 페이지로 가는 링크 + 같은 페이지 안의 #링크).
    확정 결과는 report 에 센다. 끊긴 링크(stale)에는 class="stale-anchor" 와 안내 title 을 붙이고 앵커를 뺀다."""
    here = pdirname(slug + ".html") or "."

    def settle(target, frag):
        kind, new = resolve_anchor(frag, page_ids.get(target, ()))
        report["counts"][kind] += 1
        if kind in ("key", "strict", "stale"):
            report[kind].add((slug, target, frag, new))
        if kind == "stale":  # 단어가 많이 겹치는 후보가 있으면 사람이 볼 힌트로만 남긴다 (링크는 바꾸지 않는다)
            score, cand = nearest_id(frag, page_ids.get(target, ()))
            if score >= HINT_MIN:
                report["hint"].add((slug, target, frag, cand))
        return kind, new

    def deferred(m):
        target, frag = links[int(m.group(1))]
        rel = prelpath(target + ".html", here)
        kind, new = settle(target, frag)
        if kind == "stale":
            return f'href="{attr(rel)}" class="stale-anchor" title="{attr(stale_title)}"'
        return f'href="{attr(rel)}#{attr(new)}"'

    def local(m):
        if 'class="anchor"' in m.group(1):  # 헤딩 옆의 # 링크: 자기 자신을 가리키므로 항상 맞다
            return m.group(0)
        frag = m.group(2)
        kind, new = settle(slug, frag)
        if kind == "exact":
            return m.group(0)
        if kind == "stale":
            return f'{m.group(1)}href="#" class="stale-anchor" title="{attr(stale_title)}"'
        return f'{m.group(1)}href="#{attr(new)}"'

    return LOCAL_ANCHOR.sub(local, DEFERRED.sub(deferred, body))


REPORT = {}  # 마지막 main() 실행의 링크 검사 결과 (빌드 스크립트가 로그에 옮긴다)
