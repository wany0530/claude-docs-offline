"""E2E 가 열어 볼 고정 사이트를 만든다 (실제 변환기와 실제 문서 규칙, 가짜 문서 7쪽, 네트워크 없음).

사용:  python tests/e2e/build_fixture.py [출력폴더]      (기본: tests/e2e/.site, git 무시)
들어 있는 것: 탭 2개와 하위 그룹이 있는 사이드바, 긴 목차, CJK 첫 열 표(예전 줄바꿈 버그), 본문 탭,
아코디언과 그것을 가리키는 링크, 끊긴 링크, bash/json 코드, 한국어판과 '한국어판 없음' 폴백, 검색 대상 단어.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import fixtures as fx  # noqa: E402

REF = "https://code.claude.com/docs/en/reference.md"
KO_REF = "https://code.claude.com/docs/ko/reference.md"
LONG_EN = "\n\n".join(f"## Long section {n}\n\n" + "Filler paragraph for scrolling. " * 40 for n in range(1, 5))
LONG_KO = "\n\n".join(f"## 긴 섹션 {n}\n\n" + "스크롤을 위한 채움 문단입니다. " * 40 for n in range(1, 5))

GUIDE_EN = f"""# Guide

> A short lead description.

## Overview section

Intro with [a link to the accordion]({REF}#how-it-works), [a renamed section]({REF}#removed-section) and [a local link](#install-steps).

> [!NOTE]
> A note callout with `inline code`.

> [!WARNING]
> A warning callout.

> A plain block quote.

> [card] [Card one]({REF})
>
> Description of card one.

> [card] [Card two](https://code.claude.com/docs/en/api.md)
>
> Description of card two.

### Install steps

Pick a platform.

> [tab] macOS
>
> ```bash
> # install on mac
> curl -fsSL https://example.com/install.sh | bash
> ```

> [tab] Windows
>
> Windows steps.
>
> ### Windows only heading
>
> More Windows text.

## Configuration table

| Approach | Provides | When to use |
|---|---|---|
| Subagents | Runs a focused task inside its own context window and returns only a short summary to the main conversation, so search results and logs never flood it | Side tasks whose intermediate output you will not refer to again and that would otherwise fill the main conversation with file contents |
| Agent view | One screen to dispatch background sessions and monitor them while you keep working in the foreground, with a way to peek at each session or step in | Several independent jobs that should keep running while you work on something else or when you want to check on them later |

## JSON example

```json
{{"name": "demo", "count": 3, "ok": true}}
```

{LONG_EN}
"""

GUIDE_KO = f"""# 가이드

> 짧은 설명입니다.

## 개요 섹션

[아코디언 링크]({KO_REF}#how-it-works), [이름이 바뀐 섹션]({KO_REF}#removed-section), [같은 페이지 링크](#install-steps)가 있습니다.

> [!NOTE]
> `인라인 코드`가 있는 참고 상자입니다.

> [!WARNING]
> 경고 상자입니다.

> 일반 인용문입니다.

> [card] [카드 하나]({KO_REF})
>
> 카드 하나의 설명입니다.

> [card] [카드 둘](https://code.claude.com/docs/ko/api.md)
>
> 카드 둘의 설명입니다.

### 설치 단계

플랫폼을 고르세요.

> [tab] macOS
>
> ```bash
> # 맥에 설치
> curl -fsSL https://example.com/install.sh | bash
> ```

> [tab] Windows
>
> Windows 단계입니다.
>
> ### Windows 전용 제목
>
> Windows 설명이 더 있습니다.

## 설정 표

| 접근 방식 | 제공되는 기능 | 사용 시기 |
|---|---|---|
| 서브에이전트 | 자신의 컨텍스트 창 안에서 집중된 작업을 수행하고 요약만 주 대화로 돌려주므로 검색 결과와 로그가 주 대화를 가득 채우지 않습니다 | 중간 출력을 다시 참조하지 않을 부작업이며, 그렇지 않으면 파일 내용이 주 대화를 채우게 되는 경우 |
| 에이전트 뷰 | 백그라운드 세션을 보내고 앞에서 다른 일을 하는 동안 모니터링하며 각 세션을 들여다보거나 직접 개입할 수 있는 하나의 화면 | 여러 독립 작업이 계속 실행되어야 하거나 나중에 상태를 확인하고 싶을 때 |

## JSON 예시

```json
{{"name": "demo", "count": 3, "ok": true}}
```

{LONG_KO}
"""

REFERENCE_EN = """# Reference

## Reference notes

Plain text.

> [accordion] How it works
>
> Accordion body text.

## After the accordion

More text.
"""

REFERENCE_KO = """# 레퍼런스

## 레퍼런스 노트

일반 텍스트입니다.

> [accordion] 작동 방식
>
> 아코디언 본문입니다.

## 아코디언 뒤

더 많은 글입니다.
"""


def pages():
    basics = ("Guides", "Guides", "Basics")
    return [
        fx.page("guide", "Guide", GUIDE_EN, category=basics, ko=("가이드", GUIDE_KO)),
        fx.page("reference", "Reference", REFERENCE_EN, category=basics, ko=("레퍼런스", REFERENCE_KO)),
        fx.page("zebra", "Zebra stripes", "# Zebra stripes\n\n## Why stripes\n\nThe unique zebra stripes topic.", category=basics,
                ko=("얼룩말 줄무늬", "# 얼룩말 줄무늬\n\n## 줄무늬가 있는 이유\n\n유일한 얼룩말 줄무늬 주제입니다.")),
        fx.page("more", "More details", "# More details\n\n## Extra\n\nText.", category=("Guides", "Guides", "Basics", "More"),
                ko=("더 알아보기", "# 더 알아보기\n\n## 추가\n\n본문입니다.")),
        fx.page("advanced", "Advanced topic", "# Advanced topic\n\n## Deep dive\n\nText.", category=("Guides", "Guides", "Advanced", "Deep"),
                ko=("고급 주제", "# 고급 주제\n\n## 깊이 보기\n\n본문입니다.")),
        fx.page("api", "API", "# API\n\n## Endpoints\n\nSee the [guide](https://code.claude.com/docs/en/guide.md).",
                category=("Reference", "Reference", "API"),
                ko=("API", "# API\n\n## 엔드포인트\n\n[가이드](https://code.claude.com/docs/ko/guide.md)를 보세요.")),
        fx.page("nokorean", "No Korean", "# No Korean\n\n## English only\n\nNo official Korean page.",
                category=("Reference", "Reference", "API"), ko=None),
    ]


NAV_NAMES_KO = {"Guides": "가이드", "Reference": "레퍼런스", "Basics": "기본", "Advanced": "고급", "Deep": "심화", "More": "더보기"}
# 공식 사이드바에서는 하위 그룹(More)이 일반 페이지 사이에 끼어 있다. llms.txt 순서(페이지 먼저, 하위 그룹은 뒤)와 다르다.
NAV_ORDER = {"Guides": [["g", "Basics"], ["p", "en/guide"], ["s", "More"], ["p", "en/reference"], ["p", "en/zebra"],
                        ["g", "Advanced"], ["s", "Deep"]]}


def previous_pages():
    """'이전 스냅샷': more 는 아직 없었고(= 이번에 추가), legacy 는 있었고(= 이번에 삭제), reference 는 본문이 달랐다(= 변경)."""
    old = [p for p in pages() if p["url"].rsplit("/", 1)[1] != "more.md"]
    for p in old:
        if p["url"].endswith("/reference.md"):
            p["content"] = p["content"].replace("## Reference notes", "## Old reference notes")
            p["ko"]["content"] = p["ko"]["content"].replace("## 레퍼런스 노트", "## 옛 레퍼런스 노트")
    old.append(fx.page("legacy", "Legacy page", "# Legacy page\n\nGone now.", category=("Reference", "Reference", "API"),
                       ko=("옛 페이지", "# 옛 페이지\n\n지금은 없습니다.")))
    return old


def build(out_dir):
    """out_dir 에 고정 사이트를 만든다. (없는 파일 링크 수, 변환기 보고)를 돌려준다."""
    import docsnap.site.anchors as docs_anchors
    import docsnap.history.changes as docs_changes
    shutil.rmtree(out_dir, ignore_errors=True)
    changes = docs_changes.change_data(fx.snapshot(previous_pages(), fetched_at="2025-12-01"),
                                       fx.snapshot(pages(), fetched_at="2026-01-01"), "history/2025-12-01.json.gz")
    with tempfile.TemporaryDirectory() as work:
        missing = fx.build_site(pages(), out_dir, work, changes=changes, nav_names_ko=NAV_NAMES_KO, nav_order=NAV_ORDER)
    return missing, dict(docs_anchors.REPORT)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, ".site")
    miss, rep = build(target)
    print(f"fixture site -> {target} (없는 파일 {miss}개, 끊김 {rep['counts'].get('stale', 0)}건)")
    sys.exit(1 if miss else 0)
