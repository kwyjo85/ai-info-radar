"""LLM 백엔드 추상화.

기본: claude_cli (Claude Code 헤드리스, 구독 사용량 소비, 추가 비용 없음)
전환: .env에 LLM_BACKEND=api 설정 시 Anthropic API 사용 (ANTHROPIC_API_KEY 필요)
"""

import os
import shutil
import subprocess
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
_ENV = dotenv_values(ROOT / ".env")

BACKEND = _ENV.get("LLM_BACKEND", "claude_cli")

API_MODELS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
}


def _claude_bin() -> str:
    found = shutil.which("claude")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "claude"
    if fallback.exists():
        return str(fallback)
    raise RuntimeError("claude CLI를 찾을 수 없습니다. https://claude.ai/install.sh 로 설치하세요.")


def _complete_cli(prompt: str, model: str) -> str:
    r = subprocess.run(
        [_claude_bin(), "-p", "--model", model, "--output-format", "text"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(ROOT),
    )
    if r.returncode != 0:
        raise RuntimeError(f"claude CLI 실패 (exit {r.returncode}): {r.stderr[:500]}")
    return r.stdout.strip()


def _complete_api(prompt: str, model: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=_ENV.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model=API_MODELS.get(model, model),
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def complete(prompt: str, model: str = "sonnet") -> str:
    """model: 'haiku'(저렴/분류용) 또는 'sonnet'(블루프린트용)."""
    if BACKEND == "api":
        return _complete_api(prompt, model)
    return _complete_cli(prompt, model)
