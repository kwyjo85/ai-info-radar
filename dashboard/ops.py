"""운영 현황 데이터: 사이클 실행 기록, Claude Code 세션 사용량, 파이프라인 LLM 호출 기록.

- 사이클: logs/launchd.cycle.log 를 파싱 (scripts/cycle.py가 남기는 시작/끝 줄과 각 단계 로그)
- 세션 사용량: ~/.claude/projects/**/*.jsonl (Claude Code 대화 기록). 대화형 세션과
  파이프라인의 `claude -p` 호출(entrypoint=sdk-cli)이 모두 들어 있어 과거분까지 집계된다.
- LLM 호출: data/llm_usage.jsonl (pipeline/llm.py가 기록, 성공/실패·작업 이름 포함)
  2026-09-27부터 파이프라인 호출은 세션 기록을 남기지 않으므로(--no-session-persistence) 이 파일이 원천.

비용은 API 정가로 환산한 추정치 (pipeline/usage.py). 구독 요금제의 실제 청구액과 다르다.
"""

import json
import re
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import usage  # noqa: E402

CYCLE_LOG = ROOT / "logs" / "launchd.cycle.log"
SESSIONS_DIR = Path.home() / ".claude" / "projects"

_TS = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
_START = re.compile(rf"^=== cycle start {_TS} ===")
_END = re.compile(rf"^=== cycle end {_TS} ===")
_LINE_TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ (\w+) ([\w.]+): (.*)$")
_NEW = re.compile(r"완료: 신규 (\d+)건")
_PROCESSED = re.compile(r"완료: 점수 (\d+)건, 블루프린트 (\d+)건")
_STAGE_FAIL = re.compile(r"^\[([\w-]+)\] .*실패: (.*)$")

# 파이프라인 헤드리스 호출을 첫 프롬프트로 구분 (pipeline/process.py, topic.py의 프롬프트 첫머리)
_TASK_MARKERS = [("당신은 정보 큐레이터", "score"), ("AI 자동화 구현 컨설턴트", "blueprint"), ("검색어를 만들어 주세요", "topic")]


def _dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def parse_cycles(path: Path = CYCLE_LOG) -> list[dict]:
    """사이클 실행 목록 (오래된 순). status: 정상 | 에러 | 중단(끝 줄 없이 다음 사이클 시작/진행 중)."""
    if not path.exists():
        return []
    runs, cur = [], None

    def close(end: datetime | None):
        cur["end"] = end
        cur["duration_s"] = (end - cur["start"]).total_seconds() if end else None
        cur["status"] = "중단" if end is None else ("에러" if cur["errors"] else "정상")
        runs.append(cur)

    for line in path.read_text(errors="replace").splitlines():
        if m := _START.match(line):
            if cur:
                close(None)
            cur = {"start": _dt(m.group(1)), "new": None, "scored": None, "blueprints": None,
                   "publish": None, "errors": [], "warnings": 0}
            continue
        if cur is None:
            continue
        if m := _END.match(line):
            close(_dt(m.group(1)))
            cur = None
            continue
        if m := _STAGE_FAIL.match(line):
            cur["errors"].append(f"[{m.group(1)}] {m.group(2)}")
        elif line.startswith("[publish] 대시보드 배포 실패"):
            cur["errors"].append(line)
        if m := _LINE_TS.match(line):
            _, level, logger, msg = m.groups()
            if level in ("ERROR", "CRITICAL"):
                cur["errors"].append(f"{logger}: {msg}")
            elif level == "WARNING":
                cur["warnings"] += 1
            if n := _NEW.search(msg):
                cur["new"] = int(n.group(1))
            if p := _PROCESSED.search(msg):
                cur["scored"], cur["blueprints"] = int(p.group(1)), int(p.group(2))
            if "대시보드 배포 완료" in msg:
                cur["publish"] = "배포"
            elif "배포 건너뜀" in msg:
                cur["publish"] = "건너뜀"
    if cur:
        cur["end"], cur["duration_s"], cur["status"] = None, None, "진행 중"
        runs.append(cur)
    return runs


def _local_date(ts: str) -> tuple[str, str]:
    """UTC ISO 타임스탬프 → (로컬 날짜, 로컬 시각 문자열)."""
    t = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    return t.strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d %H:%M")


@lru_cache(maxsize=None)
def _project_name(cwd: str | None, folder: str) -> str:
    """작업 폴더가 속한 git 저장소 이름 (하위 폴더에서 실행한 세션도 같은 프로젝트로 묶음)."""
    if not cwd:
        return folder
    p = Path(cwd)
    for d in (p, *p.parents):
        if (d / ".git").exists():
            return d.name
    return p.name


def parse_session_file(path: Path) -> list[dict]:
    """세션 기록 파일 1개 → 응답 메시지별 사용량 (message.id로 중복 제거)."""
    msgs: dict[str, dict] = {}
    first_prompt = None
    folder = path.relative_to(SESSIONS_DIR).parts[0] if SESSIONS_DIR in path.parents else path.parent.name
    for line in path.open(errors="replace"):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if first_prompt is None and d.get("type") == "user":
            c = (d.get("message") or {}).get("content")
            if isinstance(c, str):
                first_prompt = c
            elif isinstance(c, list):
                first_prompt = next((b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"), None)
        if d.get("type") != "assistant":
            continue
        m = d.get("message") or {}
        u, model = m.get("usage"), m.get("model")
        if not u or not model or model.startswith("<"):
            continue
        date, at = _local_date(d["timestamp"])
        msgs[m.get("id") or d.get("uuid")] = {
            "date": date, "at": at, "model": model,
            "project": _project_name(d.get("cwd"), folder),
            "mode": "파이프라인" if d.get("entrypoint") == "sdk-cli" else "대화형",
            "session": d.get("sessionId") or path.stem,
            **usage.tokens_from_usage(u),
        }
    task = None
    if first_prompt:
        task = next((t for marker, t in _TASK_MARKERS if marker in first_prompt[:400]), None)
    rows = list(msgs.values())
    for r in rows:
        r["task"] = task if r["mode"] == "파이프라인" else None
        r["cost_usd"] = usage.estimate_cost(
            r["model"], r["input_tokens"], r["output_tokens"], r["cache_read"], r["cache_write_5m"], r["cache_write_1h"]
        )
    return rows


def session_files() -> list[Path]:
    return sorted(SESSIONS_DIR.rglob("*.jsonl")) if SESSIONS_DIR.exists() else []


def load_llm_calls(path: Path = usage.USAGE_LOG) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def usage_rows_from_calls(calls: list[dict], project: str = ROOT.name) -> list[dict]:
    """llm_usage 기록 중 세션 기록에 없는 호출을 세션 사용량과 같은 모양으로 (이중 집계 방지)."""
    rows = []
    for i, c in enumerate(calls):
        if c.get("session_persisted", True) or not c.get("ok"):
            continue
        t = datetime.fromisoformat(c["ts"])
        rows.append({
            "date": t.strftime("%Y-%m-%d"), "at": t.strftime("%Y-%m-%d %H:%M"), "model": c["model"],
            "project": project, "mode": "파이프라인", "session": f"call-{i}", "task": c.get("task"),
            **{k: c.get(k) or 0 for k in ("input_tokens", "output_tokens", "cache_read", "cache_write_5m", "cache_write_1h")},
            "cost_usd": c.get("cost_usd"),
        })
    return rows
