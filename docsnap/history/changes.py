"""두 스냅샷(docs.json) 사이에 문서가 무엇이 바뀌었는지 구조화된 데이터로 계산하고, 사이트의 '변경 내역' 페이지용 마크다운을 만든다.

빌드 로그의 변경 요약과 사이트의 en/changes.html, ko/changes.html 이 같은 계산(page_changes)을 쓴다. 표준 라이브러리만 사용.
한국어 페이지는 번역이 아니라 공식 한국어판 본문의 변경을 보여 준다(한국어판이 없는 페이지는 영어 변경을 그대로).
"""
import re

FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


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


def page_changes(old, new, keep=3):
    """한 페이지 본문의 변경. 새·삭제·수정된 섹션 이름, 추가·삭제된 줄 수와 대표 줄(keep 개), 글자 수 증감."""
    so, sn = split_sections(old), split_sections(new)
    old_lines = [l.strip() for l in old.split("\n") if useful(l)]
    new_lines = [l.strip() for l in new.split("\n") if useful(l)]
    oset, nset = set(old_lines), set(new_lines)
    add_l = list(dict.fromkeys(l for l in new_lines if l not in oset))
    rem_l = list(dict.fromkeys(l for l in old_lines if l not in nset))
    return {"new_sections": [k for k in sn if k not in so and k != "(intro)"],
            "gone_sections": [k for k in so if k not in sn and k != "(intro)"],
            "edited_sections": [k for k in sn if k in so and sn[k] != so[k]],
            "add_n": len(add_l), "rem_n": len(rem_l), "added": add_l[:keep], "removed": rem_l[:keep],
            "delta": len(new) - len(old)}


def _rest(page):
    return page["url"].split("/docs/en/", 1)[1].removesuffix(".md")


def _heads(content, title):
    """페이지의 섹션 이름들. 페이지 제목(H1)과 같은 이름은 섹션이 아니라 제목이므로 뺀다."""
    return [k for k in split_sections(content) if k not in ("(intro)", title)]


def _ko(page):
    return page.get("ko") or None


def change_data(prev, new, prev_label=None):
    """직전 스냅샷 prev 대비 new 의 변경. prev 가 None 이면 비교할 것이 없다는 뜻의 최소 데이터.

    changed 항목의 "en"/"ko" 는 그 언어 사이트에서 보이는 변경(없으면 None). 한국어판이 없는 페이지의 "ko" 는 영어 변경과 같다."""
    base = {"date": new.get("fetched_at", ""), "prev": None, "prev_label": prev_label}
    if prev is None:
        return base
    new_p, old_p = {p["url"]: p for p in new["pages"]}, {p["url"]: p for p in prev["pages"]}
    added, removed, changed = [], [], []
    for u, p in new_p.items():
        k = _ko(p)
        if u not in old_p:
            added.append({"slug": _rest(p), "title": {"en": p["title"], "ko": (k or p)["title"]},
                          "desc": {"en": p.get("description", ""), "ko": (k or p).get("description", "")},
                          "sections": {"en": _heads(p["content"], p["title"]), "ko": _heads((k or p)["content"], (k or p)["title"])}})
            continue
        o = old_p[u]
        en = page_changes(o["content"], p["content"]) if o["content"] != p["content"] else None
        ko_new, ko_old = _ko(p), _ko(o)
        if ko_new is None:
            ko = en  # 한국어판이 없으면 한국어 사이트도 영어 본문을 보여 준다
        elif ko_old is not None and ko_old["content"] != ko_new["content"]:
            ko = page_changes(ko_old["content"], ko_new["content"])
        else:
            ko = None  # 영어만 바뀌고 공식 한국어판은 아직 그대로
        if en or ko:
            changed.append({"slug": _rest(p), "title": {"en": p["title"], "ko": (ko_new or p)["title"]}, "en": en, "ko": ko})
    for u, o in old_p.items():
        if u not in new_p:
            removed.append({"slug": _rest(o), "title": {"en": o["title"], "ko": (_ko(o) or o)["title"]}})
    base.update(prev=prev.get("fetched_at", "?"), added=added, removed=removed, changed=changed,
                unchanged=len(new_p) - len(added) - len(changed))
    return base


# 사이트 부품 문구(번역된 문서 내용이 아니라 이 페이지의 제목·라벨)
TEXT = {
    "en": {"title": "What changed", "intro": "Compared with the snapshot of {prev} ({label}). This snapshot: {date}.",
           "none": "There is no earlier snapshot to compare with, so nothing is listed yet. The next build will show what changed since this one.",
           "counts": "{a} added · {r} removed · {c} changed · {u} unchanged",
           "added": "Added pages", "removed": "Removed pages", "changed": "Changed pages", "sections": "Sections",
           "new_sec": "New sections", "gone_sec": "Removed sections", "edited_sec": "Edited sections",
           "line_add": "Added", "line_rem": "Removed", "chars": "chars", "lines_add": "lines added", "lines_rem": "removed",
           "more": "and {n} more", "empty": "Nothing changed."},
    "ko": {"title": "변경 내역", "intro": "{prev} 스냅샷({label})과 비교한 결과입니다. 이 스냅샷: {date}.",
           "none": "비교할 이전 스냅샷이 없어 아직 표시할 내용이 없습니다. 다음 빌드부터 이번 스냅샷 이후의 변경이 여기에 나옵니다.",
           "counts": "추가 {a}개 · 삭제 {r}개 · 변경 {c}개 · 변경 없음 {u}개",
           "added": "추가된 페이지", "removed": "삭제된 페이지", "changed": "내용이 바뀐 페이지", "sections": "섹션",
           "new_sec": "새 섹션", "gone_sec": "삭제된 섹션", "edited_sec": "내용이 바뀐 섹션",
           "line_add": "추가", "line_rem": "삭제", "chars": "자", "lines_add": "줄 추가", "lines_rem": "줄 삭제",
           "more": "외 {n}개", "empty": "바뀐 것이 없습니다."},
}


def code(s):
    """마크다운 코드 조각: 내용에 있는 백틱보다 하나 더 긴 백틱으로 감싼다."""
    s = s.replace("\n", " ")
    n = max((len(m) for m in re.findall(r"`+", s)), default=0) + 1
    fence = "`" * n
    return f"{fence} {s} {fence}" if n > 1 else f"`{s}`"


def _names(items, t, k=8):
    shown = ", ".join(code(short(i, 60)) for i in items[:k])
    return shown + (" " + t["more"].format(n=len(items) - k) if len(items) > k else "")


def _link(title, lang, slug):
    safe = title.replace("[", "\\[").replace("]", "\\]")
    return f"[{safe}](https://code.claude.com/docs/{lang}/{slug}.md)"


def changes_markdown(data, lang):
    """변경 내역 페이지의 마크다운. 변환기의 Renderer 가 링크를 사이트 안 상대 경로로 바꾼다."""
    t = TEXT[lang]
    lines = [f"# {t['title']}", ""]
    if data.get("prev") is None:
        return "\n".join(lines + [f"> {t['none']}", ""])
    label = data.get("prev_label") or ""
    lines += [f"> {t['intro'].format(prev=data['prev'], label=label, date=data['date'])}", ""]
    changed = [c for c in data["changed"] if c[lang]]
    lines += [t["counts"].format(a=len(data["added"]), r=len(data["removed"]), c=len(changed), u=data["unchanged"]), ""]
    if not (data["added"] or data["removed"] or changed):
        return "\n".join(lines + [t["empty"], ""])
    if data["added"]:
        lines += [f"## {t['added']}", ""]
        for p in data["added"]:
            desc = p["desc"][lang]
            lines.append(f"- {_link(p['title'][lang], lang, p['slug'])}" + (f": {desc}" if desc else ""))
            if p["sections"][lang]:
                lines.append(f"  - {t['sections']}: {_names(p['sections'][lang], t)}")
        lines.append("")
    if data["removed"]:
        lines += [f"## {t['removed']}", ""] + [f"- **{p['title'][lang]}** ({code(p['slug'])})" for p in data["removed"]] + [""]
    if changed:
        lines += [f"## {t['changed']}", ""]
        for c in changed:
            d = c[lang]
            lines.append(f"- {_link(c['title'][lang], lang, c['slug'])} — {d['delta']:+d} {t['chars']} "
                         f"({d['add_n']} {t['lines_add']}, {d['rem_n']} {t['lines_rem']})")
            for key, label_key in (("new_sections", "new_sec"), ("gone_sections", "gone_sec"), ("edited_sections", "edited_sec")):
                if d[key]:
                    lines.append(f"  - {t[label_key]}: {_names(d[key], t)}")
            lines += [f"  - {t['line_add']}: {code(short(x))}" for x in d["added"]]
            lines += [f"  - {t['line_rem']}: {code(short(x))}" for x in d["removed"]]
        lines.append("")
    return "\n".join(lines)
