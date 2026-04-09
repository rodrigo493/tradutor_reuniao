import aiosqlite
from typing import AsyncGenerator

DATABASE_URL = "db.sqlite3"

async def init_db(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT NOT NULL,
            email          TEXT UNIQUE NOT NULL,
            password_hash  TEXT,
            google_id      TEXT,
            my_language    TEXT DEFAULT 'pt',
            other_language TEXT DEFAULT 'en',
            drive_folder   TEXT NOT NULL DEFAULT '',
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS meetings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER REFERENCES users(id),
            started_at      DATETIME NOT NULL,
            ended_at        DATETIME,
            audio_path      TEXT,
            transcript_path TEXT,
            pdf_path        TEXT,
            summary         TEXT
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_meetings_user_id ON meetings(user_id)"
    )
    await db.commit()

async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        yield db
