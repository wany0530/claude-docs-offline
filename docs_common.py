"""수집기와 변환기가 함께 쓰는 URL 규칙 (네트워크 코드 없음)."""


def norm(url):
    """링크 비교용: '#', '?', 끝 '/', '.md' 제거."""
    url = url.split("#")[0].split("?")[0].rstrip("/")
    return url[:-3] if url.endswith(".md") else url


def slug(url):
    return norm(url).split("/docs/", 1)[1]  # 예: en/agent-teams
