import os
import asyncio
import aiosqlite
from typing import Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from starlette.middleware.sessions import SessionMiddleware
from backend.database import init_db, DATABASE_URL, get_db
from backend.routers.auth_router import router as auth_router
from backend.auth import decode_token
from backend.session import RecordingSession
from backend.storage import get_save_folder, save_transcript_txt, save_pdf, generate_summary
from openai import OpenAI

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
    print(f"[WS] Nova conexão recebida")
    payload = decode_token(token)
    if not payload:
        print("[WS] Token inválido, fechando")
        await websocket.close(code=4001)
        return
    user_id = int(payload["sub"])
    print(f"[WS] user_id={user_id} conectado")
    loop = asyncio.get_running_loop()
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            print(f"[WS] Mensagem recebida: {data}")
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

@app.post("/meetings/end")
async def end_meeting(token: str, db: aiosqlite.Connection = Depends(get_db)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido")
    user_id = int(payload["sub"])

    if user_id not in active_sessions:
        raise HTTPException(status_code=400, detail="Nenhuma sessão ativa")

    session = active_sessions.pop(user_id)
    transcriptions = session.stop()

    cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = await cursor.fetchone()

    timestamp = session.started_at.strftime("%Y%m%d_%H%M")
    drive_folder = row["drive_folder"] or os.path.expanduser("~/Desktop/Reunioes")
    folder = get_save_folder(drive_folder, row["name"], timestamp)

    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    summary = generate_summary(transcriptions, openai_client)

    txt_path = save_transcript_txt(folder, transcriptions)
    pdf_path = save_pdf(folder, transcriptions, summary, session.started_at.strftime("%d/%m/%Y %H:%M"))

    await db.execute(
        "INSERT INTO meetings (user_id, started_at, ended_at, transcript_path, pdf_path, summary) "
        "VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?, ?)",
        (user_id, session.started_at.isoformat(), txt_path, pdf_path, summary)
    )
    await db.commit()

    return {"folder": folder, "txt": txt_path, "pdf": pdf_path, "summary": summary}
