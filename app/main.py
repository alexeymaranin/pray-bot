import os
import logging
import io
import csv
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.admin_handlers import admin_users, admin_export, admin_deactivate, admin_activate, admin_run_now, \
    admin_next_run, admin_pairs
from app.client_handlers import start, pause, resume, conversation_handler, rename_conversation_handler, rename_entry
from app.db import Database
from app.keyboards import BTN_PAUSE, BTN_RESUME, BTN_RENAME, BTN_ADMIN_USERS, BTN_ADMIN_EXPORT, BTN_ADMIN_RUN_NOW, \
    BTN_ADMIN_PAIRS
from app.scheduler import run_weekly_pairing
from app.texts import (
    WELCOME_TEXT,
    REG_SUCCESS_TEMPLATE,
    ASK_FIRST_NAME,
    ASK_LAST_NAME,
    NO_USERNAME_TEXT,
    ALREADY_REGISTERED,
    CANCELLED, PAUSED, RESUMED, ADMIN_ONLY, UNKNOWN_USER, UPDATED_OK, RUN_OK
)
from app.utils import parse_admin_ids

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),  # 👈 лог в консоль
    ]
)

load_dotenv()


async def on_startup(app: Application) -> None:
    db: Database = app.bot_data["db"]
    tz_name: str = app.bot_data["tz_name"]
    await db.init()

    scheduler = build_scheduler(app, db, tz_name)
    scheduler.start()
    app.bot_data["scheduler"] = scheduler

    # Быстрый лог, что scheduler реально жив
    print(f"[scheduler] started, tz={tz_name}")


def build_scheduler(app: Application, db: Database, tz_name: str) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=ZoneInfo(tz_name))

    trigger = CronTrigger(day_of_week="sat", hour=21, minute=0, timezone=ZoneInfo(tz_name))
    # trigger = CronTrigger(second="*/30", timezone=ZoneInfo(tz_name))
    scheduler.add_job(
        run_weekly_pairing,
        trigger=trigger,
        id="weekly_pairing",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        args=[app, db, tz_name],
    )
    return scheduler


def main() -> None:
    logging.warning("*** Starting Bot ***")
    token = os.environ["BOT_TOKEN"]
    db_path = os.environ.get("DB_PATH", "/data/bot.sqlite3")
    tz_name = os.environ.get("TZ", "Europe/Moscow")

    db = Database(db_path)

    admin_ids = parse_admin_ids(os.environ.get("ADMIN_IDS", ""))

    app = Application.builder().token(token).post_init(on_startup).build()
    app.bot_data["db"] = db
    app.bot_data["tz_name"] = tz_name
    app.bot_data["admin_ids"] = admin_ids

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))

    app.add_handler(CommandHandler("users", admin_users))
    app.add_handler(CommandHandler("export", admin_export))
    app.add_handler(CommandHandler("deactivate", admin_deactivate))
    app.add_handler(CommandHandler("activate", admin_activate))
    app.add_handler(CommandHandler("run_now", admin_run_now))
    app.add_handler(CommandHandler("next_run", admin_next_run))

    conv = conversation_handler()
    app.add_handler(conv)

    rename_conv = rename_conversation_handler()
    app.add_handler(rename_conv)

    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_PAUSE}$"), pause))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_RESUME}$"), resume))
    # app.add_handler(MessageHandler(filters.Regex(f"^{BTN_RENAME}$"), rename_entry))

    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_ADMIN_USERS}$"), admin_users))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_ADMIN_PAIRS}$"), admin_pairs))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_ADMIN_EXPORT}$"), admin_export))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_ADMIN_RUN_NOW}$"), admin_run_now))

    # scheduler = build_scheduler(app, db, tz_name)
    # scheduler.start()

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
