# claude-docs

[![tests](https://github.com/wany0530/claude-docs-offline/actions/workflows/test.yml/badge.svg)](https://github.com/wany0530/claude-docs-offline/actions/workflows/test.yml)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![stdlib only](https://img.shields.io/badge/dependencies-none-brightgreen)
[![MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

**[Claude Code 공식 문서](https://code.claude.com/docs)를 오프라인 사이트로 저장합니다.**
영어판 + 공식 한국어판(번역 아님) · 서버 없이 `file://`로 열림 · 실행할 때마다 바뀐 내용 기록

한 번 실행하면 그날 기준의 문서 전체가 원문 JSON과 오프라인 HTML 사이트로 저장됩니다. 한국어는 번역한 것이 아니라 공식 사이트의 한국어 문서(`/docs/ko/`) 원문을 그대로 수집한 것입니다.

## 빠른 시작

```
python build_docs_snapshot.py
```

| 단계 | 할 일 |
|---|---|
| 1 | 인터넷에 연결합니다 (실행하는 동안만 필요) |
| 2 | 위 명령을 실행합니다. 약 10초~2분, 어느 폴더에서 실행해도 같습니다 |
| 3 | 연결을 끊고 `output/index.html`을 엽니다. 영어 Overview가 열리고, 상단의 언어 선택(English / 한국어)으로 같은 페이지의 다른 언어판으로 바꿉니다 |

요구 사항은 **Python 3.9 이상**뿐입니다. 설치할 패키지가 없습니다.
출력·로그 폴더를 바꾸려면 `python build_docs_snapshot.py [출력폴더] [로그폴더]`로 지정합니다.

## 주요 기능

| 기능 | 설명 |
|---|---|
| 공식 사이트와 같은 화면 | 상단 탭, 현재 탭의 사이드바(페이지 이름 필터 포함), 탭·아코디언·카드 컴포넌트. 사이드바는 **공식 사이트와 같은 순서**입니다 |
| 본문 검색 | 헤더의 검색 버튼 또는 `Ctrl K`. 현재 언어의 색인을 처음 검색할 때 한 번 읽습니다 |
| 이 페이지 목차 | 오른쪽에 스크롤을 따라 강조되고, 좁은 화면에서는 본문 위의 접는 목차가 됩니다 |
| 변경 내역 | `en/changes.html`, `ko/changes.html`. 지난 이력과 비교해 추가·삭제·바뀐 페이지와 섹션, 바뀐 줄을 보여 줍니다. 모든 페이지 하단에 링크가 있습니다 |
| 코드 | 구문 강조(bash·json·python·js/ts·yaml·toml·powershell)와 블록별 복사 버튼 |
| 페이지 복사 | 원문 마크다운을 클립보드로 복사합니다 |
| 화면 | 다크 모드 자동 대응, 좁은 화면용 메뉴 토글 |
| 접근성 | '본문으로 건너뛰기' 링크, 포커스 윤곽선, 키보드로 쓰는 탭·검색 창 |

- 목차에 없는 **숨은 페이지**(`Unlisted`)도 함께 수집하고, 옛 주소로 걸린 링크는 새 주소로 연결합니다.
- 한국어판이 없는 페이지(현재 `changelog`, `claude-tag`: 공식 사이트가 외부 주소로 넘김)는 한국어 사이트에서 **영어 원문**을 안내 문구와 함께 보여 줍니다.
- 한국어 변경 내역은 공식 한국어 본문의 변경을 보여 줍니다. 영어만 바뀌고 한국어판은 그대로인 페이지는 한국어 변경 내역에 나오지 않습니다.

## 결과물

```
output/
├─ index.html              site/ 로 이동하는 바로가기
├─ site/                   최신 오프라인 사이트 (브라우저로 여는 유일한 사본)
│  ├─ en/  ko/             페이지별 HTML (영어판, 공식 한국어판)
│  ├─ assets/              문서의 이미지·동영상 (이 한 곳에만 있음)
│  └─ style.css, nav.js, nav-data-*.js, search-data-*.js
└─ history/                원본 데이터 (유일한 사본, 최근 30회분)
   ├─ YYYY-MM-DD.json.gz   그날의 docs.json (분류, 영어·한국어 본문, 메뉴 이름 등)
   └─ YYYY-MM-DD.diff      직전 이력 대비 바뀐 페이지의 unified diff (변경이 있을 때만)
logs/
└─ YYYY/YYYY-MM-DD_HHMMSS.log   실행 1회당 로그 1개
```

- 사이트와 원본을 **한 벌씩만** 둡니다. 압축하지 않은 `docs.json`, 날짜별 사이트 폴더, 에셋 복사본은 만들지 않습니다.
- `history/`는 gzip(약 6MB)으로 **최근 30회분**을 보관해 과거 본문을 복원하고 비교할 수 있습니다. 개수는 `build_docs_snapshot.py`의 `KEEP_HISTORY`입니다.
- 로그에는 결과, 수집 요약, **직전 이력 대비 변경 요약**(사이트의 변경 내역과 같은 계산), 링크 검증 요약, 콘솔 출력이 들어갑니다. 긴 링크 목록은 뒤쪽 "링크 상세"에 있고, 바뀐 내용의 전문은 `history/YYYY-MM-DD.diff`입니다.
- `output/`과 `logs/`는 git에 올라가지 않습니다(`.gitignore`). 직접 실행해서 만드세요.
- 이전 버전이 만든 `output/YYYY-MM-DD/` 폴더가 있으면 첫 실행 때 비교 기준으로 한 번 쓰고 삭제합니다.

## 안전장치

다음 경우에는 **기존 사이트를 건드리지 않고** 종료 코드 1로 끝나며 로그 파일만 남습니다.

- 인터넷에 연결되지 않음
- 수집에 실패한 페이지가 하나라도 있음 (영어판, 한국어판 모두. 한국어판이 공식적으로 없는 것은 실패가 아님)
- 변환한 HTML에 없는 파일이나 앵커를 가리키는 링크가 있음
- 예상하지 못한 오류 (트레이스백이 로그에 기록됨)

그 밖의 동작은 다음과 같습니다.

- 빌드는 `output/.building/`에서 하고, 모든 페이지 수집·변환·검증이 성공했을 때만 `site/`를 통째로 교체합니다. 교체 중 실패하면 기존 `site/`를 되돌립니다.
- 이미지·동영상 다운로드 실패는 빌드를 멈추지 않고, 로그의 수집 요약(에셋 실패 수)에만 기록됩니다.
- 같은 날 다시 실행하면 그날 사이트와 이력을 덮어씁니다. 비교 대상은 **오늘 이전의 가장 최근 이력**이라 다시 실행해도 어제 대비 변경이 그대로 나옵니다. 오늘 이전 이력이 아직 없으면 변경이 거의 없게 나올 수 있습니다.

## 오프라인에서 되는 것과 안 되는 것

2026-11-27 사본(222쪽 × 2개 언어)으로 측정한 값입니다.

| 항목 | 내용 |
|---|---|
| 되는 것 | 화면을 그리는 데 필요한 원격 리소스(이미지·동영상·CSS·글꼴)가 **0개**입니다. 이미지·동영상 73개는 `assets/`에 있고 글꼴은 시스템 글꼴입니다. 메뉴, 목차, 검색, 복사, 다크 모드, 변경 내역이 모두 오프라인에서 동작합니다 |
| 안 되는 것 | 본문 안의 외부 링크 약 3,480개(claude.com 564, claude.ai 532, platform.claude.com 506, github.com 410 등)와 각 페이지 하단의 "원문" 링크는 인터넷이 있어야 열립니다. `https://code.claude.com/docs/mcp` 같은 문서 페이지가 아닌 주소도 외부 링크로 남습니다 |
| 크기 | 사이트 약 80MB(에셋 포함), 이력은 하루 약 6MB(gzip), 검색 색인은 영어 9.7MB·한국어 11.5MB |
| 속도 | 이 PC(Chromium, `file://`)에서 색인을 처음 읽는 첫 검색이 디바운스 150ms 포함 약 0.3초, JS 힙 40~47MB. 이후 검색은 거의 즉시입니다. 느린 디스크에서는 더 걸릴 수 있습니다 |
| 최신성 | 사본은 실행한 날 기준이며 자동으로 갱신하지 않습니다. 날짜는 각 페이지 하단과 변경 내역 페이지에 있습니다 (실행한 PC의 로컬 날짜) |

## 알려진 한계

- **구문 강조**는 규칙 기반이라 언어 문법을 완전히 해석하지 않습니다. 지원하지 않는 언어는 색 없이 표시됩니다.
- **검색**은 부분 문자열 일치(공백으로 나눈 단어를 모두 포함)입니다. 형태소 분석과 오타 보정은 없고, 한글은 한 글자 검색어도 됩니다.
- **온라인 요소**(공식 사이트의 "Ask Assistant", 로고, 웹폰트)는 없습니다.
- **앵커 링크**는 빌드할 때 실제 섹션(헤딩·아코디언)에 맞춰 확정합니다. 제목이 길어진 정도는 단어가 겹치는 섹션이 하나뿐일 때만 따라갑니다. 공식 문서에서 섹션이 사라지거나 크게 바뀐 링크(언어별 약 450건)는 페이지 처음으로 연결하고 점선 밑줄과 안내 문구로 표시합니다. 건수와 목록은 로그의 "링크 검증"에 남습니다.
- **링크 검증**(`docs_verify.py`)은 "대상이 있다"까지만 보장합니다. 단어 일치로 이어 준 링크가 의미상 맞는지는 `reviewed_anchors.json`의 검토 기록(현재 91건, Claude가 검토했고 사람이 확인한 것은 아님)과 대조하고, 새 보정이 생기면 로그에 "검토 필요"로 알립니다.
- **변경 요약**은 섹션·줄 단위의 규칙 기반 비교이며 문장 요약이 아닙니다. 확정이 아니라 단서로 보고, 전문은 `history/*.diff`나 `docs_diff.py`로 확인하세요. 로그의 요약은 영어판 기준이고, 한국어판 변경은 `ko/changes.html`과 diff 파일의 `ko/…` 항목에서 봅니다.
- **Windows**에서 브라우저·IDE·탐색기가 `output/site`를 열고 있으면 마지막 교체 단계가 거부될 수 있습니다. 몇 번 다시 시도하고, 그래도 안 되면 원인을 알리고 기존 사이트는 그대로 둡니다. 빌드 전에 사이트를 보던 프로그램을 닫으세요.
- **접근성**은 자동 검사(axe)와 키보드 동작으로만 확인했고, 스크린 리더로 직접 들어 보지는 않았습니다.
- **수집하지 않는 것**: GitHub 저장소 `anthropics/claude-code`의 `CHANGELOG.md`, `plugins/`, `examples/` (변경이 너무 잦거나 문서와 중복).

## 개발

### 구성

| 파일 | 역할 |
|---|---|
| `build_docs_snapshot.py` | 통합 진입점. 수집 → HTML 변환 → 검증 → `site/` 교체 → 이력·diff 저장 → 로그 |
| `docs_fetch_json.py` | `llms.txt`에서 페이지 목록을 읽어 영어 원문, 공식 한국어판, 에셋을 받아 JSON으로 저장 |
| `docs_json_to_html.py` | JSON(.gz 가능)을 영어·한국어 정적 사이트로 변환하는 진행 순서 |
| `docs_markdown.py` + `md_*.py` | 직접 만든 마크다운 → HTML 변환기. `docs_markdown.py`가 `Renderer`를 내보내고, `md_syntax`(정규식·순수 함수), `md_inline`(인라인·링크), `md_ids`(헤딩·아코디언 id), `md_components`(탭·아코디언·카드·콜아웃), `md_structures`(표·목록), `md_blocks`(블록 순회)로 나뉨 |
| `docs_anchors.py` | `#앵커` 링크를 실제 섹션에 맞춰 확정, 검토 장부 대조 |
| `docs_changes.py` | 두 스냅샷의 변경 계산 (로그 요약과 변경 내역 페이지가 같은 계산을 씀) |
| `docs_verify.py` | 변환기와 무관하게 사이트 HTML을 다시 읽는 독립 링크 검사기 |
| `docs_site.py` | 화면 문구, 메뉴 트리, 주소 표, `site_src/` 파일 읽기 |
| `site_src/` | 사이트의 실제 소스: `style.css`, `page.html`, JS(`lib.js` 계산 함수, `app.js`, `search.js`, `highlight.js`) |
| `docs_diff.py` | 보관된 이력 두 개를 비교해 페이지별 diff 출력 |
| `docs_common.py` | URL 규칙과 콘솔 UTF-8 설정 (수집기·변환기 공유) |

### 단계별 실행

```
# 수집과 변환을 따로
python docs_fetch_json.py tmp/docs.json tmp/site/assets
python docs_json_to_html.py tmp/docs.json tmp/site

# 보관된 이력으로 사이트만 다시 (네트워크 불필요, 에셋이 이미 있으면 복사하지 않음)
python docs_json_to_html.py output/history/YYYY-MM-DD.json.gz 새폴더 output/site/assets

# 보관한 두 날짜의 차이 (페이지는 선택, 언어 접두어를 붙임: ko/hooks)
python docs_diff.py 2026-11-20 2026-11-27 ko/hooks

# 만든 사이트의 링크 검사
python docs_verify.py output/site
```

### 테스트

| 종류 | 명령 |
|---|---|
| 단위 (215개, 네트워크 불필요. Node가 있으면 JS 테스트와 파이썬·JS 앵커 규칙 비교 포함) | `python -m unittest discover tests` |
| 브라우저 E2E (Chromium, 개발용) | `cd tests/e2e && npm ci && npx playwright install chromium && npm test` |
| 받아 둔 실제 데이터로 불변식 확인 | `DOCS_REAL=1 python -m unittest discover tests -p "test_realdata.py"` (PowerShell: `$env:DOCS_REAL=1`) |

<details>
<summary>테스트가 확인하는 것, 커버리지, 접근성</summary>

- **단위 테스트**: 마크다운 변환기, 앵커 확정, 수집기(가짜 네트워크), 빌드 전체(성공·실패 경로마다 "기존 사이트는 그대로"), 독립 검증기, 두 언어 사이트 출력.
- **브라우저 E2E**: 가짜 문서 6쪽으로 만든 고정 사이트에서 메뉴·목차·탭·아코디언 이동·검색·복사·구문 강조·모바일 레이아웃을 확인하고, 서버 없이 `file://`로 여는 경우도 확인합니다. `@playwright/test`는 1.61.1(Chromium 리비전 1228)로 고정돼 있습니다.
- **접근성**: `axe-core`(WCAG 2 A/AA)가 밝은·어두운 테마, 검색 창, 모바일 상태에서 위반 0건인지 확인하고, 키보드 동작(건너뛰기 링크, 탭 화살표·Home·End, 검색 창 포커스 가두기·Esc)을 확인합니다. 스크린 리더로 직접 확인한 것은 아닙니다.
- **실제 데이터 불변식**: `output/history`가 있을 때만 켜집니다. 없는 파일 0, 한국어 id 일치, 독립 검사 위반 0, 장부에 없는 새 보정 0과 끊김·보정 수의 느슨한 상한(`tests/real_data_limits.json`)을 봅니다. 업스트림이 바뀌어 새 보정이 생기면 실패하는데, 오류가 아니라 검토 신호입니다.

**커버리지** (개발 전용, `pip install -r requirements-dev.txt`)

```
python -m coverage run -m unittest discover tests && python -m coverage report   # 파이썬 줄·분기 (하한 95%, .coveragerc)
node --test --experimental-test-coverage tests/js/*.test.js                       # site_src/lib.js
cd tests/e2e && npm run coverage                                                  # 사이트 JS: E2E를 돌리며 Chromium으로 측정
```

커버리지는 "그 줄이 실행됐다"는 뜻이지 "맞다고 확인했다"는 뜻이 아닙니다. 그래서 숫자를 올리려고 테스트를 쓰지 않고, 안 실행된 줄이 실제 동작인지 먼저 읽은 뒤 쓰며, 새 테스트가 정말 어설션하는지 코드를 일부러 망가뜨려 확인합니다(`CLAUDE.md`의 "Mutation check").

</details>

### CI

GitHub Actions(`.github/workflows/test.yml`)가 push와 PR마다 **Python 3.9·3.14 단위 테스트**(3.14에서는 커버리지 포함)와 **Chromium E2E**를 돌립니다. "Python 3.9 이상"이라는 주장은 이 매트릭스가 실제로 확인하고, `tests/test_compat.py`가 로컬에서 빠르게 지키는 정적 방어선입니다. 2026-11-27의 첫 실행에서 전부 통과했습니다. 단 Ubuntu에서만 돌고 macOS·Windows는 확인하지 않았습니다.

### 콘솔 인코딩

스크립트는 시작할 때 콘솔을 UTF-8·줄 단위 버퍼로 바꿔서 한글이 깨지지 않고 출력 순서도 유지됩니다. 오래된 PowerShell 5.1에서 깨져 보이면 `[Console]::OutputEncoding=[Text.Encoding]::UTF8`을 먼저 실행하세요.

## 참고

- 이 저장소의 코드는 [MIT 라이선스](LICENSE)입니다. 이 라이선스는 코드에만 적용되며, 수집되는 Anthropic 문서에는 적용되지 않습니다.
- 이 도구는 **비공식**이며 Anthropic과 관련이 없습니다. Claude, Claude Code는 Anthropic의 상표입니다.
- 공식 문서의 내용과 이미지의 저작권은 Anthropic에 있습니다. 생성된 `output/`은 개인 열람용으로만 쓰고 재배포하지 마세요.
- 이 저장소는 문서 사본을 담지 않고 수집 도구만 담습니다. 로그의 변경 요약에는 바뀐 줄의 일부(줄당 최대 140자)가 인용될 수 있으나 로그도 git에는 올라가지 않습니다.
- 이 저장소에서 Claude Code로 작업할 때의 상세 지침은 [`CLAUDE.md`](CLAUDE.md)(영문)에 있습니다.
