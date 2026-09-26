"""본문 텍스트 유틸: HTML → 텍스트 변환, 원문 페이지 본문 추출.

RSS 피드 요약은 HTML 태그투성이이고, HN·Google 뉴스 항목은 본문 없이 링크만 담겨 있다.
채점·블루프린트가 태그나 링크가 아닌 실제 글을 읽도록 여기서 정리한다.
"""

import logging
import re
from html.parser import HTMLParser

import httpx

log = logging.getLogger(__name__)

THIN_CHARS = 400         # 정리된 본문이 이보다 짧으면 '본문 없음'으로 간주
MAX_BODY_CHARS = 8000
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"

# 리다이렉트를 JS로 푸는 등 서버에서 본문을 얻을 수 없는 호스트
UNFETCHABLE = ("news.google.com",)

_SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "button", "iframe", "template"}
_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "tr", "section", "article", "main", "table"}
_VOID_TAGS = {"br", "img", "hr", "meta", "link", "input", "source", "wbr", "area", "base", "col", "embed", "param", "track"}


class _TextParser(HTMLParser):
    """전체 텍스트와 <main>, <article> 안쪽 텍스트를 따로 모은다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.depth = {"main": 0, "article": 0}
        self.all: list[str] = []
        self.parts: dict[str, list[str]] = {"main": [], "article": []}

    def handle_starttag(self, tag, attrs):
        if tag in _VOID_TAGS:
            if tag == "br":
                self._emit("\n")
            return
        if tag in _SKIP_TAGS:
            self.skip += 1
        elif tag in self.depth:
            self.depth[tag] += 1
        if tag in _BLOCK_TAGS:
            self._emit("\n")

    def handle_endtag(self, tag):
        if tag in _VOID_TAGS:
            return
        if tag in _SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
        elif tag in self.depth:
            self.depth[tag] = max(0, self.depth[tag] - 1)
        if tag in _BLOCK_TAGS:
            self._emit("\n")

    def handle_data(self, data):
        self._emit(data)

    def _emit(self, s: str):
        if self.skip:
            return
        self.all.append(s)
        for tag, d in self.depth.items():
            if d:
                self.parts[tag].append(s)


def _tidy(text: str) -> str:
    text = re.sub(r"[ \t\r\f\v\xa0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def html_to_text(html: str | None) -> str:
    """HTML(또는 일반 텍스트)을 읽을 수 있는 텍스트로. 태그가 없으면 공백만 정리."""
    if not html:
        return ""
    if "<" not in html:
        return _tidy(html)
    p = _TextParser()
    try:
        p.feed(html)
        p.close()
    except Exception:
        return _tidy(re.sub(r"<[^>]+>", " ", html))
    return _tidy("".join(p.all))


def is_thin(text: str | None) -> bool:
    """본문이 사실상 없는지: 짧거나, HN 피드처럼 링크·포인트 메타데이터뿐인 경우."""
    t = html_to_text(text)
    if "Article URL:" in t and "Points:" in t:
        return True
    return len(t) < THIN_CHARS


def fetch_body(url: str) -> str | None:
    """원문 페이지에서 본문 텍스트를 추출. 실패하거나 너무 짧으면 None."""
    if any(h in url for h in UNFETCHABLE):
        return None
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": UA})
    except httpx.HTTPError as e:
        log.info("본문 가져오기 실패 %s (%s)", url, type(e).__name__)
        return None
    if r.status_code != 200:
        log.info("본문 가져오기 실패 %s (HTTP %d)", url, r.status_code)
        return None
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype and "text/plain" not in ctype:
        log.info("본문 가져오기 건너뜀 %s (%s)", url, ctype[:40])
        return None

    if "html" in ctype:
        p = _TextParser()
        try:
            p.feed(r.text)
            p.close()
        except Exception:
            pass
        # 가장 좁은 본문 영역부터: <article>(블로그 글·GitHub README) → <main> → 페이지 전체
        candidates = [_tidy("".join(p.parts["article"])), _tidy("".join(p.parts["main"])), _tidy("".join(p.all))]
        body = next((c for c in candidates if len(c) >= THIN_CHARS), candidates[-1])
    else:
        body = _tidy(r.text)
    if len(body) < THIN_CHARS:
        log.info("본문 너무 짧음 %s (%d자)", url, len(body))
        return None
    return body[:MAX_BODY_CHARS]
