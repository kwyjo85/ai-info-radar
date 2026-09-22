"""RSS 피드 수집기.

- config/feeds.yaml의 rss 목록: 항상 수집
- Hacker News 검색 피드(hnrss.org): 현재 주제의 검색 질의로 동적 생성
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import topic

log = logging.getLogger(__name__)


def load_feeds() -> list[tuple[str, str | None]]:
    """(feed_url, keyword) 목록. 고정 피드는 keyword None, HN 검색 피드는 질의어."""
    data = yaml.safe_load((ROOT / "config" / "feeds.yaml").read_text())
    feeds = [(url, None) for url in (data.get("rss") or [])]
    feeds += [(f"https://hnrss.org/newest?q={quote_plus(q)}", q) for q in topic.hn_queries()]
    return feeds


def _published(entry) -> str | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if not t:
        return None
    return datetime(*t[:6], tzinfo=timezone.utc).isoformat(timespec="seconds")


def collect() -> list[dict]:
    items = []
    for feed_url, keyword in load_feeds():
        parsed = feedparser.parse(feed_url)
        if parsed.bozo and not parsed.entries:
            log.warning("rss: 파싱 실패 %s (%s)", feed_url, parsed.bozo_exception)
            continue
        for entry in parsed.entries:
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
                "content": content[:5000],
                "keyword": keyword,
                "published_at": _published(entry),
            })
    log.info("rss: %d건 수집", len(items))
    return items
