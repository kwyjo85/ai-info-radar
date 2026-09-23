"""사이클 끝 git 동기화: 새 블루프린트 커밋 → 원격 변경 반영(pull --rebase) → push.

Mac에서 손으로 하던 '블루프린트 커밋'과 'git pull'을 대신한다. 받아온 코드는 다음 사이클부터 적용.
main 브랜치에서만 동작하고, 실패하면 로그만 남기고 넘어간다(사이클은 계속 돔).
끄려면 .env에 RADAR_GIT_SYNC=0.

실행: uv run python -m scripts.git_sync
"""

import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
BRANCH = "main"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=120)


def _log(msg: str) -> None:
    print(f"[git-sync] {msg}", flush=True)


def sync() -> None:
    if (dotenv_values(ROOT / ".env").get("RADAR_GIT_SYNC") or "1").strip() == "0":
        return
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != BRANCH:
        _log(f"현재 브랜치 {branch!r} — {BRANCH}에서만 동기화, 건너뜀")
        return

    _git("add", "blueprints")
    if _git("diff", "--cached", "--quiet", "--", "blueprints").returncode != 0:
        r = _git("commit", "-q", "-m", "chore: 사이클 산출 블루프린트 추가", "--", "blueprints")
        if r.returncode != 0:
            _log(f"블루프린트 커밋 실패: {r.stderr.strip()[:300]}")
            return
        _log("블루프린트 커밋 완료")

    # 블루프린트 외에 손으로 고친 파일이 있으면 pull이 거부되므로 --autostash로 잠시 치워 둠
    r = _git("pull", "--rebase", "--autostash", "-q", "origin", BRANCH)
    if r.returncode != 0:
        _git("rebase", "--abort")
        _log(f"pull 실패 — 이번 사이클은 건너뜀: {r.stderr.strip()[:300]}")
        return

    if _git("rev-list", "--count", f"origin/{BRANCH}..HEAD").stdout.strip() not in ("", "0"):
        r = _git("push", "-q", "origin", f"HEAD:{BRANCH}")
        if r.returncode != 0:
            _log(f"push 실패: {r.stderr.strip()[:300]}")
            return
        _log("push 완료")


if __name__ == "__main__":
    sys.exit(sync())
