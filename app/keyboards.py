from telegram import ReplyKeyboardRemove
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from app.db import Database
from telegram.ext import ContextTypes

from app.utils import is_admin

BTN_REGISTER = "Зарегистрироваться"
BTN_PAUSE = "⏸ Пауза"
BTN_RESUME = "▶️ Продолжить"
BTN_RENAME = "✏️ Переименовать"

BTN_ADMIN_USERS = "👥 Участники"
BTN_ADMIN_EXPORT = "📤 Экспорт"
BTN_ADMIN_RUN_NOW = "🚀 Рассылка сейчас"
BTN_ADMIN_PAIRS = "📅 Текущие пары"


def admin_keyboard(is_paused: bool) -> ReplyKeyboardMarkup:
    base = [
        [KeyboardButton(BTN_RESUME if is_paused else BTN_PAUSE)],
        [KeyboardButton(BTN_RENAME)],
        [KeyboardButton(BTN_ADMIN_USERS), KeyboardButton(BTN_ADMIN_EXPORT)],
        [KeyboardButton(BTN_ADMIN_PAIRS)],
        [KeyboardButton(BTN_ADMIN_RUN_NOW)],
    ]
    return ReplyKeyboardMarkup(base, resize_keyboard=True)


def guest_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_REGISTER)]],
        resize_keyboard=True,
        one_time_keyboard=True,   # прячет клавиатуру после нажатия (клиент-зависимо)
    )


def user_keyboard(is_paused: bool) -> ReplyKeyboardMarkup:
    row1 = [KeyboardButton(BTN_RESUME if is_paused else BTN_PAUSE)]
    row2 = [KeyboardButton(BTN_RENAME)]
    return ReplyKeyboardMarkup([row1, row2], resize_keyboard=True)


async def keyboard_for(update: Update, context: ContextTypes.DEFAULT_TYPE) -> ReplyKeyboardMarkup:
    db: Database = context.application.bot_data["db"]
    user_id = update.effective_user.id

    registered = await db.is_registered(user_id)
    if not registered:
        return guest_keyboard()

    u = await db.get_user(user_id)  # у тебя уже есть get_user
    paused = bool(u.is_paused) if u else False

    if is_admin(context.application, user_id):
        return admin_keyboard(paused)
    return user_keyboard(paused)
