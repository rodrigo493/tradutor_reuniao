import os
from typing import AsyncGenerator, Optional
import asyncpg

_pool: Optional[asyncpg.Pool] = None


async def connect_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.environ["SUPABASE_DB_URL"],
            ssl="require",
            min_size=1,
            max_size=5,
            statement_cache_size=0,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool não inicializado")
    return _pool


async def init_db(conn: asyncpg.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name           TEXT NOT NULL,
            email          TEXT UNIQUE NOT NULL,
            password_hash  TEXT,
            google_id      TEXT,
            my_language    TEXT DEFAULT 'pt',
            other_language TEXT DEFAULT 'en',
            drive_folder   TEXT NOT NULL DEFAULT '',
            created_at     TIMESTAMPTZ DEFAULT now()
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id         BIGINT REFERENCES users(id),
            started_at      TIMESTAMPTZ NOT NULL,
            ended_at        TIMESTAMPTZ,
            audio_path      TEXT,
            transcript_path TEXT,
            pdf_path        TEXT,
            summary         TEXT
        )
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversations_user_id "
        "ON conversations(user_id)"
    )


async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    async with get_pool().acquire() as conn:
        yield conn
