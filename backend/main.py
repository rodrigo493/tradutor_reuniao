import os
import asyncio
import asyncpg
from typing import Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from starlette.middleware.sessions import SessionMiddleware
from backend.database import connect_pool, close_pool, get_pool, init_db, get_db
from backend.routers.auth_router import router as auth_router
from backend.auth import decode_token
from backend.session import RecordingSession
from backend.devices import list_devices, find_vbcable
from backend.storage import get_save_folder, save_transcript_txt, save_pdf, generate_summary
from openai import OpenAI

active_sessions: Dict[int, RecordingSession] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_pool()
    async with get_pool().acquire() as conn:
        await init_db(conn)
    yield
    await close_pool()

app = FastAPI(title="Live Translator", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev-secret"))
app.include_router(auth_router)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")

@app.get("/devices")
async def devices():
    data = list_devices()
    return {
        "inputs": data["inputs"],
        "outputs": data["outputs"],
        "vbcable": find_vbcable(data["outputs"]),
    }

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
                async with get_pool().acquire() as conn:
                    row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
                other_lang = data.get("other_language", row["other_language"] if row else "en")
                hp = data.get("headphone_index")
                vb = data.get("vbcable_index")
                if hp is None or vb is None:
                    await websocket.send_json({"type": "error", "message": "Selecione os dispositivos (fone e VB-Cable) antes de iniciar."})
                    continue
                try:
                    headphone_index = int(hp)
                    vbcable_index = int(vb)
                    mic_index = int(data["mic_index"]) if data.get("mic_index") is not None else None
                    loopback_index = int(data["loopback_index"]) if data.get("loopback_index") is not None else None
                except (TypeError, ValueError):
                    await websocket.send_json({"type": "error", "message": "Índices de dispositivo inválidos."})
                    continue
                session = RecordingSession(
                    user_id=user_id, other_lang=other_lang, websocket=websocket, loop=loop,
                    headphone_index=headphone_index, vbcable_index=vbcable_index,
                    mic_index=mic_index, loopback_index=loopback_index,
                )
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
async def end_meeting(token: str, db: asyncpg.Connection = Depends(get_db)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido")
    user_id = int(payload["sub"])

    if user_id not in active_sessions:
        raise HTTPException(status_code=400, detail="Nenhuma sessão ativa")

    session = active_sessions.pop(user_id)
    transcriptions = session.stop()

    row = await db.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    timestamp = session.started_at.strftime("%Y%m%d_%H%M")
    drive_folder = row["drive_folder"] or os.path.expanduser("~/Desktop/Reunioes")
    folder = get_save_folder(drive_folder, row["name"], timestamp)

    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    summary = generate_summary(transcriptions, openai_client)

    txt_path = save_transcript_txt(folder, transcriptions)
    pdf_path = save_pdf(folder, transcriptions, summary, session.started_at.strftime("%d/%m/%Y %H:%M"))

    await db.execute(
        "INSERT INTO conversations (user_id, started_at, ended_at, transcript_path, pdf_path, summary) "
        "VALUES ($1, $2, now(), $3, $4, $5)",
        user_id, session.started_at, txt_path, pdf_path, summary,
    )

    return {"folder": folder, "txt": txt_path, "pdf": pdf_path, "summary": summary}
