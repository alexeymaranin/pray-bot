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


def monday_iso(dt: datetime) -> str:
    monday = (dt - timedelta(days=dt.weekday())).date()
    return monday.isoformat()


def current_and_previous_week_starts(tz_name: str) -> tuple[str, str]:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz=tz)
    current = monday_iso(now)
    prev = (datetime.fromisoformat(current) - timedelta(days=7)).date().isoformat()
    return current, prev


def chunk_text(text: str, limit: int = 3900) -> list[str]:
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    parts.append(text)
    return parts


def _fmt_username(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return "—"
    if not u.startswith("@"):
        u = "@" + u.lstrip("@")
    return u


def _user_label(u) -> str:
    full = f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip()
    if not full:
        full = "—"
    return f"{full} ({_fmt_username(u.username)})"


def build_pairs_text(title: str, week_start: str, assignments: dict[int, set[int]], user_map: dict[int, object]) -> str:
    lines = []
    lines.append(f"{title}")
    lines.append(f"Неделя: {week_start}")

    if not assignments:
        lines.append("Пары ещё не сформированы.")
        return "\n".join(lines) + "\n"

    visited: set[int] = set()
    pairs: list[tuple[int, int]] = []
    triplets: list[set[int]] = []

    for user_id, partners in assignments.items():
        if user_id in visited:
            continue

        if len(partners) == 1:
            partner_id = next(iter(partners))
            if partner_id in visited:
                continue
            pairs.append((user_id, partner_id))
            visited.update({user_id, partner_id})

        elif len(partners) == 2:
            group = {user_id, *partners}
            if group & visited:
                continue
            triplets.append(group)
            visited |= group

    if pairs:
        lines.append("")
        lines.append("Пары:")
        for a, b in pairs:
            ua, ub = user_map.get(a), user_map.get(b)
            if ua and ub:
                lines.append(f" - {_user_label(ua)}  <->  {_user_label(ub)}")

    if triplets:
        lines.append("")
        lines.append("Тройки:")
        for group in triplets:
            members = [user_map.get(uid) for uid in group]
            members = [m for m in members if m is not None]
            if members:
                lines.append(" - " + "  <->  ".join(_user_label(m) for m in members))

    lines.append("")
    lines.append(f"Итого: пар={len(pairs)}, троек={len(triplets)}")
    return "\n".join(lines) + "\n"
