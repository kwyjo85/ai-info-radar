"""YouTube 수집기: 채널 RSS로 새 영상 목록 → 자막(transcript) 수집.

config/feeds.yaml의 youtube_channels(채널 ID 목록) 사용.
API 키 불필요 (채널 RSS + youtube-transcript-api).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml
from youtube_transcript_api import YouTubeTranscriptApi

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger(__name__)

CHANNEL_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
MAX_TRANSCRIPT_CHARS = 8000


def load_channels() -> list[str]:
    data = yaml.safe_load((ROOT / "config" / "feeds.yaml").read_text())
    return data.get("youtube_channels") or []


def _transcript(video_id: str) -> str | None:
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=["ko", "en"])
        return " ".join(s.text for s in fetched)[:MAX_TRANSCRIPT_CHARS]
    except Exception as e:
        log.debug("youtube: 자막 없음 %s (%s)", video_id, e)
        return None


def collect() -> list[dict]:
    items = []
    for cid in load_channels():
        parsed = feedparser.parse(CHANNEL_FEED.format(cid=cid))
        if not parsed.entries:
            log.warning("youtube: 채널 피드 비어있음 %s", cid)
            continue
        for entry in parsed.entries:
            video_id = entry.get("yt_videoid")
            link = entry.get("link")
            if not video_id or not link:
                continue
            transcript = _transcript(video_id)
            t = entry.get("published_parsed")
            items.append({
                "source": "youtube",
                "external_id": video_id,
                "url": link,
                "author": entry.get("author"),
                "title": entry.get("title"),
                "content": transcript or entry.get("summary", ""),
                "keyword": None,
                "published_at": datetime(*t[:6], tzinfo=timezone.utc).isoformat(timespec="seconds") if t else None,
            })
    log.info("youtube: %d건 수집", len(items))
    return items
