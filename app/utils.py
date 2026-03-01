from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo
from telegram.ext import Application


def parse_admin_ids(raw: str) -> set[int]:
    raw = (raw or "").strip()
    if not raw:
        return set()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    out = set()
    for p in parts:
        try:
            out.add(int(p))
        except ValueError:
            pass
    return out


def is_admin(app: Application, user_id: int) -> bool:
    return user_id in app.bot_data.get("admin_ids", set())


def normalize_username(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    if not s.startswith("@"):
        s = "@" + s.lstrip("@")
    return s


def next_saturday_21(tz_name: str) -> datetime:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz=tz)

    # найдём ближайшую субботу
    days_ahead = (5 - now.weekday()) % 7  # Mon=0 ... Sat=5
    candidate_date = (now + timedelta(days=days_ahead)).date()
    candidate_dt = datetime.combine(candidate_date, dtime(21, 0), tzinfo=tz)

    # если сегодня суббота, но уже после/в 21:00 — берём следующую
    if candidate_dt <= now:
        candidate_dt = candidate_dt + timedelta(days=7)
    return candidate_dt


def current_week_start(tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz=tz)
    monday = (now - timedelta(days=now.weekday())).date()
    return monday.isoformat()
