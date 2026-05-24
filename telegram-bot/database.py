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
