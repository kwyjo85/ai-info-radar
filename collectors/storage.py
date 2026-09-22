"""SQLite 스토리지: items 테이블 관리."""

import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "radar.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,            -- threads | rss | youtube
    external_id   TEXT,
    url           TEXT NOT NULL UNIQUE,     -- permalink 기준 중복 제거
    author        TEXT,
    title         TEXT,
    content       TEXT,
    keyword       TEXT,                     -- 매칭된 검색 키워드
    published_at  TEXT,
    collected_at  TEXT NOT NULL,
    -- 3단계 처리기에서 채움
    score         INTEGER,
    kind          TEXT,                     -- 구현 (기법/도구/워크플로우) | 뉴스 (출시소식/의견/홍보)
    category      TEXT,
    summary       TEXT,
    blueprint_path TEXT,
    processed_at  TEXT,
    status        TEXT NOT NULL DEFAULT 'new'  -- new | processed | briefed | approved | skipped
);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_score ON items(score);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """기존 DB에 새 컬럼 추가 (CREATE TABLE IF NOT EXISTS는 기존 테이블을 바꾸지 않음)."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(items)")}
    for col, ddl in {"kind": "TEXT"}.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE items ADD COLUMN {col} {ddl}")
    conn.commit()


def upsert_items(conn: sqlite3.Connection, items: list[dict]) -> int:
    """url 기준 upsert. 새로 삽입된 건수 반환."""
    now = datetime.now().isoformat(timespec="seconds")
    inserted = 0
    for it in items:
        cur = conn.execute(
            """INSERT INTO items
               (source, external_id, url, author, title, content, keyword, published_at, collected_at)
               VALUES (:source, :external_id, :url, :author, :title, :content, :keyword, :published_at, :collected_at)
               ON CONFLICT(url) DO NOTHING""",
            {
                "source": it["source"],
                "external_id": it.get("external_id"),
                "url": it["url"],
                "author": it.get("author"),
                "title": it.get("title"),
                "content": it.get("content"),
                "keyword": it.get("keyword"),
                "published_at": it.get("published_at"),
                "collected_at": now,
            },
        )
        inserted += cur.rowcount
    conn.commit()
    return inserted
