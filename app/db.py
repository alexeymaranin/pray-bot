import aiosqlite
from dataclasses import dataclass
from typing import Optional, List, Tuple
from collections import defaultdict


@dataclass
class User:
    user_id: int
    chat_id: int
    first_name: str
    last_name: str
    username: str
    is_active: int
    is_paused: int


class Database:
    def __init__(self, path: str):
        self.path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id       INTEGER PRIMARY KEY,
                    chat_id       INTEGER NOT NULL,
                    first_name    TEXT NOT NULL,
                    last_name     TEXT NOT NULL,
                    username      TEXT NOT NULL,
                    is_active     INTEGER NOT NULL DEFAULT 1,
                    is_paused     INTEGER NOT NULL DEFAULT 0,
                    registered_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                """
            )

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS assignments (
                    week_start TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    partner_user_id INTEGER NOT NULL,
                    PRIMARY KEY (week_start, user_id, partner_user_id)
                );
                """
            )

            # миграция на случай старой БД (если колонок нет)
            # await db.execute("ALTER TABLE users ADD COLUMN is_paused INTEGER NOT NULL DEFAULT 0;")  # может упасть
            await db.commit()

    async def _safe_exec(self, sql: str) -> None:
        # helper, чтобы не падать на ALTER TABLE при повторном запуске
        async with aiosqlite.connect(self.path) as db:
            try:
                await db.execute(sql)
                await db.commit()
            except Exception:
                pass

    async def ensure_migrations(self) -> None:
        await self._safe_exec("ALTER TABLE users ADD COLUMN is_paused INTEGER NOT NULL DEFAULT 0;")

    async def upsert_user(self, user_id: int, chat_id: int, first_name: str, last_name: str, username: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO users (user_id, chat_id, first_name, last_name, username, is_active, is_paused)
                VALUES (?, ?, ?, ?, ?, 1, 0)
                ON CONFLICT(user_id) DO UPDATE SET
                    chat_id=excluded.chat_id,
                    first_name=excluded.first_name,
                    last_name=excluded.last_name,
                    username=excluded.username,
                    is_active=1;
                """,
                (user_id, chat_id, first_name.strip(), last_name.strip(), username.strip()),
            )
            await db.commit()

    async def is_registered(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT 1 FROM users WHERE user_id=? AND is_active=1", (user_id,)) as cur:
                return await cur.fetchone() is not None

    async def set_paused(self, user_id: int, paused: bool) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("UPDATE users SET is_paused=? WHERE user_id=?", (1 if paused else 0, user_id))
            await db.commit()
            return cur.rowcount > 0

    async def set_active(self, user_id: int, active: bool) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("UPDATE users SET is_active=? WHERE user_id=?", (1 if active else 0, user_id))
            await db.commit()
            return cur.rowcount > 0

    async def get_active_users(self) -> List[User]:
        # участвуют только активные и НЕ на паузе
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """
                SELECT user_id, chat_id, first_name, last_name, username, is_active, is_paused
                FROM users
                WHERE is_active=1 AND is_paused=0
                """
            ) as cur:
                rows = await cur.fetchall()
        return [User(*r) for r in rows]

    async def list_users(self) -> List[User]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """
                SELECT user_id, chat_id, first_name, last_name, username, is_active, is_paused
                FROM users
                ORDER BY registered_at ASC
                """
            ) as cur:
                rows = await cur.fetchall()
        return [User(*r) for r in rows]

    async def get_last_week_partners(self, user_id: int, last_week_start: str) -> set[int]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                    "SELECT partner_user_id FROM assignments WHERE week_start=? AND user_id=?",
                    (last_week_start, user_id),
            ) as cur:
                rows = await cur.fetchall()
        return {r[0] for r in rows}

    async def save_assignments(self, week_start: str, pairs: List[tuple[int, int]]) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM assignments WHERE week_start=?", (week_start,))
            for u, p in pairs:
                await db.execute(
                    "INSERT INTO assignments (week_start, user_id, partner_user_id) VALUES (?, ?, ?)",
                    (week_start, u, p),
                )
            await db.commit()

    async def get_user(self, user_id: int) -> Optional[User]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """
                SELECT user_id, chat_id, first_name, last_name, username, is_active, is_paused
                FROM users
                WHERE user_id=?
                """,
                (user_id,),
            ) as cur:
                row = await cur.fetchone()
        return User(*row) if row else None

    async def update_name(self, user_id: int, first_name: str, last_name: str) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "UPDATE users SET first_name=?, last_name=? WHERE user_id=?",
                (first_name.strip(), last_name.strip(), user_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def get_assignments_for_week(self, week_start: str) -> dict[int, set[int]]:
        """
        Возвращает словарь:
        {
            user_id: {partner_user_id1, partner_user_id2}
        }
        """
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                    "SELECT user_id, partner_user_id FROM assignments WHERE week_start=?",
                    (week_start,),
            ) as cur:
                rows = await cur.fetchall()

        result = defaultdict(set)
        for user_id, partner_id in rows:
            result[user_id].add(partner_id)

        return dict(result)
