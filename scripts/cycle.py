"""30분 주기 사이클: 수집 → 처리 → 대시보드 배포 → git 동기화. launchd에서 호출됨.

실행: uv run python -m scripts.cycle
"""

import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.run import main as collect_main
from pipeline.process import main as process_main
from scripts.git_sync import sync as git_sync
from scripts.publish_dashboard import publish as publish_dashboard


STAGES = [
    ("collect", "수집", collect_main),
    ("process", "처리", process_main),
    ("publish", "대시보드 배포", publish_dashboard),
    ("git-sync", "동기화", git_sync),
]


def main():
    # 한 단계가 실패해도 다음 단계는 돈다 (예: 수집 실패여도 쌓인 항목 처리·배포는 진행).
    # '[단계] … 실패:' 줄은 운영 현황 대시보드(dashboard/ops.py)가 에러로 집계함.
    print(f"=== cycle start {datetime.now():%Y-%m-%d %H:%M:%S} ===", flush=True)
    for key, label, fn in STAGES:
        try:
            fn()
        except Exception as e:
            print(f"[{key}] {label} 실패: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()
    print(f"=== cycle end {datetime.now():%Y-%m-%d %H:%M:%S} ===", flush=True)


if __name__ == "__main__":
    main()
