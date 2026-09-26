"""RSS 피드 수집기.

- config/feeds.yaml의 rss 목록: 항상 수집
- Hacker News 검색 피드(hnrss.org): 현재 주제의 검색 질의로 동적 생성
- Google 뉴스 검색 피드: 주제가 설정된 경우 한/영 대표 키워드로 동적 생성
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors import storage
from collectors.article import html_to_text
from pipeline import topic

log = logging.getLogger(__name__)

MAX_ENTRIES_PER_FEED = 20   # 검색형 피드는 결과가 많아 최신 N건만 (채점 물량 보호)
GNEWS_KEYWORDS_PER_LANG = 2  # 주제 키워드 중 Google 뉴스 검색에 쓸 개수 (언어별)


def _gnews(query: str, lang: str) -> str:
    q = quote_plus(query)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def load_feeds() -> list[tuple[str, str | None]]:
    """(feed_url, keyword) 목록. 고정 피드는 keyword None, 검색 피드는 질의어."""
    data = yaml.safe_load((ROOT / "config" / "feeds.yaml").read_text())
    feeds = [(url, None) for url in (data.get("rss") or [])]
    feeds += [(f"https://hnrss.org/newest?q={quote_plus(q)}", q) for q in topic.hn_queries()]

    t = topic.get_topic()
    if t:
        feeds += [(_gnews(k, "en"), k) for k in t["keywords_en"][:GNEWS_KEYWORDS_PER_LANG]]
        feeds += [(_gnews(k, "ko"), k) for k in t["keywords_ko"][:GNEWS_KEYWORDS_PER_LANG]]
    return feeds


def _published(entry) -> str | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if not t:
        return None
    return datetime(*t[:6], tzinfo=timezone.utc).isoformat(timespec="seconds")


def _update_empty_streaks(queries: set[str], results: dict[str, bool]) -> None:
    """검색 질의별 연속 0건 횟수를 갱신하고, 기준에 처음 닿은 질의는 경고.

    queries: 이번 피드의 전체 검색 질의, results: 응답을 받은 질의 → 결과 있음 여부 (요청 실패한 질의는 기존 값 유지).
    """
    conn = storage.connect()
    try:
        raw = storage.get_setting(conn, topic.EMPTY_STREAK_KEY)
        old = json.loads(raw) if raw else {}
        # 현재 피드에 없는 질의(주제 변경으로 사라진 것)는 버림
        streaks = {q: old.get(q, 0) for q in queries}
        for q, found in results.items():
            streaks[q] = 0 if found else streaks[q] + 1
        for q, n in streaks.items():
            if n == topic.EMPTY_STREAK_WARN:
                log.warning("rss: 검색어 '%s' %d회 연속 결과 없음 — 주제 확인에서 안내", q, n)
        storage.set_setting(conn, topic.EMPTY_STREAK_KEY, json.dumps({q: n for q, n in streaks.items() if n}, ensure_ascii=False))
    finally:
        conn.close()


def collect() -> list[dict]:
    items = []
    searched: dict[str, bool] = {}  # 이번에 응답을 받은 검색 질의 → 결과 있음 여부 (요청 실패는 제외)
    feeds = load_feeds()
    for feed_url, keyword in feeds:
        parsed = feedparser.parse(feed_url)
        if keyword is not None and parsed.get("status") == 200:
            searched[keyword] = searched.get(keyword, False) or bool(parsed.entries)
        if not parsed.entries:
            # hnrss는 결과 0건일 때 빈 채널을 반환하는데 feedparser가 bozo로 표시함 — 정상 상황
            if parsed.get("status") == 200:
                log.info("rss: 결과 없음 %s", keyword or feed_url)
            else:
                log.warning(
                    "rss: 파싱 실패 %s (HTTP %s, %s)",
                    feed_url, parsed.get("status"), parsed.get("bozo_exception"),
                )
            continue
        entries = parsed.entries if keyword is None else parsed.entries[:MAX_ENTRIES_PER_FEED]
        for entry in entries:
            link = entry.get("link")
            if not link:
                continue
            content = entry.get("summary", "")
            if entry.get("content"):
                content = entry["content"][0].get("value", content)
            items.append({
                "source": "rss",
                "external_id": entry.get("id"),
                "url": link,
                "author": entry.get("author") or parsed.feed.get("title"),
                "title": entry.get("title"),
                "content": html_to_text(content)[:5000],
                "keyword": keyword,
                "published_at": _published(entry),
            })
    try:
        _update_empty_streaks({k for _, k in feeds if k is not None}, searched)
    except Exception:
        log.exception("rss: 검색어 0건 기록 실패")
    log.info("rss: %d건 수집", len(items))
    return items
