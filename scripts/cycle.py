"""30분 주기 사이클: 수집 → 처리. launchd에서 호출됨.

실행: uv run python -m scripts.cycle
"""

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.run import main as collect_main
from pipeline.process import main as process_main


def main():
    print(f"=== cycle start {datetime.now():%Y-%m-%d %H:%M:%S} ===", flush=True)
    collect_main()
    process_main()
    print(f"=== cycle end {datetime.now():%Y-%m-%d %H:%M:%S} ===", flush=True)


if __name__ == "__main__":
    main()
