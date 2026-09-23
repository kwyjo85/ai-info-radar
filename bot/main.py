"""텔레그램 브리핑 봇 (롱폴링).

- 매일 정해진 시각(기본 08:00)에 다이제스트 브리핑: 상위 N건은 상세 카드, 나머지 신규 항목은 제목 목록
- /brief : 즉시 브리핑
- "브리핑 개수 : 10" / "브리핑 목록 개수 : 30" / "브리핑 시각 : 8, 18" / "브리핑 설정" : 브리핑 조절
- "주제 설정 : <문장>" 또는 /topic <문장> : 수집 주제 변경 (다음 변경까지 유지)
- "주제 확인" 또는 /topic : 현재 주제 보기
- 항목별 인라인 버튼: [블루프린트 보기] [구현 진행] [스킵]
  - 구현 진행 → 블루프린트를 tasks/pending/ 으로 복사 (Claude Code 작업 지시용)

실행: uv run python -m bot.main
"""

import asyncio
import datetime as dt
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from collectors import storage
from pipeline import topic

CYCLE_LAUNCHD_LABEL = "com.ai-info-radar.cycle"
TOPIC_SET_RE = re.compile(r"^\s*주제\s*(?:설정|변경)\s*[:：]\s*(.+)$", re.S)
TOPIC_SHOW_RE = re.compile(r"^\s*주제\s*(?:확인)?\s*$")

LOG_DIR = ROOT / "logs"
TASKS_PENDING = ROOT / "tasks" / "pending"

# 브리핑 기본값 — 텔레그램 명령으로 바꾸면 settings 테이블에 저장되어 우선함
BRIEF_DEFAULTS = {"top_n": 5, "list_n": 30, "hours": [8]}
BRIEF_CHECK_INTERVAL = 300  # 브리핑 전송 여부 점검 주기(초)
MSG_LIMIT = 4000     # 텔레그램 메시지 길이 제한 (4096) 여유분
BRIEF_CONFIG_KEY = "brief_config"
BRIEF_SENT_KEY = "brief_sent_slots"   # 오늘 전송한 시각 슬롯 ["YYYY-MM-DD:H", ...]

BRIEF_TOP_RE = re.compile(r"^\s*브리핑\s*개수\s*[:：]\s*(\d+)\s*$")
BRIEF_LIST_RE = re.compile(r"^\s*브리핑\s*목록\s*개수\s*[:：]\s*(\d+)\s*$")
BRIEF_HOURS_RE = re.compile(r"^\s*브리핑\s*시각\s*[:：]\s*([\d,\s시]+)$")
BRIEF_SHOW_RE = re.compile(r"^\s*브리핑\s*설정\s*$")

_ENV = dotenv_values(ROOT / ".env")
CHAT_ID = int(_ENV["TELEGRAM_CHAT_ID"])


def _dashboard_url() -> str | None:
    """RADAR_SITE_URL 또는 git origin(github.com:USER/REPO)에서 GitHub Pages 주소를 유도."""
    if _ENV.get("RADAR_SITE_URL"):
        return _ENV["RADAR_SITE_URL"]
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True, timeout=5).stdout.strip()
        m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
        return f"https://{m.group(1)}.github.io/{m.group(2)}/" if m else None
    except Exception:
        return None


DASHBOARD_URL = _dashboard_url()

log = logging.getLogger("bot")


def _buttons(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("블루프린트 보기", callback_data=f"bp:{item_id}"),
        InlineKeyboardButton("구현 진행", callback_data=f"go:{item_id}"),
        InlineKeyboardButton("스킵", callback_data=f"skip:{item_id}"),
    ]])


def _format_item(row) -> str:
    tag = "📰 뉴스" if row["kind"] == "뉴스" else "🛠 구현"
    uses = (row["use_cases"] or "").split("\n")
    lines = [
        f"[{row['score']}점 · {tag} · {row['category']}] {row['title'] or '(제목 없음)'}",
        f"💬 {row['easy']}" if row["easy"] else (row["summary"] or ""),
        "💡 이걸로 할 수 있는 것:\n" + "\n".join(f"  • {u.strip()}" for u in uses if u.strip()) if row["use_cases"] else "",
        row["url"],
    ]
    return "\n".join(l for l in lines if l)


def get_brief_config(conn) -> dict:
    cfg = dict(BRIEF_DEFAULTS)
    raw = storage.get_setting(conn, BRIEF_CONFIG_KEY)
    if raw:
        cfg.update(json.loads(raw))
    return cfg


def set_brief_config(conn, **changes) -> dict:
    cfg = get_brief_config(conn)
    cfg.update(changes)
    storage.set_setting(conn, BRIEF_CONFIG_KEY, json.dumps(cfg, ensure_ascii=False))
    return cfg


def format_brief_config(cfg: dict) -> str:
    hours = ", ".join(f"{h:02d}:00" for h in cfg["hours"])
    return (
        f"브리핑 설정\n"
        f"• 시각: {hours} (맥이 잠들어 있으면 깨어난 뒤 5분 내)\n"
        f"• 상세 카드: 상위 {cfg['top_n']}건\n"
        f"• 제목 목록: 그다음 {cfg['list_n']}건\n\n"
        "변경: 「브리핑 개수 : 10」 「브리핑 목록 개수 : 30」 「브리핑 시각 : 8, 18」"
    )


def _split_messages(lines: list[str], header: str = "") -> list[str]:
    """텔레그램 길이 제한에 맞춰 줄 목록을 여러 메시지로 나눔."""
    msgs, cur = [], header
    for line in lines:
        if len(cur) + len(line) + 1 > MSG_LIMIT:
            msgs.append(cur)
            cur = ""
        cur += ("\n" if cur else "") + line
    if cur:
        msgs.append(cur)
    return msgs


async def send_briefing(context: ContextTypes.DEFAULT_TYPE) -> None:
    """다이제스트: 상위 top_n건 상세 카드 + 다음 list_n건 제목 목록 + 나머지 건수와 대시보드 링크."""
    conn = storage.connect()
    current_topic = topic.topic_text(conn)
    cfg = get_brief_config(conn)
    # 다른 주제로 채점된 항목은 브리핑에서 제외 (대시보드에서는 볼 수 있음)
    rows = conn.execute(
        """SELECT id, COALESCE(title_ko, title) AS title, url, score, kind, category, summary, easy, use_cases FROM items
           WHERE status='processed' AND topic=? ORDER BY score DESC""",
        (current_topic,),
    ).fetchall()
    if not rows:
        await context.bot.send_message(CHAT_ID, f"브리핑할 새 항목이 없습니다.\n주제: {current_topic}")
        conn.close()
        return

    top, listed = rows[:cfg["top_n"]], rows[cfg["top_n"]:cfg["top_n"] + cfg["list_n"]]
    rest = len(rows) - len(top) - len(listed)
    header = (
        f"AI 레이더 브리핑 ({dt.date.today():%m/%d}) — 새 항목 {len(rows)}건\n"
        f"주제: {current_topic}\n"
        f"상세 {len(top)}건 · 목록 {len(listed)}건" + (f" · 그 외 {rest}건은 대시보드에서" if rest > 0 else "")
    )
    if DASHBOARD_URL:
        header += f"\n{DASHBOARD_URL}"
    await context.bot.send_message(CHAT_ID, header)

    for row in top:
        await context.bot.send_message(CHAT_ID, _format_item(row), reply_markup=_buttons(row["id"]))
        conn.execute("UPDATE items SET status='briefed' WHERE id=?", (row["id"],))

    if listed:
        lines = [
            f"{'🛠' if r['kind'] == '구현' else '📰'} {r['score']} · {(r['title'] or '(제목 없음)')[:70]}\n    {r['url']}"
            for r in listed
        ]
        for msg in _split_messages(lines, header="📋 그 외 신규 항목 (점수순)"):
            await context.bot.send_message(CHAT_ID, msg, disable_web_page_preview=True)
        for r in listed:
            conn.execute("UPDATE items SET status='briefed' WHERE id=?", (r["id"],))

    conn.commit()
    conn.close()


def _sent_slots(conn) -> list[str]:
    raw = storage.get_setting(conn, BRIEF_SENT_KEY)
    return json.loads(raw) if raw else []


async def daily_briefing_check(context: ContextTypes.DEFAULT_TYPE) -> None:
    """설정된 시각마다 오늘 그 슬롯의 브리핑이 아직 안 나갔으면 전송.

    run_daily 대신 주기 점검을 쓰는 이유: 맥이 예정 시각에 잠들어 있으면 스케줄러가 그 시각을
    놓치고(그리고 asyncio 타이머는 슬립 시간만큼 밀림), 깨어난 뒤에도 브리핑이 오지 않기 때문.
    """
    now = dt.datetime.now()
    today = now.date().isoformat()
    conn = storage.connect()
    cfg = get_brief_config(conn)
    sent = [s for s in _sent_slots(conn) if s.startswith(today)]  # 지난 날짜 슬롯은 버림
    due = [h for h in cfg["hours"] if now.hour >= h and f"{today}:{h}" not in sent]
    if not due:
        conn.close()
        return
    # 여러 슬롯을 한 번에 놓쳤어도(오래 잠들었던 경우) 브리핑은 1회만
    log.info("브리핑 전송 (예정 %s, 실제 %s)", ", ".join(f"{h:02d}:00" for h in due), now.strftime("%H:%M"))
    sent += [f"{today}:{h}" for h in due]
    storage.set_setting(conn, BRIEF_SENT_KEY, json.dumps(sent))
    conn.close()
    await send_briefing(context)


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_briefing(context)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "AI Info Radar 봇입니다.\n"
        "/brief — 지금 브리핑 받기\n"
        "브리핑 설정 — 시각·개수 보기\n"
        "브리핑 개수 : 10 / 브리핑 목록 개수 : 30 / 브리핑 시각 : 8, 18\n"
        "주제 설정 : <문장> — 수집 주제 변경 (다음 변경까지 유지)\n"
        "주제 확인 — 현재 주제 보기"
    )


def _kickstart_cycle() -> bool:
    """주제 변경 즉시 수집·처리 사이클을 한 번 돌림 (launchd 미설치 환경이면 False)."""
    try:
        r = subprocess.run(
            ["launchctl", "kickstart", f"gui/{os.getuid()}/{CYCLE_LAUNCHD_LABEL}"],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


async def _apply_topic(update: Update, text: str) -> None:
    if update.effective_chat.id != CHAT_ID:
        return
    await update.message.reply_text(f"주제를 분석해 검색어를 만들고 있습니다…\n「{text.strip()}」")
    try:
        data = await asyncio.to_thread(topic.set_topic, text)
    except Exception as e:
        log.exception("주제 설정 실패")
        await update.message.reply_text(f"주제 설정에 실패했습니다: {type(e).__name__}: {e}")
        return

    kicked = _kickstart_cycle()
    requeued = data.get("requeued", 0)
    tail = (
        f"새 주제로 수집을 시작하고, 기존 항목 {requeued}건을 새 주제 기준으로 다시 평가합니다 "
        "(5~10분 소요). 끝나면 /brief 로 확인하세요."
        if kicked else
        f"다음 30분 사이클부터 새 주제로 수집·재평가({requeued}건)됩니다."
    )
    await update.message.reply_text("주제를 설정했습니다.\n\n" + topic.format_topic(data) + "\n\n" + tail)


async def cmd_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args) if context.args else ""
    if text:
        await _apply_topic(update, text)
    else:
        await update.message.reply_text(topic.format_topic(topic.get_topic()))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    if update.effective_chat.id != CHAT_ID:
        return
    if m := TOPIC_SET_RE.match(text):
        await _apply_topic(update, m.group(1))
    elif TOPIC_SHOW_RE.match(text):
        await update.message.reply_text(topic.format_topic(topic.get_topic()))
    elif m := BRIEF_TOP_RE.match(text):
        n = max(1, min(20, int(m.group(1))))
        conn = storage.connect(); cfg = set_brief_config(conn, top_n=n); conn.close()
        await update.message.reply_text(f"상세 카드 개수를 {n}건으로 바꿨습니다.\n\n" + format_brief_config(cfg))
    elif m := BRIEF_LIST_RE.match(text):
        n = max(0, min(100, int(m.group(1))))
        conn = storage.connect(); cfg = set_brief_config(conn, list_n=n); conn.close()
        await update.message.reply_text(f"제목 목록 개수를 {n}건으로 바꿨습니다.\n\n" + format_brief_config(cfg))
    elif m := BRIEF_HOURS_RE.match(text):
        hours = sorted({int(h) for h in re.findall(r"\d+", m.group(1)) if 0 <= int(h) <= 23})
        if not hours:
            await update.message.reply_text("시각을 0~23 사이 숫자로 적어주세요. 예) 브리핑 시각 : 8, 18")
            return
        conn = storage.connect(); cfg = set_brief_config(conn, hours=hours); conn.close()
        await update.message.reply_text("브리핑 시각을 바꿨습니다.\n\n" + format_brief_config(cfg))
    elif BRIEF_SHOW_RE.match(text):
        conn = storage.connect(); cfg = get_brief_config(conn); conn.close()
        await update.message.reply_text(format_brief_config(cfg))


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action, item_id = query.data.split(":")
    item_id = int(item_id)

    conn = storage.connect()
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if not row:
        await query.message.reply_text(f"항목 {item_id}을 찾을 수 없습니다.")
        conn.close()
        return

    if action == "bp":
        if row["blueprint_path"]:
            text = (ROOT / row["blueprint_path"]).read_text()[:MSG_LIMIT]
        else:
            text = "블루프린트가 아직 없습니다 (점수 70 미만이거나 다음 처리 대기 중)."
        await query.message.reply_text(text)

    elif action == "go":
        if row["blueprint_path"]:
            src = ROOT / row["blueprint_path"]
            TASKS_PENDING.mkdir(parents=True, exist_ok=True)
            dst = TASKS_PENDING / src.name
            shutil.copy(src, dst)
            conn.execute("UPDATE items SET status='approved' WHERE id=?", (item_id,))
            conn.commit()
            await query.message.reply_text(
                f"구현 작업으로 등록했습니다.\ntasks/pending/{dst.name}\n"
                "Claude Code에서 이 파일을 열어 구현을 시작하세요."
            )
        else:
            await query.message.reply_text("블루프린트가 없어 등록할 수 없습니다.")

    elif action == "skip":
        conn.execute("UPDATE items SET status='skipped' WHERE id=?", (item_id,))
        conn.commit()
        await query.message.reply_text("스킵했습니다.")

    conn.close()


def main():
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(LOG_DIR / "bot.log")],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    app = Application.builder().token(_ENV["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("brief", cmd_brief))
    app.add_handler(CommandHandler("topic", cmd_topic))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_button))
    app.job_queue.run_repeating(daily_briefing_check, interval=BRIEF_CHECK_INTERVAL, first=10)

    log.info("봇 시작 (롱폴링, 브리핑 시각은 settings.brief_config, 기본 %s)", BRIEF_DEFAULTS["hours"])
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
