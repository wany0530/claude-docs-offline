# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 목적
Claude Code 공식 문서(https://code.claude.com/docs)를 오프라인 스냅샷으로 만드는 도구. 표준 라이브러리만 사용하는 Python 스크립트로 구성된다(수집 → JSON → HTML 변환 + 통합 진입점). git 저장소이며 `output/`은 `.gitignore`로 제외, `logs/`는 추적한다.

## 갱신 방법 (인터넷을 잠깐 연결해 오늘 기준으로 업데이트)
1. 인터넷에 연결한다. 2. `python build_docs_snapshot.py` 를 실행한다(약 10초~2분). 3. 연결을 끊고 `output/index.html`을 연다(항상 최신 스냅샷으로 이동).
- `output/`에는 **최신 스냅샷 폴더 하나만** 남는다(`KEEP_SNAPSHOTS = 1`, `build_docs_snapshot.py` 상단). 스냅샷 1회분은 `output/YYYY-MM-DD/{docs.json, assets/, html/}` 폴더 하나에 모인다. 성공한 빌드 뒤에 이전 날짜 폴더를 지운다. 이전 스냅샷 없이는 다음 비교가 안 되므로 최신 1개는 항상 남는다. zip 산출물은 만들지 않는다.
- **실행 로그**: 실행할 때마다(성공·실패·오류 모두) `logs/YYYY/YYYY-MM-DD_HHMMSS.log` 1개가 생긴다(예: `logs/2026/2026-11-26_144952.log`). 구성: 결과, 시작·종료·소요 시간, 수집 요약(페이지·에셋·별칭·숨은 페이지·비문서/미확인 링크 수), **직전 스냅샷 대비 변경 요약**, 정리한 이전 스냅샷, 오류가 나면 트레이스백, **구역별 역할 설명표**, 콘솔 출력 전체. 같은 날 여러 번 실행해도 덮어쓰지 않는다(같은 초면 `_2.log`).
- 설명표(`build_docs_snapshot.py`의 `LOG_GUIDE`)는 모든 로그 끝에 붙는다. 추가·삭제된 페이지, 새·삭제된·바뀐 섹션, 대표 줄이 각각 무엇을 알려 주는지(새 기능 신호, 폐지·이동 신호, 동작 변경 신호 등) 설명한다. 규칙 기반 비교이므로 확정이 아니라 확인할 단서라고 표기했다.
- 변경 요약은 추가/삭제/내용 변경 페이지 수와, 바뀐 페이지의 글자 수 증감·새 섹션·삭제된 섹션·바뀐 섹션·추가/삭제된 대표 줄(각 3개, 140자까지)이다. 섹션(헤딩)·줄 단위의 규칙 기반 비교이며 전체 diff나 문장 요약은 아니다. 이전 스냅샷은 지워지므로 원문 변경 전체는 복원할 수 없다.
- 안전장치: 연결이 안 되면 스냅샷은 건드리지 않고 종료(exit 1)하며 로그 파일만 남긴다. 빌드는 `output/.building/`에서 하고, 모든 페이지 수집·변환이 성공했을 때만 결과를 옮기고 이전 스냅샷을 지운다. 실패하면 기존 스냅샷은 그대로이고 `.building`은 지워진다.

## 실행
한 번에 실행(권장): `python build_docs_snapshot.py [출력폴더] [로그폴더]` — 기본값은 스크립트가 있는 폴더의 `output/`과 `logs/`(어디서 실행해도 같다). 오늘 날짜 폴더 `output/YYYY-MM-DD/`에 `docs.json`, `assets/`, `html/`을 만들고 `output/index.html`(바로가기)을 갱신하며 `logs/`에 실행 로그를 쓴다. 아래 두 단계를 순서대로 호출하는 진입점이며, 단계별로 따로 실행할 수도 있다.
```
python docs_fetch_json.py output/YYYY-MM-DD/docs.json
python docs_json_to_html.py output/YYYY-MM-DD/docs.json output/YYYY-MM-DD/html
```
(`build_docs_snapshot.py`는 다른 스크립트를 import하므로 스크립트들을 같은 폴더에 두고, `python -I`는 쓰지 않는다. `docs_fetch_json.py`와 `docs_json_to_html.py`는 공용 URL 규칙 `norm`/`slug`를 `docs_common.py`에서 import한다.)

1. `docs_fetch_json.py` — `llms.txt`에서 페이지 목록을 읽고 각 `.md` 원문을 받아 JSON 1개로 저장한다. 숨은 페이지(`_unlisted`), 옛 링크 별칭(`redirects`), 좌측 메뉴 이름(`nav_label`)을 함께 수집하고, 이미지·동영상은 JSON 옆 `assets/` 폴더에 저장한다. GitHub 저장소(`anthropics/claude-code`)의 `CHANGELOG.md`·`plugins/`·`examples/`는 변경이 너무 잦거나 문서와 중복이라 받지 않는다.

2. `docs_json_to_html.py` — 같은 JSON을 서버 없이 `file://`로 열리는 정적 HTML 사이트로 변환한다. `<폴더>/index.html`이 전체 목차이고, 페이지는 원문 주소 구조(`en/...html`)로 저장된다. 마크다운→HTML 변환기를 직접 구현했다(표준 라이브러리만; GitHub식 콜아웃 `> [!NOTE]`, 표, 중첩 목록, 코드블록 지원). docs 내부 링크는 상대 경로로, 이미지·동영상은 `assets/`로 바꾼다. 사이드바(`nav-data.js` + `nav.js`)에 필터와 코드 복사 버튼이 있다. 코드 구문 강조와 전문 검색은 없다.
   - 앵커: 사이트의 헤딩 id 규칙(`.`, `/`, `’` 처리)이 달라 `nav.js`가 구두점을 무시한 비교로 폴백한다. 그래도 남는 앵커(약 470건)는 원문 사이트에서 헤딩이 바뀌었거나 아코디언 제목에서 나온 것이라 복원할 수 없다(빌드 마지막에 건수 출력).

## 구조
- `output/` — 실행 결과물(git 제외). `YYYY-MM-DD/{docs.json, assets/, html/}`와 바로가기 `index.html`. `docs.json`과 `assets/`는 같은 폴더에 있어야 한다(변환기가 JSON 옆에서 assets를 찾는다).
- `docs_common.py` — 수집기와 변환기가 공유하는 URL 규칙(`norm`, `slug`).
- `logs/` — 실행 1회당 로그 1개(변경 요약 포함), `logs/YYYY/` 아래에 `.log`로 저장. `output/`과 분리되어 있어 스냅샷을 정리해도 지워지지 않는다.
- `reference/` — 참고 자료(문서 사이트 스크린샷).

## 링크 분류
본문이 링크한 docs 주소 중 수집되지 않은 것은 `resolve_links`가 분류한다: `redirects`(옛 주소 별칭), `_unlisted`(숨은 페이지로 추가), `non_page_links`(GET이 405이거나 docs 페이지가 아닌 응답을 주는 MCP 서버 등 문서가 아닌 엔드포인트, 예: `/docs/mcp`), `unresolved_links`(그 외 실패, 404 등).
