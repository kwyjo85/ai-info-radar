"""이상 감지: 사이클 연속 실패, 사이클 지연(멈춤), 파이프라인 하루 비용 초과.

텔레그램 봇이 주기적으로 check()를 불러 새 문제는 알림, 계속되는 문제는 REMIND_HOURS마다 재알림,
사라진 문제는 복구 알림을 보낸다. 상태는 settings.alert_state에 저장 (봇 재시작 후에도 중복 알림 방지).

기준값은 .env로 조절: ALERT_FAIL_STREAK(기본 2), ALERT_STALE_MIN(기본 90), ALERT_DAILY_COST_USD(기본 3).
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values

from collectors import storage
from dashboard import ops

_ENV = dotenv_values(ROOT / ".env")
FAIL_STREAK = int(_ENV.get("ALERT_FAIL_STREAK") or 2)
STALE_MIN = int(_ENV.get("ALERT_STALE_MIN") or 90)
DAILY_COST_USD = float(_ENV.get("ALERT_DAILY_COST_USD") or 3)
REMIND_HOURS = 6
WAKE_GRACE_MIN = 45   # 맥이 깨어난 직후엔 launchd가 밀린 사이클을 돌릴 시간을 줌 (지연 판정 보류)
STATE_KEY = "alert_state"


def pipeline_cost_today(calls: list[dict], now: datetime) -> float:
    today = now.strftime("%Y-%m-%d")
    return sum(c.get("cost_usd") or 0 for c in calls if c.get("ts", "").startswith(today))


def detect(now: datetime, cycles: list[dict], calls: list[dict], check_stale: bool = True) -> dict[str, str]:
    """현재 문제 {키: 알림 문구}. 키가 같으면 같은 문제로 보고 중복 알림하지 않음."""
    issues = {}

    done = [c for c in cycles if c["status"] != "진행 중"]
    recent = done[-FAIL_STREAK:]
    if len(recent) == FAIL_STREAK and all(c["status"] != "정상" for c in recent):
        last = recent[-1]
        errs = "\n".join(f"  • {e[:150]}" for e in last["errors"][:3]) or "  • (사이클이 끝 줄 없이 중단됨)"
        issues["fail"] = f"⚠️ 사이클이 {FAIL_STREAK}회 연속 실패했습니다 (마지막 {last['start']:%m-%d %H:%M}).\n{errs}"

    if check_stale and cycles:
        last = cycles[-1]
        ago = (now - last["start"]).total_seconds() / 60
        if ago > STALE_MIN:
            if last["status"] == "진행 중":
                issues["stale"] = f"⏳ 사이클이 {ago:.0f}분째 끝나지 않고 있습니다 ({last['start']:%m-%d %H:%M} 시작). 멈춘 것일 수 있어요."
            else:
                issues["stale"] = (f"⛔ 마지막 사이클이 {ago:.0f}분 전입니다 (30분 주기). "
                                   "launchd 작업(com.ai-info-radar.cycle)이 멈췄을 수 있어요.")

    cost = pipeline_cost_today(calls, now)
    if cost > DAILY_COST_USD:
        issues[f"cost:{now:%Y-%m-%d}"] = (f"💸 오늘 파이프라인 LLM 추정 비용이 ${cost:.2f}로 기준(${DAILY_COST_USD:.2f})을 넘었습니다. "
                                          "주제 변경 직후 재채점이 몰렸거나 호출이 반복되고 있을 수 있어요.")
    return issues


def _load_state(conn) -> dict:
    raw = storage.get_setting(conn, STATE_KEY)
    return json.loads(raw) if raw else {}


def check(now: datetime | None = None, check_stale: bool = True) -> list[str]:
    """보낼 메시지 목록을 만들고 상태를 갱신. (전송은 호출하는 쪽에서)"""
    now = now or datetime.now()
    issues = detect(now, ops.parse_cycles(), ops.load_llm_calls(), check_stale)
    conn = storage.connect()
    try:
        state = _load_state(conn)
        messages = []
        for key, text in issues.items():
            prev = state.get(key)
            if prev is None:
                messages.append(text)
                state[key] = {"since": now.isoformat(timespec="seconds"), "notified": now.isoformat(timespec="seconds")}
            elif now - datetime.fromisoformat(prev["notified"]) >= timedelta(hours=REMIND_HOURS):
                messages.append(f"(계속) {text}")
                prev["notified"] = now.isoformat(timespec="seconds")
        for key in [k for k in state if k not in issues]:
            # 지연 판정을 보류한 동안(깨어난 직후)은 stale이 해결된 것으로 보지 않음
            if key == "stale" and not check_stale:
                continue
            since = datetime.fromisoformat(state.pop(key)["since"])
            if not key.startswith("cost:"):  # 비용 문제는 날짜가 바뀌면 조용히 해제
                label = {"fail": "사이클 실패", "stale": "사이클 지연"}.get(key, key)
                messages.append(f"✅ 복구됨: {label} ({since:%m-%d %H:%M}부터 {int((now - since).total_seconds() // 60)}분)")
        storage.set_setting(conn, STATE_KEY, json.dumps(state, ensure_ascii=False))
    finally:
        conn.close()
    return messages


def status_text(now: datetime | None = None) -> str:
    """텔레그램 「상태」 응답: 마지막 사이클, 최근 24시간, 오늘 비용, 진행 중인 문제."""
    now = now or datetime.now()
    cycles, calls = ops.parse_cycles(), ops.load_llm_calls()
    lines = ["🩺 AI 레이더 상태"]
    if cycles:
        last = cycles[-1]
        lines.append(f"• 마지막 사이클: {int((now - last['start']).total_seconds() // 60)}분 전 ({last['status']})")
        day = [c for c in cycles if c["start"] >= now - timedelta(hours=24)]
        bad = sum(c["status"] not in ("정상", "진행 중") for c in day)
        lines.append(f"• 최근 24시간: {len(day)}회" + (f", 문제 {bad}회" if bad else ", 모두 정상"))
    else:
        lines.append("• 사이클 기록 없음")
    today = [c for c in calls if c.get("ts", "").startswith(now.strftime("%Y-%m-%d"))]
    fails = sum(not c.get("ok") for c in today)
    lines.append(f"• 오늘 파이프라인 LLM: {len(today)}회, 추정 ${pipeline_cost_today(calls, now):.2f}"
                 + (f", 실패 {fails}회" if fails else "") + f" (알림 기준 ${DAILY_COST_USD:.2f})")
    conn = storage.connect()
    try:
        state = _load_state(conn)
    finally:
        conn.close()
    if state:
        lines.append("• 진행 중인 문제: " + ", ".join(
            {"fail": "사이클 실패", "stale": "사이클 지연"}.get(k, "비용 초과" if k.startswith("cost:") else k) for k in state))
    return "\n".join(lines)
