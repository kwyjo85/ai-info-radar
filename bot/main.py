"""텔레그램 브리핑 봇 (롱폴링).

- 매일 08:00 상위 항목 브리핑 자동 전송
- /brief : 즉시 브리핑
- 항목별 인라인 버튼: [블루프린트 보기] [구현 진행] [스킵]
  - 구현 진행 → 블루프린트를 tasks/pending/ 으로 복사 (Claude Code 작업 지시용)

실행: uv run python -m bot.main
"""

import datetime as dt
import logging
import shutil
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
)

from collectors import storage

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
    rows = conn.execute(
        """SELECT id, title, url, score, kind, category, summary FROM items
           WHERE status='processed' ORDER BY score DESC LIMIT ?""",
        (BRIEF_TOP_N,),
    ).fetchall()
    if not rows:
        await context.bot.send_message(CHAT_ID, "오늘 브리핑할 새 항목이 없습니다.")
        conn.close()
        return

    await context.bot.send_message(
        CHAT_ID, f"AI 레이더 브리핑 — 상위 {len(rows)}건 ({dt.date.today():%m/%d})"
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
        "AI Info Radar 봇입니다.\n/brief — 지금 브리핑 받기"
    )


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
    app.add_handler(CallbackQueryHandler(on_button))
    app.job_queue.run_daily(send_briefing, time=dt.time(hour=BRIEF_HOUR, minute=0))

    log.info("봇 시작 (롱폴링, 매일 %02d:00 브리핑)", BRIEF_HOUR)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
