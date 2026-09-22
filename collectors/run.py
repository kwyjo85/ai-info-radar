"""수집 오케스트레이터: 토큰 갱신 → 전체 수집기 실행 → SQLite upsert.

실행: uv run python -m collectors.run  (프로젝트 루트에서)
"""

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors import rss, storage, threads, youtube
from scripts.threads_auth import refresh_if_needed

LOG_DIR = ROOT / "logs"


def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_DIR / "collect.log"),
        ],
    )
    # httpx INFO 로그에 access_token이 포함된 URL이 찍히므로 차단
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main():
    setup_logging()
    log = logging.getLogger("collect")

    try:
        refresh_if_needed()
    except Exception as e:
        log.warning("토큰 갱신 실패 (수집은 계속): %s", e)

    conn = storage.connect()
    total_new = 0
    for collector in (threads, rss, youtube):
        name = collector.__name__.rsplit(".", 1)[-1]
        try:
            items = collector.collect()
        except Exception:
            log.exception("%s 수집기 실패", name)
            continue
        new = storage.upsert_items(conn, items)
        total_new += new
        log.info("%s: 수집 %d건 / 신규 %d건", name, len(items), new)

    total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    log.info("완료: 신규 %d건, DB 누적 %d건", total_new, total)
    conn.close()


if __name__ == "__main__":
    main()
