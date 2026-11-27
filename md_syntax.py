"""마크다운 변환에 쓰는 정규식과 상태 없는 도우미 함수 (Renderer 의 믹스인들이 함께 쓴다). 표준 라이브러리만 사용."""
import html
import re
import urllib.parse

ALLOWED_TAGS = {
    "a", "b", "i", "u", "em", "strong", "code", "kbd", "sub", "sup", "br", "span", "img", "video", "source",
    "details", "summary", "div", "p", "table", "thead", "tbody", "tr", "th", "td", "ul", "ol", "li", "hr",
}
BLOCK_HTML = {"video", "img", "div", "details", "summary", "table", "iframe", "p", "ul", "ol", "hr",
              "thead", "tbody", "tfoot", "tr", "th", "td", "caption"}

FENCE = re.compile(r"^( {0,3})(`{3,}|~{3,})\s*(.*)$")
HEAD = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
HR = re.compile(r"^ {0,3}([-*_])(?:\s*\1){2,}\s*$")
ITEM = re.compile(r"^( *)([-*+]|\d{1,9}[.)])(?:\s+(.*))?$")
QUOTE = re.compile(r"^ {0,3}>")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
HTML_START = re.compile(r"^\s*<(/?)([a-zA-Z][\w-]*)\b|^\s*<!--")
TAG = re.compile(r"</?([a-zA-Z][\w-]*)((?:\s[^<>]*?)?)\s*/?>")
URL_ATTR = re.compile(r'\b(src|href|poster)="([^"]*)"')
CODE_SPAN = re.compile(r"(?<![\\`])(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.S)
IMAGE = re.compile(r'!\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+"([^"]*)")?\s*\)')
LINK = re.compile(r'\[((?:[^\[\]]|\[[^\]]*\])*)\]\(\s*([^)\s]+)(?:\s+"([^"]*)")?\s*\)')
BARE_URL = re.compile(r"(?<![\w/@=\"'>\x00])(https?://[^\s<>\x00]+)")
ESCAPED = re.compile(r"\\([!-/:-@\[-`{-~])")
STRONG = [re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S), re.compile(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)", re.S)]
EM = [re.compile(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])", re.S),
      re.compile(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)", re.S)]
DEL = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~", re.S)
MARKER = re.compile(r"^\[(tab|accordion|card)\](?:[ \t]+(.*))?$")  # Mintlify 컴포넌트: > [tab] 이름 / > [accordion] 제목 / > [card] [제목](주소)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def esc_text(s):  # 이미 있는 &entity; 는 보존
    return re.sub(r"&(?!#?\w+;)", "&amp;", s).replace("<", "&lt;").replace(">", "&gt;")


def attr(s):
    return html.escape(s, quote=True)


def heading_slug(text):
    text = re.sub(r"<[^>]+>", "", html.unescape(text)).strip().lower()
    return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", text))


def anchor_key(s):
    """앵커 비교용: URL 디코딩 + 소문자 + 글자·숫자만. site_src/lib.js 의 anchorKey 와 같은 규칙이어야 한다
    (tests/test_anchor_sync.py 가 두 구현을 같은 입력으로 비교한다). JS 의 decodeURIComponent 는 깨진 %인코딩에서
    예외를 던져 원문을 그대로 쓰므로, 여기서도 엄격하게 디코딩하고 실패하면 원문을 쓴다."""
    try:
        s = urllib.parse.unquote(s, errors="strict")
    except UnicodeDecodeError:
        pass
    return re.sub(r"[\W_]", "", s.lower())


def strip_banner(content):
    """모든 페이지 맨 위의 'Documentation Index' 안내문(> 로 시작하는 줄들)을 뺀 본문 줄 목록."""
    lines = content.replace("\r\n", "\n").split("\n")
    if lines and lines[0].startswith("> ## Documentation Index"):
        while lines and (lines[0].startswith(">") or not lines[0].strip()):
            lines.pop(0)
    return lines


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def plain_text(content):
    """본문 검색용 평문: 마크다운 기호·태그·링크 주소를 걷어내고 공백을 한 칸으로 줄인다 (코드는 내용만 남김)."""
    t = "\n".join(l for l in strip_banner(content) if not FENCE.match(l))
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"</?[a-zA-Z][^<>]*>", " ", t)
    t = re.sub(r"^ {0,3}(?:#{1,6}|>+)[ \t]?", "", t, flags=re.M)
    t = re.sub(r"^[ \t]*\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$", "", t, flags=re.M)
    t = re.sub(r"[`*|]+|~~", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()
