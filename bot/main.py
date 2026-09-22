"""텔레그램 브리핑 봇 (롱폴링).

- 매일 08:00 상위 항목 브리핑 자동 전송
- /brief : 즉시 브리핑
- "주제 설정 : <문장>" 또는 /topic <문장> : 수집 주제 변경 (다음 변경까지 유지)
- "주제 확인" 또는 /topic : 현재 주제 보기
- 항목별 인라인 버튼: [블루프린트 보기] [구현 진행] [스킵]
  - 구현 진행 → 블루프린트를 tasks/pending/ 으로 복사 (Claude Code 작업 지시용)

실행: uv run python -m bot.main
"""

import asyncio
import datetime as dt
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

BRIEF_HOUR = 8       # 매일 브리핑 시각
BRIEF_TOP_N = 5      # 브리핑 항목 수
MSG_LIMIT = 4000     # 텔레그램 메시지 길이 제한 (4096) 여유분

_ENV = dotenv_values(ROOT / ".env")
CHAT_ID = int(_ENV["TELEGRAM_CHAT_ID"])

log = logging.getLogger("bot")


def _buttons(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("블루프린트 보기", callback_data=f"bp:{item_id}"),
        InlineKeyboardButton("구현 진행", callback_data=f"go:{item_id}"),
        InlineKeyboardButton("스킵", callback_data=f"skip:{item_id}"),
    ]])


def _format_item(row) -> str:
    tag = "📰 뉴스" if row["kind"] == "뉴스" else "🛠 구현"
    lines = [
        f"[{row['score']}점 · {tag} · {row['category']}] {row['title'] or '(제목 없음)'}",
        row["summary"] or "",
        row["url"],
    ]
    return "\n".join(l for l in lines if l)


async def send_briefing(context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = storage.connect()
    current_topic = topic.topic_text(conn)
    # 다른 주제로 채점된 항목은 브리핑에서 제외 (대시보드에서는 볼 수 있음)
    rows = conn.execute(
        """SELECT id, title, url, score, kind, category, summary FROM items
           WHERE status='processed' AND topic=? ORDER BY score DESC LIMIT ?""",
        (current_topic, BRIEF_TOP_N),
    ).fetchall()
    if not rows:
        await context.bot.send_message(CHAT_ID, f"오늘 브리핑할 새 항목이 없습니다.\n주제: {current_topic}")
        conn.close()
        return

    await context.bot.send_message(
        CHAT_ID,
        f"AI 레이더 브리핑 — 상위 {len(rows)}건 ({dt.date.today():%m/%d})\n주제: {current_topic}",
    )
    for row in rows:
        await context.bot.send_message(
            CHAT_ID, _format_item(row), reply_markup=_buttons(row["id"])
        )
        conn.execute("UPDATE items SET status='briefed' WHERE id=?", (row["id"],))
    conn.commit()
    conn.close()


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_briefing(context)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "AI Info Radar 봇입니다.\n"
        "/brief — 지금 브리핑 받기\n"
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
    tail = (
        "새 주제로 수집·처리를 시작했습니다 (수 분 소요). /brief 로 확인하세요."
        if kicked else
        "다음 30분 사이클부터 새 주제로 수집됩니다."
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
    if m := TOPIC_SET_RE.match(text):
        await _apply_topic(update, m.group(1))
    elif TOPIC_SHOW_RE.match(text):
        await update.message.reply_text(topic.format_topic(topic.get_topic()))


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
    app.job_queue.run_daily(send_briefing, time=dt.time(hour=BRIEF_HOUR, minute=0))

    log.info("봇 시작 (롱폴링, 매일 %02d:00 브리핑)", BRIEF_HOUR)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
