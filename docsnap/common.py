"""수집기와 변환기가 함께 쓰는 URL 규칙 (네트워크 코드 없음)과 콘솔 설정."""
import os
import sys


def norm(url):
    """링크 비교용: '#', '?', 끝 '/', '.md' 제거."""
    url = url.split("#")[0].split("?")[0].rstrip("/")
    return url[:-3] if url.endswith(".md") else url


def slug(url):
    return norm(url).split("/docs/", 1)[1]  # 예: en/agent-teams


def ko_url(url):
    """영어 문서 주소(.../docs/en/X.md)에 해당하는 공식 한국어판 주소(.../docs/ko/X.md). 번역이 아니라 공식 사이트의 주소 규칙."""
    return url.replace("/docs/en/", "/docs/ko/", 1)


def setup_console():
    """파이프·리다이렉트에서도 한글이 깨지지 않고 출력 순서가 섞이지 않게 한다.

    stdout/stderr 를 UTF-8 + 줄 단위 버퍼로 바꾼다. PYTHONIOENCODING 이 지정돼 있으면 인코딩은 존중한다.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            kw = {"errors": "replace", "line_buffering": True}
            if not os.environ.get("PYTHONIOENCODING"):
                kw["encoding"] = "utf-8"
            stream.reconfigure(**kw)
        except (AttributeError, ValueError):  # reconfigure 가 없는 스트림(테스트 캡처 등)
            pass
