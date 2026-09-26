"""DB 백업: data/radar.db를 백업 폴더(기본 iCloud Drive)에 하루 1개 파일로 복사, 최근 N일만 보관.

Mac이 고장 나도 수집·채점 기록을 다른 Mac에서 복구할 수 있게 한다(복구는 scripts/install_mac.sh).
사이클마다 호출되며 같은 날에는 그날 파일을 덮어쓴다. sqlite 백업 API를 써서 사용 중에도 안전하게 복사.

.env 설정:
  RADAR_BACKUP_DIR   백업 폴더 (기본: iCloud Drive/ai-info-radar-backup, iCloud가 없으면 건너뜀)
  RADAR_BACKUP_KEEP  보관 일수 (기본 14)

실행: uv run python -m scripts.backup_db
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "radar.db"
ICLOUD = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"


def backup_dir() -> Path | None:
    custom = (dotenv_values(ROOT / ".env").get("RADAR_BACKUP_DIR") or "").strip()
    if custom:
        return Path(custom).expanduser()
    return ICLOUD / "ai-info-radar-backup" if ICLOUD.is_dir() else None


def backup() -> Path | None:
    dest_dir = backup_dir()
    if dest_dir is None:
        print("[backup] iCloud Drive 없음 — RADAR_BACKUP_DIR 설정 시 백업", flush=True)
        return None
    if not DB_PATH.exists():
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"radar-{datetime.now():%Y-%m-%d}.db"
    tmp = dest.with_suffix(".db.tmp")

    src = sqlite3.connect(DB_PATH)
    out = sqlite3.connect(tmp)
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()
    tmp.replace(dest)  # 복사 도중 끊겨도 기존 백업이 반쯤 쓰인 파일로 바뀌지 않게

    keep = int((dotenv_values(ROOT / ".env").get("RADAR_BACKUP_KEEP") or "14").strip())
    for old in sorted(dest_dir.glob("radar-*.db"))[:-keep]:
        old.unlink()
    print(f"[backup] {dest}", flush=True)
    return dest


if __name__ == "__main__":
    backup()
