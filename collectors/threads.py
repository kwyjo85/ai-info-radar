"""Threads keyword_search 수집기.

주의: threads_keyword_search 권한이 App Review 승인 전이라
현재는 본인 게시물만 검색됨. 심사 통과 후 공개 게시물 검색 가능.
쿼리 한도: 사용자당 롤링 24시간 2,200쿼리.
"""

import logging
from pathlib import Path

import httpx
import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
GRAPH = "https://graph.threads.net/v1.0"

log = logging.getLogger(__name__)


def load_keywords() -> list[str]:
    data = yaml.safe_load((ROOT / "config" / "keywords.yaml").read_text())
    return data["keywords"]


def collect() -> list[dict]:
    token = dotenv_values(ROOT / ".env").get("THREADS_ACCESS_TOKEN")
    if not token:
        log.warning("threads: 토큰 없음, 건너뜀")
        return []

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
                    log.warning("threads: keyword_search 권한 없음 (App Review 필요) — 수집 중단")
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
