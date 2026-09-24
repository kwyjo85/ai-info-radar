"""30분 주기 사이클: 수집 → 처리 → DB 백업 → 대시보드 배포 → git 동기화. launchd에서 호출됨.

실행: uv run python -m scripts.cycle
"""

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.run import main as collect_main
from pipeline.process import main as process_main
from scripts.backup_db import backup as backup_db
from scripts.git_sync import sync as git_sync
from scripts.publish_dashboard import publish as publish_dashboard


def main():
    print(f"=== cycle start {datetime.now():%Y-%m-%d %H:%M:%S} ===", flush=True)
    collect_main()
    process_main()
    try:
        backup_db()
    except Exception as e:
        print(f"[backup] DB 백업 실패: {e}", flush=True)
    try:
        publish_dashboard()
    except Exception as e:
        print(f"[publish] 대시보드 배포 실패: {e}", flush=True)
    try:
        git_sync()
    except Exception as e:
        print(f"[git-sync] 동기화 실패: {e}", flush=True)
    print(f"=== cycle end {datetime.now():%Y-%m-%d %H:%M:%S} ===", flush=True)


if __name__ == "__main__":
    main()
