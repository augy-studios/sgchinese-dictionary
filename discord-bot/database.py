import aiosqlite
import config


async def init_db() -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                user_id    INTEGER PRIMARY KEY,
                query      TEXT    NOT NULL DEFAULT '',
                sort       TEXT    NOT NULL DEFAULT 'hypy_asc',
                page       INTEGER NOT NULL DEFAULT 0,
                total      INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS persistent_messages (
                message_id  INTEGER PRIMARY KEY,
                channel_id  INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                query       TEXT    NOT NULL DEFAULT '',
                sort        TEXT    NOT NULL DEFAULT 'hypy_asc',
                page        INTEGER NOT NULL DEFAULT 0,
                total       INTEGER NOT NULL DEFAULT 0,
                updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.commit()


async def get_session(user_id: int) -> dict:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT query, sort, page, total FROM user_sessions WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
            return {"query": "", "sort": "hypy_asc", "page": 0, "total": 0}


async def save_session(user_id: int, **kwargs) -> None:
    if not kwargs:
        return
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = [*kwargs.values(), user_id]
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_sessions (user_id) VALUES (?)", (user_id,)
        )
        await db.execute(
            f"UPDATE user_sessions SET {set_clause}, updated_at = datetime('now') WHERE user_id = ?",
            values,
        )
        await db.commit()


async def save_persistent_message(
    message_id: int,
    channel_id: int,
    user_id: int,
    query: str,
    sort: str,
    page: int,
    total: int,
) -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO persistent_messages
                (message_id, channel_id, user_id, query, sort, page, total, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (message_id, channel_id, user_id, query, sort, page, total),
        )
        await db.commit()


async def update_persistent_message(message_id: int, **kwargs) -> None:
    if not kwargs:
        return
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = [*kwargs.values(), message_id]
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            f"UPDATE persistent_messages SET {set_clause}, updated_at = datetime('now') WHERE message_id = ?",
            values,
        )
        await db.commit()


async def get_all_persistent_messages() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT message_id, channel_id, user_id, query, sort, page, total FROM persistent_messages"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def delete_persistent_message(message_id: int) -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "DELETE FROM persistent_messages WHERE message_id = ?", (message_id,)
        )
        await db.commit()
