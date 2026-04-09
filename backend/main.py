import os
import aiosqlite
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from backend.database import init_db, DATABASE_URL
from backend.routers.auth_router import router as auth_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with aiosqlite.connect(DATABASE_URL) as db:
        await init_db(db)
    yield

app = FastAPI(title="Live Translator", lifespan=lifespan)
app.include_router(auth_router)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")
