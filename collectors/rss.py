"""RSS 피드 수집기. config/feeds.yaml의 rss 목록을 읽음."""

import logging
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger(__name__)


def load_feeds() -> list[str]:
    data = yaml.safe_load((ROOT / "config" / "feeds.yaml").read_text())
    return data.get("rss") or []


def _published(entry) -> str | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if not t:
        return None
    return datetime(*t[:6], tzinfo=timezone.utc).isoformat(timespec="seconds")


def collect() -> list[dict]:
    items = []
    for feed_url in load_feeds():
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
                "keyword": None,
                "published_at": _published(entry),
            })
    log.info("rss: %d건 수집", len(items))
    return items
