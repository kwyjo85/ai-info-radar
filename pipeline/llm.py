"""LLM 백엔드 추상화.

기본: claude_cli (Claude Code 헤드리스, 구독 사용량 소비, 추가 비용 없음)
전환: .env에 LLM_BACKEND=api 설정 시 Anthropic API 사용 (ANTHROPIC_API_KEY 필요)
호출마다 작업 이름·토큰·추정 비용을 data/llm_usage.jsonl에 기록 (pipeline/usage.py).
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from dotenv import dotenv_values

from pipeline import usage

ROOT = Path(__file__).resolve().parent.parent
_ENV = dotenv_values(ROOT / ".env")

BACKEND = _ENV.get("LLM_BACKEND", "claude_cli")

API_MODELS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
}


# 헤드리스 호출은 텍스트만 돌려받으면 되므로 도구·MCP를 끄고 Claude Code 기본 시스템 프롬프트를 짧은 것으로 바꾼다.
# 기본 설정이면 호출마다 시스템 프롬프트·도구 정의로 약 3만 토큰이 붙고, 블루프린트 작성 중 Bash/Write 등을
# 스스로 호출하며 여러 번 왕복했다 (2026-09-27 측정: 입력 30,748 → 907 토큰).
CLI_SYSTEM_PROMPT = "You are a precise assistant inside an automated pipeline. Follow the requested output format exactly and output nothing else."
CLI_FLAGS = ["--tools", "", "--strict-mcp-config", "--system-prompt", CLI_SYSTEM_PROMPT, "--no-session-persistence"]

# 생각(thinking)을 끌 모델. 채점·주제 확장(haiku)은 형식이 정해진 JSON 작업이라 생각 토큰이 출력의 87%를 차지했고,
# 끄면 출력·비용이 절반 이하로 줄면서 점수가 더 일정했다 (2026-09-27, 10건 배치 반복 비교: 켬↔켬 평균 4.5점 차, 끔↔끔 2.3점 차).
# 블루프린트(sonnet)는 긴 글 작성이라 그대로 둔다.
NO_THINKING_MODELS = {"haiku"}


def _claude_bin() -> str:
    found = shutil.which("claude")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "claude"
    if fallback.exists():
        return str(fallback)
    raise RuntimeError("claude CLI를 찾을 수 없습니다. https://claude.ai/install.sh 로 설치하세요.")


def _complete_cli(prompt: str, model: str, task: str) -> str:
    env = dict(os.environ)
    # launchd 등 비로그인 환경용: `claude setup-token`으로 발급한 장기 토큰 주입
    oauth_token = _ENV.get("CLAUDE_CODE_OAUTH_TOKEN")
    if oauth_token and not env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
    if model in NO_THINKING_MODELS:
        env["MAX_THINKING_TOKENS"] = "0"
    r = subprocess.run(
        [_claude_bin(), "-p", "--model", model, "--output-format", "json", *CLI_FLAGS],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(ROOT),
        env=env,
    )
    try:
        out = json.loads(r.stdout)
    except json.JSONDecodeError:
        out = None
    if out is None or r.returncode != 0 or out.get("is_error"):
        detail = (out or {}).get("result") or r.stderr or r.stdout
        err = f"claude CLI 실패 (exit {r.returncode}): {detail[:500]}"
        usage.record_call(task, model, "claude_cli", False, (out or {}).get("duration_ms"), error=err)
        raise RuntimeError(err)
    # modelUsage 키가 실제 모델 ID ('sonnet' 같은 별칭이 무엇으로 풀렸는지)
    resolved = next(iter(out.get("modelUsage") or {}), model)
    usage.record_call(task, resolved, "claude_cli", True, out.get("duration_ms"),
                      tokens=usage.tokens_from_usage(out.get("usage") or {}), cost_usd=out.get("total_cost_usd"))
    return (out.get("result") or "").strip()


def _complete_api(prompt: str, model: str, task: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=_ENV.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))
    model_id = API_MODELS.get(model, model)
    started = time.monotonic()
    try:
        msg = client.messages.create(
            model=model_id,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        usage.record_call(task, model_id, "api", False, int((time.monotonic() - started) * 1000), error=f"{type(e).__name__}: {e}")
        raise
    usage.record_call(task, model_id, "api", True, int((time.monotonic() - started) * 1000),
                      tokens=usage.tokens_from_usage(msg.usage.model_dump()))
    return msg.content[0].text.strip()


def complete(prompt: str, model: str = "sonnet", task: str = "other") -> str:
    """model: 'haiku'(저렴/분류용) 또는 'sonnet'(블루프린트용). task: 사용량 기록용 작업 이름."""
    if BACKEND == "api":
        return _complete_api(prompt, model, task)
    return _complete_cli(prompt, model, task)
