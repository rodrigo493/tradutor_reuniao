import os
import pytest
import asyncpg
from dotenv import load_dotenv
from backend.database import connect_pool, close_pool, init_db

load_dotenv()
pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_DB_URL"), reason="SUPABASE_DB_URL não configurada"
)


@pytest.mark.asyncio
async def test_init_db_creates_tables():
    pool = await connect_pool()
    try:
        async with pool.acquire() as conn:
            await init_db(conn)
            rows = await conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            tables = {r["table_name"] for r in rows}
            assert "users" in tables
            assert "conversations" in tables
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_init_db_is_idempotent():
    pool = await connect_pool()
    try:
        async with pool.acquire() as conn:
            await init_db(conn)
            await init_db(conn)  # segunda vez não deve falhar
    finally:
        await close_pool()
