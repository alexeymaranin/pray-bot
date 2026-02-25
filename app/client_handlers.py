import logging
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from app.db import Database
from app.keyboards import keyboard_for, BTN_REGISTER, BTN_RENAME

from app.texts import (
    WELCOME_TEXT,
    REG_SUCCESS_TEMPLATE,
    ASK_FIRST_NAME,
    ASK_LAST_NAME,
    NO_USERNAME_TEXT,
    ALREADY_REGISTERED,
    CANCELLED, PAUSED, RESUMED, RENAME_START, RENAME_ASK_LAST, RENAME_DONE, RENAME_NOT_REGISTERED
)
from app.utils import normalize_username, next_saturday_21
from telegram import ReplyKeyboardRemove


REGISTER_FIRST, REGISTER_LAST, REGISTER_USERNAME = range(3)
RENAME_FIRST, RENAME_LAST = range(100, 102)


# def register_keyboard() -> ReplyKeyboardMarkup:
#     return ReplyKeyboardMarkup(
#         [[KeyboardButton(BTN_REGISTER)]],
#         resize_keyboard=True,
#         one_time_keyboard=True,
#     )


def conversation_handler() -> ConversationHandler:
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{BTN_REGISTER}$"), register_entry)],
        states={
            REGISTER_FIRST: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_first)],
            REGISTER_LAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_last)],
            REGISTER_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_username)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    return conv


def rename_conversation_handler() -> ConversationHandler:
    rename_conv = ConversationHandler(
        entry_points=[CommandHandler("rename", rename_entry),
                      MessageHandler(filters.Regex(f"^{BTN_RENAME}$"), rename_entry)],
        states={
            RENAME_FIRST: [MessageHandler(filters.TEXT & ~filters.COMMAND, rename_first)],
            RENAME_LAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, rename_last)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    return rename_conv


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    kb = await keyboard_for(update, context)
    await update.message.reply_text(WELCOME_TEXT, reply_markup=kb)


async def register_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db: Database = context.application.bot_data["db"]
    user = update.effective_user
    logging.warning(f"{user.id}")

    if await db.is_registered(user.id):
        kb = await keyboard_for(update, context)
        await update.message.reply_text(ALREADY_REGISTERED, reply_markup=kb)
        return ConversationHandler.END

    await update.message.reply_text(ASK_FIRST_NAME)
    return REGISTER_FIRST


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    ok = await db.set_paused(update.effective_user.id, True)
    kb = await keyboard_for(update, context)
    if ok:
        await update.message.reply_text(PAUSED, reply_markup=kb)
    else:
        await update.message.reply_text("Сначала зарегистрируйся 🙂", reply_markup=kb)


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    ok = await db.set_paused(update.effective_user.id, False)
    kb = await keyboard_for(update, context)
    if ok:
        await update.message.reply_text(RESUMED, reply_markup=kb)
    else:
        await update.message.reply_text("Сначала зарегистрируйся 🙂", reply_markup=kb)


async def reg_first(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["first_name"] = update.message.text.strip()
    await update.message.reply_text(ASK_LAST_NAME)
    return REGISTER_LAST


async def reg_last(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["last_name"] = update.message.text.strip()

    tg_username = update.effective_user.username
    if tg_username:
        context.user_data["username"] = normalize_username(tg_username)
        return await finish_registration(update, context)

    await update.message.reply_text(NO_USERNAME_TEXT)
    return REGISTER_USERNAME


async def reg_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    username = normalize_username(update.message.text)
    if not username.startswith("@") or len(username) < 2:
        await update.message.reply_text("Нужно прислать username в формате @username")
        return REGISTER_USERNAME

    context.user_data["username"] = username
    return await finish_registration(update, context)


async def finish_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db: Database = context.application.bot_data["db"]
    tz_name: str = context.application.bot_data["tz_name"]

    user = update.effective_user
    chat_id = update.effective_chat.id

    first_name = context.user_data["first_name"]
    last_name = context.user_data["last_name"]
    username = context.user_data["username"]

    await db.upsert_user(
        user_id=user.id,
        chat_id=chat_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
    )

    dt = next_saturday_21(tz_name)
    next_saturday_str = dt.strftime("%d.%m.%Y")

    kb = await keyboard_for(update, context)
    await update.message.reply_text(
        REG_SUCCESS_TEMPLATE.format(first_name=first_name, next_saturday=next_saturday_str),
        reply_markup=kb,
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = await keyboard_for(update, context)
    await update.message.reply_text(CANCELLED, reply_markup=kb)
    return ConversationHandler.END


async def rename_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db: Database = context.application.bot_data["db"]
    user_id = update.effective_user.id

    if not await db.is_registered(user_id):
        kb = await keyboard_for(update, context)
        await update.message.reply_text(RENAME_NOT_REGISTERED, reply_markup=kb)
        return ConversationHandler.END

    await update.message.reply_text(RENAME_START)
    return RENAME_FIRST


async def rename_first(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["rename_first_name"] = update.message.text.strip()
    await update.message.reply_text(RENAME_ASK_LAST)
    return RENAME_LAST


async def rename_last(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db: Database = context.application.bot_data["db"]
    user_id = update.effective_user.id

    first_name = context.user_data.get("rename_first_name", "").strip()
    last_name = update.message.text.strip()

    kb = await keyboard_for(update, context)

    ok = await db.update_name(user_id=user_id, first_name=first_name, last_name=last_name)
    if not ok:
        await update.message.reply_text(RENAME_NOT_REGISTERED, reply_markup=kb)
        return ConversationHandler.END

    await update.message.reply_text(
        RENAME_DONE.format(first_name=first_name, last_name=last_name),
        reply_markup=kb,
    )
    return ConversationHandler.END
