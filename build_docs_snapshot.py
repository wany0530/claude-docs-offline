#!/usr/bin/env python3
"""Claude Code 공식 문서(영어 + 공식 한국어판)를 지금(오늘 날짜) 기준으로 다시 수집해 오프라인 사이트를 갱신합니다.

사용법:  (인터넷 연결 후)  python build_docs_snapshot.py [출력폴더] [로그폴더]
         기본값은 이 스크립트가 있는 폴더의 output/ 과 logs/ 입니다 (어디서 실행해도 같음).
결과:    <출력폴더>/site/         최신 오프라인 사이트 1벌 (en/ ko/ assets/ ...). 브라우저로 여는 유일한 사본
         <출력폴더>/index.html    site/ 로 이동하는 바로가기
         <출력폴더>/history/YYYY-MM-DD.json.gz   그날의 원본 데이터(docs.json) 1벌. 최근 KEEP_HISTORY 회분만 보관
         <출력폴더>/history/YYYY-MM-DD.diff      직전 이력 대비 바뀐 페이지의 전체 diff (변경이 있을 때만)
         <로그폴더>/YYYY/YYYY-MM-DD_HHMMSS.log   실행 1회당 로그 1개: 결과, 수집 요약, 직전 이력 대비 변경 요약,
                                                구역별 역할 설명, 콘솔 출력
임의의 두 날짜 비교는 docs_diff.py 를 쓰세요.

안전장치: 인터넷이 안 되면 기존 사이트는 건드리지 않고 종료합니다(로그 파일만 남음). 빌드는 <출력폴더>/.building 에서
하고, 모든 페이지 수집(영어·한국어)과 변환이 성공했을 때만 site/ 를 교체합니다. 표준 라이브러리만 사용합니다.
"""
import collections
import gzip
import io
import os
import re
import shutil
import sys
import time
import traceback
from datetime import date, datetime

import docs_diff
import docs_fetch_json
import docs_anchors
import docs_json_to_html
import docs_verify
from docs_common import setup_console

KEEP_HISTORY = 30  # 남겨둘 이력(날짜별 docs.json.gz 와 .diff) 개수. 오래된 것부터 지운다. 다음 비교의 기준이 되므로 최소 1.
HISTORY_DIR = "history"
SITE_DIR = "site"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "output")  # 실행 위치와 무관하게 스크립트 폴더 기준
DEFAULT_LOGS = os.path.join(HERE, "logs")
SNAP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # 옛 구조의 날짜 폴더 이름 (이전 버전이 만든 output/YYYY-MM-DD/)
HIST_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json\.gz$")  # 이력 파일 이름
FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def log(msg):
    print(msg, file=sys.stderr)


# ---------- 변경 요약 ----------
def split_sections(content):
    """본문을 헤딩 기준 섹션 {헤딩: 본문}으로 나눈다 (코드블록 안의 # 는 헤딩이 아님)."""
    secs, seen, cur, buf, infence = {}, {}, "(intro)", [], False
    for line in content.split("\n"):
        if FENCE_RE.match(line):
            infence = not infence
        m = None if infence else HEAD_RE.match(line)
        if m:
            secs[cur] = "\n".join(buf).strip()
            title = re.sub(r"[`*_]", "", m.group(2))
            seen[title] = seen.get(title, 0) + 1
            cur, buf = (title if seen[title] == 1 else f"{title} ({seen[title]})"), []
        else:
            buf.append(line)
    secs[cur] = "\n".join(buf).strip()
    return secs


def useful(line):
    s = line.strip()
    return len(s) >= 4 and re.search(r"\w", s) is not None and not s.startswith(("> ## Documentation", "> Fetch the", "> Use this"))


def short(s, n=140):
    s = re.sub(r"\s+", " ", s.strip())
    return s if len(s) <= n else s[: n - 1] + "…"


def names(items, k=8):
    shown = ", ".join(f"`{short(i, 60)}`" for i in items[:k])
    return shown + (f" 외 {len(items) - k}개" if len(items) > k else "")


def page_label(p):
    return f"**{p['title']}** (`{p['url'].split('/docs/', 1)[1].removesuffix('.md')}`)"


def summarize_change(old, new):
    so, sn = split_sections(old), split_sections(new)
    added = [k for k in sn if k not in so and k != "(intro)"]
    gone = [k for k in so if k not in sn and k != "(intro)"]
    edited = [k for k in sn if k in so and sn[k] != so[k]]
    old_lines = [l.strip() for l in old.split("\n") if useful(l)]
    new_lines = [l.strip() for l in new.split("\n") if useful(l)]
    oset, nset = set(old_lines), set(new_lines)
    add_l = list(dict.fromkeys(l for l in new_lines if l not in oset))
    rem_l = list(dict.fromkeys(l for l in old_lines if l not in nset))
    out = []
    if added:
        out.append(f"  - 새 섹션: {names(added)}")
    if gone:
        out.append(f"  - 삭제된 섹션: {names(gone)}")
    if edited:
        out.append(f"  - 내용이 바뀐 섹션: {names(edited)}")
    out += [f"  - 추가: {short(l)}" for l in add_l[:3]]
    out += [f"  - 삭제: {short(l)}" for l in rem_l[:3]]
    return out, len(add_l), len(rem_l)


def prev_label(path):
    """비교 대상 표시: 이력 파일이면 'history/날짜.json.gz', 스냅샷이면 '날짜/docs.json'."""
    base = os.path.basename(path)
    return f"{HISTORY_DIR}/{base}" if HIST_RE.match(base) else f"{os.path.basename(os.path.dirname(path))}/{base}"


def make_entry(prev_path, snap):
    """직전 스냅샷 대비 변경 요약. (본문 줄 목록, (추가, 삭제, 변경) 개수 또는 None) 반환."""
    if prev_path is None:
        return ["이전 스냅샷이 없어 비교하지 않았습니다 (최초 수집).", ""], None
    prev = docs_diff.open_json(prev_path)
    new_p, old_p = {p["url"]: p for p in snap["pages"]}, {p["url"]: p for p in prev["pages"]}
    added = [new_p[u] for u in new_p if u not in old_p]
    removed = [old_p[u] for u in old_p if u not in new_p]
    changed = [u for u in new_p if u in old_p and new_p[u]["content"] != old_p[u]["content"]]
    lines = [f"비교 대상: {prev_label(prev_path)} (수집일 {prev.get('fetched_at', '?')})", "",
             f"추가 {len(added)}개 · 삭제 {len(removed)}개 · 내용 변경 {len(changed)}개 · "
             f"변경 없음 {len(new_p) - len(added) - len(changed)}개", ""]
    if added:
        lines += ["### 추가된 페이지", ""]
        for p in added:
            heads = [k for k in split_sections(p["content"]) if k != "(intro)"]
            lines.append(f"- {page_label(p)}: {p['description'] or '(설명 없음)'}")
            if heads:
                lines.append(f"  - 섹션: {names(heads)}")
        lines.append("")
    if removed:
        lines += ["### 삭제된 페이지", ""] + [f"- {page_label(p)}" for p in removed] + [""]
    if changed:
        lines += ["### 내용이 바뀐 페이지", ""]
        for u in changed:
            detail, n_add, n_rem = summarize_change(old_p[u]["content"], new_p[u]["content"])
            delta = len(new_p[u]["content"]) - len(old_p[u]["content"])
            lines.append(f"- {page_label(new_p[u])} — {delta:+d}자 (추가 {n_add}줄 · 삭제 {n_rem}줄)")
            lines += detail
        lines.append("")
    return lines, (len(added), len(removed), len(changed))


# ---------- 실행 로그 ----------
# 모든 로그 끝에 붙는 설명표. "변경 요약"의 추가/삭제/수정 항목이 각각 무엇을 알려 주는지 정리한 것이다.
# (규칙 기반 비교이므로 아래 '신호'는 확정이 아니라 확인할 단서다.)
LOG_GUIDE = """
| 구역 | 담기는 것 | 얻을 수 있는 정보 / 하는 역할 |
|---|---|---|
| 결과·시간 | 성공/실패/오류, 시작·종료·소요 시간 | 언제 갱신을 시도했고 결과를 믿어도 되는지 판단한다. 실패해도 스냅샷은 그대로이므로 오프라인 사본이 몇 월 며칠 기준인지 알 수 있다. |
| 수집 요약 | 페이지·에셋 수, 별칭, 숨은 페이지, 비문서·미확인 링크 수, 공식 한국어판 수집·없음 수 | 수집이 빠짐없이 됐는지 점검한다. 페이지 수가 갑자기 줄거나 미확인 링크가 늘면 사이트 구조 변경이나 수집 문제의 단서다. 한국어판 없음이 늘면 공식 한글 문서가 영어보다 뒤처졌다는 뜻이다(번역은 하지 않고 영어 원문을 대신 보여 준다). |
| 수집 실패 | 받지 못한 영어·한국어 페이지와 에셋의 주소, 마지막 오류 | 빌드가 중단된 원인을 바로 찾는다(일시적 네트워크 오류인지, 주소가 사라졌는지). 실패가 있으면 기존 사이트는 그대로 둔다. |
| 링크 검증 | 페이지 안팎 앵커 링크의 확정 결과(그대로/보정/페이지 처음으로 연결)와 목록, 없는 파일 수, 한국어 id 일치 | 오프라인 사본의 링크 품질을 보여 준다. "페이지 처음으로 연결" 목록은 공식 문서가 섹션 이름을 바꾸거나 지워 대상이 사라진 링크이고, 늘어나면 공식 문서가 크게 개편됐다는 단서다. "단어 일치 보정"은 제목이 길어진 섹션을 자동으로 이어 준 것이라, 장부(reviewed_anchors.json)에 없는 새 보정은 "검토 필요"로 따로 나온다. "독립 검사"는 변환기 코드를 쓰지 않고 결과 HTML 만 다시 읽어 모든 링크의 대상 파일·앵커·중복 id 를 확인한 것이고, 위반이 있으면 빌드가 중단된다(대상이 존재한다는 것만 보장하며 섹션이 의미상 맞는지는 장부와 사람의 판단이다). "수동 확인 후보"는 끊긴 링크와 비슷한 제목이 있다는 힌트일 뿐 링크는 바뀌지 않았다. |
| 경고: 한국어 메뉴 이름 | 영어·한국어 메뉴 개수가 달라 짝짓지 못한 탭·그룹 | 이 경고가 있으면 한국어 사이트 메뉴에 영어 이름이 남는다. 공식 사이트 메뉴 구조가 바뀐 신호이므로 `korean_names` 를 점검한다. |
| 추가된 페이지 | 새로 생긴 페이지의 제목·주소·설명·섹션 목록 | 공식 문서에 새 기능이나 가이드가 생겼다는 단서다. 오프라인 사본에 이번에 처음 들어온 내용이라 먼저 읽어 볼 대상을 고르는 데 쓴다. |
| 삭제된 페이지 | 공식 문서에서 사라진 페이지의 제목·주소 | 기능 폐지, 문서 통합, 주소 이동의 단서다. 사이트(site/)에서는 사라지지만 본문은 history/ 에 최근 KEEP_HISTORY 회분 남아 있다. 북마크와 링크를 점검한다. |
| 내용이 바뀐 페이지 | 글자 수 증감, 추가·삭제된 줄 수 | 변경의 규모를 보여 준다. 크게 늘었으면 새 내용이 붙은 것이고, 증감이 거의 없으면 문구 수정이나 오탈자일 가능성이 크다. |
| 새 섹션 | 기존 페이지에 새로 생긴 소제목 | 이미 있는 페이지에 새 절차, 옵션, 기능이 추가됐다는 단서다. 새로 알아야 할 내용이 어디인지 바로 짚어 준다. |
| 삭제된 섹션 | 기존 페이지에서 사라진 소제목 | 폐지, 이동, 통합의 단서다. 내가 쓰던 방법이 더 이상 안내되지 않는지 확인한다. |
| 내용이 바뀐 섹션 | 소제목은 그대로이고 본문이 달라진 섹션 | 동작, 옵션, 주의사항이 수정됐다는 단서다. 이미 아는 내용 중 다시 확인할 곳을 좁혀 준다. |
| 추가/삭제된 대표 줄 | 바뀐 줄의 원문 일부(각 3개, 140자까지) | 무엇이 어떻게 바뀌었는지 근거를 보여 준다(버전, 명령어, 옵션 이름 등). 페이지를 열지 않고도 변화 내용을 파악한다. 전체 변경은 diff 파일에 있다. |
| 전체 diff | 바뀐 페이지별 unified diff 파일 경로 (output/history/날짜.diff) | 대표 줄로 부족할 때 실제 변경 전문을 확인한다. 임의의 두 날짜는 `python docs_diff.py 날짜1 날짜2 [페이지]` 로 비교한다. |
| 정리 | 이번에 지운 옛 구조의 날짜 폴더와 오래된 이력 | 디스크에서 무엇이 사라졌는지 알려 준다. 이력(history)에서 최근 KEEP_HISTORY 회분 본문은 복원할 수 있다. |
| 콘솔 출력 | 실행 중 화면에 나온 내용 전부 | 실패 원인 추적과 경고(앵커 불일치 등) 확인에 쓴다. |
"""


class Tee:
    """stdout/stderr 를 대신해 화면과 공용 버퍼에 동시에 쓴다 (로그에 콘솔 출력 전체를 남기기 위함)."""

    def __init__(self, stream, buf):
        self.stream, self.buf = stream, buf

    def write(self, s):
        self.buf.write(s)
        return self.stream.write(s)

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):  # encoding, isatty 등은 원래 스트림 것을 그대로 사용
        return getattr(self.stream, name)


def write_log(log_dir, start, end, out_dir, state, console):
    """실행 1회의 로그를 <log_dir>/YYYY/YYYY-MM-DD_HHMMSS.log 로 저장하고 경로를 돌려준다."""
    year_dir = os.path.join(log_dir, start.strftime("%Y"))
    os.makedirs(year_dir, exist_ok=True)
    stem = os.path.join(year_dir, start.strftime("%Y-%m-%d_%H%M%S"))
    path, n = stem + ".log", 1
    while os.path.exists(path):  # 같은 초에 두 번 실행해도 덮어쓰지 않음
        n += 1
        path = f"{stem}_{n}.log"
    lines = [f"# 실행 로그 {start:%Y-%m-%d %H:%M:%S}", "",
             f"- 결과: {state['result']}",
             f"- 시작 {start:%H:%M:%S} · 종료 {end:%H:%M:%S} · 소요 {int((end - start).total_seconds())}초",
             f"- 출력 폴더: {os.path.abspath(out_dir)}"]
    if state.get("name"):
        lines.append(f"- 스냅샷 날짜: {state['name']}")
    c = state.get("collect")
    if c:
        lines += ["", "## 수집 요약",
                  f"- 페이지 {c['pages']}개 (실패 {c['failed']}), 별칭 {c['redirects']}개, 숨은 페이지 {c['unlisted']}개",
                  f"- 공식 한국어판 {c['ko']}개, 한국어판 없음(영어 원문 대체) {c['ko_missing']}개",
                  f"- 비문서 링크 {c['non_page']}개, 미확인 링크 {c['unresolved']}개",
                  f"- 에셋 {c['assets']}개 (실패 {c['asset_errors']})"]
    if state.get("failures"):
        lines += ["", "## 수집 실패 (주소와 마지막 오류)", "", "| 주소 | 오류 |", "|---|---|"]
        lines += [f"| {u} | {str(e).replace('|', '/')[:160]} |" for u, e in state["failures"]]
    lk = state.get("links")
    if lk:
        c = lk["counts"]
        lines += ["", "## 링크 검증",
                  f"- 앵커 링크 {sum(c.values())}건: 그대로 {c.get('exact', 0)}, 대소문자·구두점 보정 {c.get('key', 0)}, "
                  f"단어 일치 보정 {c.get('strict', 0)}, 원문에서 사라져 페이지 처음으로 연결 {c.get('stale', 0)}",
                  f"- 없는 파일을 가리키는 링크 {lk['missing_files']}개, 한국어 id 빌려 쓰기 헤딩 {lk['ko_heading_full'][0]}/{lk['ko_heading_full'][1]}"
                  f"·아코디언 {lk['ko_accordion_full'][0]}/{lk['ko_accordion_full'][1]}페이지 일치"]
        vf = lk.get("verify")
        if vf:
            vc = vf["counts"]
            lines.append(f"- 독립 검사(결과 HTML 을 다시 읽음): 페이지 {vc.get('pages', 0)}개, 링크 {vc.get('links', 0)}건"
                         f"(앵커 {vc.get('anchors', 0)}건), 끊김 표시 {vc.get('stale', 0)}건 -> 위반 {len(vf['problems'])}건")
        if lk.get("unreviewed") or lk.get("ledger_changed"):
            lines.append(f"- **검토 필요**: 장부(reviewed_anchors.json)에 없는 새 보정 {len(lk.get('unreviewed', []))}건, "
                         f"장부와 다르게 보정된 것 {len(lk.get('ledger_changed', []))}건. 확인한 뒤 장부에 추가하거나 고친다.")
            lines += [f"  - 새 보정: {k} → #{got}" for k, got in lk.get("unreviewed", [])]
            lines += [f"  - 장부와 다름: {k} 장부 #{want} / 이번 #{got}" for k, want, got in lk.get("ledger_changed", [])]
        elif lk.get("strict"):
            lines.append("- 새 보정 없음: 단어 일치 보정은 모두 장부에 있는 검토 완료 항목이다.")
        if lk["stale"]:
            stale_en = collections.Counter((t, f) for s, t, f, _ in lk["stale"] if s.startswith("en/"))
            lines.append(f"- 페이지 처음으로 연결된 링크: 영어판 고유 {len(stale_en)}건(링크한 페이지 기준 {sum(stale_en.values())}곳). "
                         f"한국어판도 같은 링크이며, 아래는 영어판 기준 (대상#원래 앵커, 링크한 페이지 수):")
            lines += [f"  - {t}#{f} ({n}곳)" for (t, f), n in sorted(stale_en.items())]
        hints = sorted({(t, f, x) for s, t, f, x in lk.get("hints", []) if s.startswith("en/")})
        if hints:
            lines.append(f"- 수동 확인 후보 {len(hints)}건 (끊긴 링크 중 단어가 많이 겹치는 섹션이 있는 것. 링크는 바꾸지 않았다. 앞이 원래 앵커 ~ 뒤가 후보):")
            lines += [f"  - {t}#{f} ~ #{x}" for t, f, x in hints]
        if lk["strict"]:
            strict_en = collections.Counter((t, f, n) for s, t, f, n in lk["strict"] if s.startswith("en/"))
            lines.append(f"- 단어 일치로 보정한 링크: 영어판 고유 {len(strict_en)}건 (대상#원래 앵커 → 연결한 섹션, 링크한 페이지 수):")
            lines += [f"  - {t}#{f} → #{n} ({c}곳)" for (t, f, n), c in sorted(strict_en.items())]
    if state.get("nav_mismatch"):
        lines += ["", "## 경고: 한국어 메뉴 이름"] + [f"- {m}" for m in state["nav_mismatch"]] + [
            "- 개수가 달라 짝짓지 못한 이름은 영어 그대로 보입니다. 공식 사이트 메뉴 구조가 바뀐 신호일 수 있습니다."]
    if state.get("change_lines"):
        lines += ["", "## 변경 요약", ""] + state["change_lines"]
    if state.get("removed") or state.get("removed_history"):
        lines += ["", "## 정리"]
        if state.get("removed"):
            lines.append(f"- 지운 옛 구조의 날짜 폴더: {', '.join(state['removed'])}")
        if state.get("removed_history"):
            lines.append(f"- 지운 오래된 이력: {', '.join(state['removed_history'])}")
    if state.get("traceback"):
        lines += ["", "## 오류", "```", state["traceback"].rstrip(), "```"]
    lines += ["", "## 이 로그 읽는 법 (구역별로 얻을 수 있는 정보와 역할)", ""] + LOG_GUIDE.strip().split("\n")
    lines += ["", "## 콘솔 출력 전체", "```", console.rstrip(), "```", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    return path


# ---------- 정리 ----------


def snapshot_dirs(out_dir):
    """스냅샷 날짜 폴더 이름들 (오래된 순)."""
    return sorted(n for n in os.listdir(out_dir)
                  if SNAP_RE.match(n) and os.path.isdir(os.path.join(out_dir, n)))


def history_dir(out_dir):
    return os.path.join(out_dir, HISTORY_DIR)


def history_dates(out_dir):
    """보관된 이력의 날짜들 (오래된 순)."""
    d = history_dir(out_dir)
    if not os.path.isdir(d):
        return []
    return sorted(m.group(1) for m in map(HIST_RE.match, os.listdir(d)) if m)


def find_previous(out_dir, name):
    """직전 비교 대상 JSON 경로. 우선순위: 오늘 이전 가장 최근 이력 > 오늘이 아닌 가장 최근 스냅샷 > 오늘 스냅샷(같은 날 재실행)."""
    older = [d for d in history_dates(out_dir) if d < name]
    if older:
        return os.path.join(history_dir(out_dir), older[-1] + ".json.gz")
    found = [os.path.join(out_dir, n, "docs.json") for n in snapshot_dirs(out_dir)]
    found = [p for p in found if os.path.exists(p)]
    others = [p for p in found if os.path.basename(os.path.dirname(p)) != name]
    return (others or found or [None])[-1]


def save_history(out_dir, name, json_path, prev_path, snap):
    """오늘 docs.json 을 gzip 으로 보관하고, 직전 대비 전체 diff 를 저장한다. diff 파일 경로(없으면 None)를 돌려준다."""
    d = history_dir(out_dir)
    os.makedirs(d, exist_ok=True)
    with open(json_path, "rb") as src, gzip.open(os.path.join(d, name + ".json.gz"), "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst)
    diff_path = os.path.join(d, name + ".diff")
    if prev_path is None:
        if os.path.exists(diff_path):
            os.remove(diff_path)
        return None
    chunks = docs_diff.diff_snapshots(docs_diff.open_json(prev_path), snap)
    if not chunks:
        if os.path.exists(diff_path):
            os.remove(diff_path)
        return None
    with open(diff_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# 비교: {prev_label(prev_path)} -> {name}\n\n" + "\n".join(chunks))
    return diff_path


def prune_history(out_dir, keep):
    """최신 keep 개 날짜의 이력(.json.gz, .diff)만 남기고 지운다. 지운 날짜 목록을 돌려준다."""
    removed = history_dates(out_dir)[:-keep] if keep > 0 else history_dates(out_dir)
    for d in removed:
        for ext in (".json.gz", ".diff"):
            path = os.path.join(history_dir(out_dir), d + ext)
            if os.path.exists(path):
                os.remove(path)
    return removed


def remove_legacy_dirs(out_dir):
    """이전 버전이 만든 output/YYYY-MM-DD/ 폴더(docs.json, assets, html 중복본)를 지운다. 지운 이름들을 돌려준다."""
    removed = snapshot_dirs(out_dir)
    for n in removed:
        shutil.rmtree(os.path.join(out_dir, n))
    return removed


SWAP_RETRIES, SWAP_DELAY = 6, 1.0  # Windows 에서 브라우저·IDE 가 폴더를 잠깐 잡고 있으면 이름 변경이 거부된다


def _replace(src, dst):
    """os.replace 를 PermissionError(폴더가 다른 프로그램에 잡혀 있을 때)에 한해 몇 번 다시 시도한다."""
    for attempt in range(SWAP_RETRIES):
        try:
            return os.replace(src, dst)
        except PermissionError as e:
            if attempt == SWAP_RETRIES - 1:
                raise PermissionError(
                    f"{src} 를 옮기지 못했습니다. 다른 프로그램(브라우저, IDE, 탐색기, 로컬 서버)이 이 폴더를 쓰고 있을 수 있습니다. "
                    f"닫은 뒤 다시 실행하세요. 기존 사이트는 그대로입니다. ({e})") from e
            time.sleep(SWAP_DELAY * (attempt + 1))


def swap_site(out_dir, new_site):
    """site/ 를 새 사이트로 교체한다. 교체 도중 실패하면 기존 사이트를 되돌려 놓는다."""
    final, old = os.path.join(out_dir, SITE_DIR), os.path.join(out_dir, SITE_DIR + ".old")
    shutil.rmtree(old, ignore_errors=True)
    had = os.path.exists(final)
    if had:
        _replace(final, old)
    try:
        _replace(new_site, final)
    except Exception:
        if had:
            _replace(old, final)
        raise
    shutil.rmtree(old, ignore_errors=True)
    return final


def _run(out_dir, state):
    """본 작업. 결과·요약을 state 에 담고 종료 코드를 돌려준다 (로그 작성은 main 이 한다)."""
    name = date.today().isoformat()  # 스냅샷 날짜 (이력 파일 이름)
    state["name"] = name

    log("[0/2] 인터넷 연결 확인")
    try:
        docs_fetch_json.get(docs_fetch_json.INDEX_URL)
    except Exception as e:
        state["result"] = f"실패: 인터넷 연결 안 됨 ({e})"
        log(f"연결 실패: {e}\n인터넷 연결을 확인한 뒤 다시 실행하세요. 기존 사이트는 변경하지 않았습니다.")
        return 1

    os.makedirs(out_dir, exist_ok=True)
    build = os.path.join(out_dir, ".building")
    shutil.rmtree(build, ignore_errors=True)  # 이전 실행이 중간에 끊겨 남은 찌꺼기
    os.makedirs(build)
    try:
        json_path = os.path.join(build, "docs.json")
        site_dir = os.path.join(build, SITE_DIR)

        log(f"[1/2] 수집: {json_path}")
        docs_fetch_json.main([json_path, os.path.join(site_dir, "assets")])  # 에셋은 사이트 폴더에 바로 저장 (복사본 없음)
        snap = docs_diff.open_json(json_path)
        failed = [p["url"] for p in snap["pages"] if p["content"] is None]
        ko_failed = snap.get("ko_errors", {})
        n_ko = sum(1 for p in snap["pages"] if p.get("ko"))
        state["collect"] = {
            "pages": len(snap["pages"]), "failed": len(failed), "redirects": len(snap.get("redirects", {})),
            "unlisted": sum(p["category"][0] == "_unlisted" for p in snap["pages"]),
            "ko": n_ko, "ko_missing": len(snap["pages"]) - n_ko - len(ko_failed),
            "non_page": len(snap.get("non_page_links", {})), "unresolved": len(snap.get("unresolved_links", {})),
            "assets": len({a for p in snap["pages"] for a in p.get("assets", {}).values()}),
            "asset_errors": len(snap.get("asset_errors", {}))}
        state["failures"] = [(p["url"], p.get("error", "원인 불명")) for p in snap["pages"] if p["content"] is None] + \
                            [(u + " (한국어판)", e) for u, e in ko_failed.items()] + \
                            [(u, "에셋: " + e) for u, e in snap.get("asset_errors", {}).items()]
        if failed:
            state["result"] = f"실패: 수집 실패 페이지 {len(failed)}개 (예: {failed[0]})"
            log(f"수집 실패 페이지 {len(failed)}개 (예: {failed[0]}). 기존 사이트는 그대로 두고 중단합니다.")
            return 1
        if ko_failed:
            first = next(iter(ko_failed))
            state["result"] = f"실패: 한국어판 수집 실패 페이지 {len(ko_failed)}개 (예: {first})"
            log(f"한국어판 수집 실패 페이지 {len(ko_failed)}개 (예: {first}). 기존 사이트는 그대로 두고 중단합니다.")
            return 1

        state["nav_mismatch"] = snap.get("nav_name_mismatch", [])
        log(f"[2/2] HTML 변환: {site_dir}")
        failed_convert = docs_json_to_html.main([json_path, site_dir])
        state["links"] = dict(docs_anchors.REPORT)  # 앵커·링크 검사 결과를 로그에 옮긴다
        verdict = docs_verify.check(site_dir)  # 변환기와 무관하게 결과 HTML 의 링크·id 를 전수 재검사
        state["links"]["verify"] = verdict
        vc = verdict["counts"]
        log(f"독립 검사: 페이지 {vc.get('pages', 0)}개, 링크 {vc.get('links', 0)}건(앵커 {vc.get('anchors', 0)}건) -> 위반 {len(verdict['problems'])}건")
        if verdict["problems"]:
            for page, kind, detail in verdict["problems"][:20]:
                log(f"  {kind}: {page} -> {detail}")
            state["result"] = f"실패: 독립 검사에서 링크·id 위반 {len(verdict['problems'])}건"
            log("결과 HTML 에 깨진 링크나 id 문제가 있어 중단합니다. 기존 사이트는 그대로입니다.")
            return 1
        if failed_convert:
            state["result"] = "실패: HTML 에 없는 파일을 가리키는 링크가 있음"
            log("HTML 에 없는 파일을 가리키는 링크가 있어 중단합니다. 기존 사이트는 그대로입니다.")
            return 1

        # 변경 요약 (이력을 정리하기 전에 비교)
        prev_path = find_previous(out_dir, name)
        body, counts = make_entry(prev_path, snap)
        state["change_lines"] = body

        # 모두 성공: 사이트를 교체하고, 원본 데이터를 이력에 보관한다 (docs.json 은 아직 .building 안에 있음)
        swap_site(out_dir, site_dir)
        diff_path = save_history(out_dir, name, json_path, prev_path, snap)
    finally:
        shutil.rmtree(build, ignore_errors=True)

    if diff_path:
        state["change_lines"] += [f"전체 diff: {diff_path}", ""]
    state["removed"] = remove_legacy_dirs(out_dir)
    state["removed_history"] = prune_history(out_dir, KEEP_HISTORY)
    latest = f"{SITE_DIR}/index.html"
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(f'<!doctype html><meta charset="utf-8"><title>Claude Code Docs (offline)</title>'
                f'<meta http-equiv="refresh" content="0; url={latest}">'
                f'<a href="{latest}">{latest}</a>\n')

    summary = "이전 이력 없음" if counts is None else f"추가 {counts[0]}, 삭제 {counts[1]}, 변경 {counts[2]}"
    log(f"완료: {os.path.join(out_dir, 'index.html')} -> {latest} ({len(snap['pages'])}페이지 x 2개 언어, {summary})")
    if state["removed"]:
        log(f"정리한 옛 구조의 날짜 폴더: {', '.join(state['removed'])}")
    if state["removed_history"]:
        log(f"정리한 오래된 이력: {', '.join(state['removed_history'])}")
    state["result"] = "성공"
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out_dir = argv[0] if argv else DEFAULT_OUT
    log_dir = argv[1] if len(argv) > 1 else DEFAULT_LOGS
    state, code, start = {"result": "중단 (정상 종료하지 못함)"}, 1, datetime.now()
    buf = io.StringIO()
    real_out, real_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = Tee(real_out, buf), Tee(real_err, buf)  # 화면 출력은 그대로, 로그용으로도 복사
    try:
        code = _run(out_dir, state)
    except Exception as e:
        state["result"] = f"오류: {type(e).__name__}: {e}"
        state["traceback"] = traceback.format_exc()
        log(state["traceback"])
    finally:
        sys.stdout, sys.stderr = real_out, real_err
        try:  # 로그를 못 써도 본 작업의 결과는 바꾸지 않는다
            log(f"로그: {write_log(log_dir, start, datetime.now(), out_dir, state, buf.getvalue())}")
        except Exception as e:
            log(f"경고: 로그를 쓰지 못했습니다: {e}")
    return code


if __name__ == "__main__":
    setup_console()
    sys.exit(main())
