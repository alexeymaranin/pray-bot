import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Tuple, Optional

from telegram.ext import Application

from app.db import Database, User
from app.texts import PARTNER_TEMPLATE


ODD_TRIPLET_TEMPLATE = (
    "Привет, {first_name}!\n\n"
    "На этой неделе вы молитесь втроём 🙏\n\n"
    "Твои партнёры:\n"
    "{partners}\n\n"
    "Что теперь?\n"
    "Самое время познакомиться! Напиши привет, расскажи немного о себе и спроси, "
    "как вы можете поддержать друг друга в молитве на этой неделе.\n\n"
    "Пусть эта неделя будет наполнена поддержкой и силой общей молитвы🙏"
)


def week_start_for(dt: datetime) -> str:
    monday = (dt - timedelta(days=dt.weekday())).date()
    return monday.isoformat()


async def run_weekly_pairing(app: Application, db: Database, tz_name: str) -> None:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz=tz)
    this_week = week_start_for(now)
    last_week = week_start_for(now - timedelta(days=7))

    users = await db.get_active_users()
    if len(users) < 2:
        return

    pool = users[:]
    random.shuffle(pool)

    # Подготовим lookup: прошлые партнёры для каждого (могут быть 1 или 2)
    last_partners_map = {}
    for u in pool:
        last_partners_map[u.user_id] = await db.get_last_week_partners(u.user_id, last_week)

    # Простая эвристика "снизить повторы" (для пар; для троек повторы менее критичны)
    for _ in range(2):
        for i in range(0, len(pool) - 1, 2):
            u1, u2 = pool[i], pool[i + 1]
            if u2.user_id in last_partners_map.get(u1.user_id, set()) or u1.user_id in last_partners_map.get(u2.user_id, set()):
                if i + 2 < len(pool):
                    pool[i + 1], pool[i + 2] = pool[i + 2], pool[i + 1]

    triplet: Optional[List[User]] = None
    pairs: List[Tuple[User, User]] = []

    if len(pool) % 2 == 1:
        # берём последних 3 в тройку (если всего 3 — будет только тройка)
        if len(pool) >= 3:
            triplet = pool[-3:]
            pool = pool[:-3]
        else:
            # теоретически сюда не попадём, т.к. len(users) >= 2 и odd => минимум 3
            triplet = pool
            pool = []

    for i in range(0, len(pool), 2):
        pairs.append((pool[i], pool[i + 1]))

    # Сохраняем assignments:
    # - для пары: u<->p (2 строки)
    # - для тройки: каждый с каждым (по 2 партнёра на пользователя, итого 6 строк)
    to_save: List[Tuple[int, int]] = []

    for a, b in pairs:
        to_save.append((a.user_id, b.user_id))
        to_save.append((b.user_id, a.user_id))

    if triplet:
        a, b, c = triplet
        # a
        to_save.append((a.user_id, b.user_id))
        to_save.append((a.user_id, c.user_id))
        # b
        to_save.append((b.user_id, a.user_id))
        to_save.append((b.user_id, c.user_id))
        # c
        to_save.append((c.user_id, a.user_id))
        to_save.append((c.user_id, b.user_id))

    await db.save_assignments(this_week, to_save)

    # Рассылка по парам
    for u1, u2 in pairs:
        await send_partner(app, u1, u2)
        await send_partner(app, u2, u1)

    # Рассылка по тройке
    if triplet:
        await send_triplet(app, triplet)


async def send_partner(app: Application, user: User, partner: User) -> None:
    partner_username = partner.username if partner.username.startswith("@") else f"@{partner.username}"
    text = PARTNER_TEMPLATE.format(
        first_name=user.first_name,
        partner_username=partner_username,
        partner_full_name=f"{partner.first_name} {partner.last_name}",
    )
    await app.bot.send_message(chat_id=user.chat_id, text=text)


async def send_triplet(app: Application, users: List[User]) -> None:
    for u in users:
        others = [x for x in users if x.user_id != u.user_id]
        lines = []
        for o in others:
            uname = o.username if o.username.startswith("@") else f"@{o.username}"
            lines.append(f"• {o.first_name} {o.last_name} — {uname}")

        text = ODD_TRIPLET_TEMPLATE.format(
            first_name=u.first_name,
            partners="\n".join(lines),
        )
        await app.bot.send_message(chat_id=u.chat_id, text=text)