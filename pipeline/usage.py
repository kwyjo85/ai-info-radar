"""LLM 사용량 기록·비용 추정.

- record_call(): pipeline/llm.py가 호출마다 data/llm_usage.jsonl에 한 줄 기록 (작업 이름·토큰·비용·소요시간)
- estimate_cost(): API 정가 기준 추정 비용 (구독 요금제에서는 실제 청구액이 아니라 '환산치')

단가는 Anthropic API 정가(USD / 1M 토큰). 캐시 쓰기는 5분 TTL 1.25배, 1시간 TTL 2배.
"""

import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USAGE_LOG = ROOT / "data" / "llm_usage.jsonl"

# 모델: (입력, 출력, 캐시 읽기)
PRICES = {
    "claude-fable-5-1": (10.0, 50.0, 0.25),
    "claude-mythos-5-1": (10.0, 50.0, 0.25),
    "claude-fable-5": (10.0, 50.0, 1.0),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, 0.50),
    "claude-opus-4-8": (5.0, 25.0, 0.50),
    "claude-opus-4-7": (5.0, 25.0, 0.50),
    "claude-opus-4-6": (5.0, 25.0, 0.50),
    "claude-sonnet-5": (2.0, 10.0, 0.20),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30),
    "claude-haiku-4-5": (1.0, 5.0, 0.10),
}


def _price(model: str) -> tuple[float, float, float] | None:
    return PRICES.get(re.sub(r"-\d{8}$", "", model or ""))


def estimate_cost(model: str, input_tokens=0, output_tokens=0, cache_read=0, cache_write_5m=0, cache_write_1h=0) -> float | None:
    p = _price(model)
    if p is None:
        return None
    pin, pout, pread = p
    return (input_tokens * pin + output_tokens * pout + cache_read * pread
            + cache_write_5m * pin * 1.25 + cache_write_1h * pin * 2.0) / 1_000_000


def tokens_from_usage(usage: dict) -> dict:
    """API/CLI usage 객체 → 표준 토큰 필드."""
    cc = usage.get("cache_creation") or {}
    write_total = usage.get("cache_creation_input_tokens") or 0
    w1h = cc.get("ephemeral_1h_input_tokens") or 0
    w5m = cc.get("ephemeral_5m_input_tokens")
    if w5m is None:
        w5m = write_total - w1h
    return {
        "input_tokens": usage.get("input_tokens") or 0,
        "output_tokens": usage.get("output_tokens") or 0,
        "cache_read": usage.get("cache_read_input_tokens") or 0,
        "cache_write_5m": w5m,
        "cache_write_1h": w1h,
    }


def record_call(task: str, model: str, backend: str, ok: bool, duration_ms: int | None,
                tokens: dict | None = None, cost_usd: float | None = None, error: str | None = None,
                session_persisted: bool = False) -> None:
    """호출 1건 기록. 기록 실패가 파이프라인을 멈추지 않도록 예외는 삼킴.

    session_persisted: 이 호출이 ~/.claude/projects 세션 기록에도 남는지. 대시보드는 False인 줄만
    세션 집계에 더해 같은 호출을 두 번 세지 않는다.
    """
    tokens = tokens or {}
    if cost_usd is None and tokens:
        cost_usd = estimate_cost(model, **tokens)
    row = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "task": task, "model": model, "backend": backend, "ok": ok,
        "duration_ms": duration_ms, "session_persisted": session_persisted, **tokens,
        "cost_usd": round(cost_usd, 6) if cost_usd is not None else None,
    }
    if error:
        row["error"] = error[:300]
    try:
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass
