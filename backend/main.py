import os
import asyncio
import aiosqlite
from typing import Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from starlette.middleware.sessions import SessionMiddleware
from backend.database import init_db, DATABASE_URL
from backend.routers.auth_router import router as auth_router
from backend.auth import decode_token
from backend.session import RecordingSession

active_sessions: Dict[int, RecordingSession] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with aiosqlite.connect(DATABASE_URL) as db:
        await init_db(db)
    yield

app = FastAPI(title="Live Translator", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev-secret"))
app.include_router(auth_router)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str):
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4001)
        return
    user_id = int(payload["sub"])
    loop = asyncio.get_event_loop()
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("action") == "start":
                async with aiosqlite.connect(DATABASE_URL) as db:
                    db.row_factory = aiosqlite.Row
                    cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                    row = await cursor.fetchone()
                my_lang = data.get("my_language", row["my_language"] if row else "pt")
                other_lang = data.get("other_language", row["other_language"] if row else "en")
                session = RecordingSession(user_id, my_lang, other_lang, websocket, loop)
                session.start()
                active_sessions[user_id] = session
                await websocket.send_json({"type": "status", "status": "recording"})
            elif data.get("action") == "stop":
                if user_id in active_sessions:
                    session = active_sessions.pop(user_id)
                    transcriptions = session.stop()
                    await websocket.send_json({"type": "stopped", "transcriptions": transcriptions})
    except WebSocketDisconnect:
        if user_id in active_sessions:
            active_sessions.pop(user_id).stop()
