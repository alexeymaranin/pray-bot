import os
import logging
import io
import csv

from telegram import Update
from telegram.ext import (
    ContextTypes,
)

from app.db import Database
from app.scheduler import run_weekly_pairing
from app.texts import ADMIN_ONLY, UNKNOWN_USER, UPDATED_OK, RUN_OK
from app.utils import is_admin


def _status_badge(is_active: int, is_paused: int) -> str:
    if not is_active:
        return "⛔️"
    if is_paused:
        return "⏸"
    return "✅"


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(context.application, update.effective_user.id):
        await update.message.reply_text(ADMIN_ONLY)
        return

    db: Database = context.application.bot_data["db"]
    users = await db.list_users()

    total = len(users)
    active = sum(1 for u in users if u.is_active == 1 and u.is_paused == 0)
    paused = sum(1 for u in users if u.is_active == 1 and u.is_paused == 1)
    inactive = sum(1 for u in users if u.is_active == 0)

    # Заголовок-сводка
    header = (
        "👥 *Участники*\n"
        f"Всего: *{total}* \n ✅ активных: *{active}* \n ⏸ на паузе: *{paused}* \n ⛔️ выключено: *{inactive}*\n"
    )

    lines = []
    for u in users:
        flags = []
        flags.append(_status_badge(u.is_active, u.is_paused))
        uname = u.username if u.username.startswith("@") else f"@{u.username}"
        lines.append(f"{u.user_id} | {u.first_name} {u.last_name} | {uname} | {', '.join(flags)}")

    text = header + "\n" + ("\n-----------------\n".join(lines) if lines else "пусто")
    await update.message.reply_text(text)


async def admin_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(context.application, update.effective_user.id):
        await update.message.reply_text(ADMIN_ONLY)
        return

    db: Database = context.application.bot_data["db"]
    users = await db.list_users()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["user_id", "chat_id", "first_name", "last_name", "username", "is_active", "is_paused"])
    for u in users:
        w.writerow([u.user_id, u.chat_id, u.first_name, u.last_name, u.username, u.is_active, u.is_paused])

    data = buf.getvalue().encode("utf-8")
    await update.message.reply_document(
        document=io.BytesIO(data),
        filename="users.csv",
        caption="Экспорт участников",
    )


async def admin_deactivate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(context.application, update.effective_user.id):
        await update.message.reply_text(ADMIN_ONLY)
        return

    if not context.args:
        await update.message.reply_text("Использование: /deactivate <user_id>")
        return

    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("user_id должен быть числом")
        return

    db: Database = context.application.bot_data["db"]
    ok = await db.set_active(uid, False)
    await update.message.reply_text(UPDATED_OK if ok else UNKNOWN_USER)


async def admin_activate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(context.application, update.effective_user.id):
        await update.message.reply_text(ADMIN_ONLY)
        return

    if not context.args:
        await update.message.reply_text("Использование: /activate <user_id>")
        return

    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("user_id должен быть числом")
        return

    db: Database = context.application.bot_data["db"]
    ok = await db.set_active(uid, True)
    await update.message.reply_text(UPDATED_OK if ok else UNKNOWN_USER)


async def admin_run_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(context.application, update.effective_user.id):
        await update.message.reply_text(ADMIN_ONLY)
        return

    db: Database = context.application.bot_data["db"]
    tz_name: str = context.application.bot_data["tz_name"]
    await run_weekly_pairing(context.application, db, tz_name)
    await update.message.reply_text(RUN_OK)


async def admin_next_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(context.application, update.effective_user.id):
        await update.message.reply_text(ADMIN_ONLY)
        return

    scheduler = context.application.bot_data.get("scheduler")
    if not scheduler:
        await update.message.reply_text("scheduler: ❌ not initialized")
        return

    job = scheduler.get_job("weekly_pairing")
    if not job:
        await update.message.reply_text("job weekly_pairing: ❌ not found")
        return

    await update.message.reply_text(f"scheduler: ✅ running\nnext_run_time: {job.next_run_time}")
