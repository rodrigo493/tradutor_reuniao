import pytest
import asyncio
import aiosqlite
from backend.database import init_db, get_db

@pytest.mark.asyncio
async def test_init_db_creates_tables():
    async with aiosqlite.connect(":memory:") as db:
        await init_db(db)
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in await cursor.fetchall()}
        assert "users" in tables
        assert "meetings" in tables
