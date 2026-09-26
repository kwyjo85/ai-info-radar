"""Threads keyword_search 수집기.

주의: threads_keyword_search 권한이 App Review 승인 전이라
현재는 본인 게시물만 검색됨. 심사 통과 후 공개 게시물 검색 가능.
쿼리 한도: 사용자당 롤링 24시간 2,200쿼리.
권한 없음(App Review 전) 응답을 받으면 BLOCKED_RETRY_HOURS 동안 요청을 쉰다 (settings.threads_blocked_until).
"""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors import storage
from pipeline import topic

GRAPH = "https://graph.threads.net/v1.0"
BLOCKED_KEY = "threads_blocked_until"
BLOCKED_RETRY_HOURS = 24

log = logging.getLogger(__name__)


def load_keywords() -> list[str]:
    """현재 주제의 확장 키워드, 주제 미설정 시 config/keywords.yaml."""
    return topic.keywords()


def collect() -> list[dict]:
    token = dotenv_values(ROOT / ".env").get("THREADS_ACCESS_TOKEN")
    if not token:
        log.warning("threads: 토큰 없음, 건너뜀")
        return []
    conn = storage.connect()
    try:
        until = storage.get_setting(conn, BLOCKED_KEY)
        if until and datetime.now() < datetime.fromisoformat(until):
            log.info("threads: keyword_search 권한 없음 — %s까지 요청 쉼", until[:16].replace("T", " "))
            return []
        return _search(token, conn)
    finally:
        conn.close()


def _search(token: str, conn) -> list[dict]:

    items = []
    with httpx.Client(timeout=30) as client:
        for kw in load_keywords():
            try:
                r = client.get(f"{GRAPH}/keyword_search", params={
                    "q": kw,
                    "search_type": "RECENT",
                    "fields": "id,text,username,permalink,timestamp",
                    "access_token": token,
                })
            except httpx.HTTPError as e:
                log.warning("threads: 키워드 '%s' 요청 실패: %s", kw, type(e).__name__)
                continue
            if r.status_code != 200:
                # 토큰 노출 방지를 위해 URL 대신 에러 메시지만 로깅
                err = r.json().get("error", {}) if "json" in r.headers.get("content-type", "") else {}
                msg = err.get("message", r.text[:200])
                if err.get("error_subcode") == 4279067:  # App Review 전 액세스 티어 제한
                    until = (datetime.now() + timedelta(hours=BLOCKED_RETRY_HOURS)).isoformat(timespec="seconds")
                    storage.set_setting(conn, BLOCKED_KEY, until)
                    log.warning("threads: keyword_search 권한 없음 (App Review 필요) — %d시간 뒤 재시도", BLOCKED_RETRY_HOURS)
                    break
                log.warning("threads: 키워드 '%s' 검색 실패 (%d): %s", kw, r.status_code, msg)
                continue
            for post in r.json().get("data", []):
                if not post.get("permalink"):
                    continue
                items.append({
                    "source": "threads",
                    "external_id": post.get("id"),
                    "url": post["permalink"],
                    "author": post.get("username"),
                    "title": None,
                    "content": post.get("text", ""),
                    "keyword": kw,
                    "published_at": post.get("timestamp"),
                })
    log.info("threads: %d건 수집", len(items))
    return items
