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
    title_ko      TEXT,                     -- 한국어 제목 (채점 시 생성)
    content       TEXT,
    keyword       TEXT,                     -- 매칭된 검색 키워드
    published_at  TEXT,
    collected_at  TEXT NOT NULL,
    -- 3단계 처리기에서 채움
    score         INTEGER,
    kind          TEXT,                     -- 구현 (기법/도구/워크플로우) | 뉴스 (출시소식/의견/홍보)
    category      TEXT,
    summary       TEXT,
    easy          TEXT,                     -- 전문용어 없는 쉬운 설명 1~2문장
    use_cases     TEXT,                     -- '이걸로 할 수 있는 것' 예시 (줄바꿈 구분)
    blueprint_path TEXT,
    processed_at  TEXT,
    status        TEXT NOT NULL DEFAULT 'new'  -- new | processed | briefed | approved | skipped
);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_score ON items(score);

-- 런타임 설정 (현재 수집 주제 등). 텔레그램에서 바꾸고 수집기/처리기가 읽음.
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

DEFAULT_TOPIC = "AI 기반 업무 효율화·자동화"


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
    for col, ddl in {"kind": "TEXT", "topic": "TEXT", "easy": "TEXT", "use_cases": "TEXT", "title_ko": "TEXT"}.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE items ADD COLUMN {col} {ddl}")
    # 주제 기능 도입 전에 채점된 항목은 기본 주제로 간주 (브리핑 필터에서 빠지지 않게)
    conn.execute(
        "UPDATE items SET topic=? WHERE topic IS NULL AND status != 'new'", (DEFAULT_TOPIC,)
    )
    conn.commit()


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
        (key, value, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()


def upsert_items(conn: sqlite3.Connection, items: list[dict], topic: str | None = None) -> int:
    """url 기준 upsert. 새로 삽입된 건수 반환. topic은 수집 시점의 주제 태그."""
    now = datetime.now().isoformat(timespec="seconds")
    inserted = 0
    for it in items:
        cur = conn.execute(
            """INSERT INTO items
               (source, external_id, url, author, title, content, keyword, published_at, collected_at, topic)
               VALUES (:source, :external_id, :url, :author, :title, :content, :keyword, :published_at, :collected_at, :topic)
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
                "topic": topic,
            },
        )
        inserted += cur.rowcount
    conn.commit()
    return inserted
