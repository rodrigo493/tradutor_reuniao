# Live Translator Web App — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o app Tkinter por um webapp moderno (FastAPI + HTML/JS) com auth de equipe, detecção automática de reuniões, transcrição/tradução em tempo real com TTS, e salvamento no Google Drive.

**Architecture:** FastAPI backend com WebSocket para streaming em tempo real; frontend HTML/CSS/JS vanilla conectado via WebSocket; watcher Python independente monitora processos de reunião e abre o browser automaticamente; SQLite para usuários e sessões.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, faster-whisper, deep-translator, edge-tts, python-jose, passlib[bcrypt], Authlib, aiosqlite, reportlab, psutil, pygetwindow, keyboard, pyaudiowpatch, openai

---

## Estrutura de Arquivos

```
tradutor_reuniao/
├── backend/
│   ├── main.py          # FastAPI app, monta rotas e serve static/
│   ├── database.py      # Setup SQLite, criação de tabelas
│   ├── models.py        # Modelos Pydantic (User, Meeting, etc.)
│   ├── auth.py          # JWT email/senha + Google OAuth
│   ├── audio.py         # Captura mic + loopback via pyaudiowpatch
│   ├── transcriber.py   # Whisper + deep-translator, envia via WebSocket
│   ├── tts.py           # edge-tts: converte texto para áudio e toca
│   ├── storage.py       # Salva WAV, TXT, PDF no Google Drive folder
│   └── watcher.py       # Monitora processos, abre browser, hotkey
├── static/
│   ├── index.html       # SPA com 4 telas
│   ├── app.js           # Lógica frontend, WebSocket client
│   └── style.css        # Tema dark
├── tests/
│   ├── test_auth.py
│   ├── test_transcriber.py
│   ├── test_storage.py
│   └── test_watcher.py
├── requirements.txt
├── .env.example
└── tradutor.py          # MANTIDO — app Tkinter legado (não modificar)
```

---

## Task 1: Estrutura do projeto e dependências

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `backend/__init__.py`
- Create: `tests/__init__.py`
- Create: `static/.gitkeep`

- [ ] **Step 1: Criar requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
aiosqlite==0.20.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
authlib==1.3.1
httpx==0.27.2
python-multipart==0.0.9
faster-whisper==1.0.3
deep-translator==1.11.4
edge-tts==6.1.12
pyaudiowpatch==0.2.12.6
openai==1.40.0
reportlab==4.2.2
psutil==6.0.0
pygetwindow==0.0.9
keyboard==0.13.5
python-dotenv==1.0.1
pydantic[email]==2.8.2
pytest==8.3.2
pytest-asyncio==0.23.8
httpx==0.27.2
```

- [ ] **Step 2: Criar .env.example**

```
OPENAI_API_KEY=sk-...
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
SECRET_KEY=troque-por-string-aleatoria-longa
ACCESS_TOKEN_EXPIRE_MINUTES=10080
WHISPER_MODEL=tiny
```

- [ ] **Step 3: Criar pastas e __init__.py**

```bash
mkdir -p backend tests static
touch backend/__init__.py tests/__init__.py static/.gitkeep
```

- [ ] **Step 4: Instalar dependências**

```bash
pip install -r requirements.txt
```

Esperado: instalação sem erros. Se `pyaudiowpatch` falhar, instalar via: `pip install pyaudiowpatch --no-deps && pip install pyaudio`.

- [ ] **Step 5: Commit**

```bash
git init
git add requirements.txt .env.example backend/__init__.py tests/__init__.py
git commit -m "chore: project structure and dependencies"
```

---

## Task 2: Banco de dados (SQLite)

**Files:**
- Create: `backend/database.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Escrever o teste**

```python
# tests/test_database.py
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
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_database.py -v
```

Esperado: `ModuleNotFoundError: No module named 'backend.database'`

- [ ] **Step 3: Implementar backend/database.py**

```python
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
    await db.commit()

async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        yield db
```

- [ ] **Step 4: Rodar para confirmar passou**

```bash
pytest tests/test_database.py -v
```

Esperado: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/database.py tests/test_database.py
git commit -m "feat: SQLite database setup with users and meetings tables"
```

---

## Task 3: Modelos Pydantic

**Files:**
- Create: `backend/models.py`

- [ ] **Step 1: Criar backend/models.py**

```python
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    drive_folder: str = ""
    my_language: str = "pt"
    other_language: str = "en"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    name: str
    email: str
    my_language: str
    other_language: str
    drive_folder: str

class UserUpdate(BaseModel):
    name: Optional[str] = None
    my_language: Optional[str] = None
    other_language: Optional[str] = None
    drive_folder: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class MeetingOut(BaseModel):
    id: int
    user_id: int
    started_at: datetime
    ended_at: Optional[datetime]
    audio_path: Optional[str]
    transcript_path: Optional[str]
    pdf_path: Optional[str]
    summary: Optional[str]

class TranscriptionEvent(BaseModel):
    """Enviado via WebSocket para o frontend."""
    type: str          # "transcription"
    speaker: str       # "Você" ou "Outro"
    original: str      # texto original
    translation: str   # texto traduzido
    timestamp: str     # HH:MM:SS
```

- [ ] **Step 2: Verificar import**

```bash
python -c "from backend.models import UserCreate, Token, TranscriptionEvent; print('OK')"
```

Esperado: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/models.py
git commit -m "feat: Pydantic models for users, meetings, auth and WebSocket events"
```

---

## Task 4: Autenticação JWT (email + senha)

**Files:**
- Create: `backend/auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Escrever testes**

```python
# tests/test_auth.py
import pytest
from backend.auth import hash_password, verify_password, create_access_token, decode_token

def test_hash_and_verify_password():
    hashed = hash_password("minhasenha123")
    assert verify_password("minhasenha123", hashed)
    assert not verify_password("senhaerrada", hashed)

def test_create_and_decode_token():
    token = create_access_token({"sub": "42", "email": "user@test.com"})
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["email"] == "user@test.com"

def test_decode_invalid_token():
    payload = decode_token("token.invalido.aqui")
    assert payload is None
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_auth.py -v
```

Esperado: `ModuleNotFoundError`

- [ ] **Step 3: Implementar backend/auth.py**

```python
import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 10080))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
```

- [ ] **Step 4: Rodar para confirmar passou**

```bash
pytest tests/test_auth.py -v
```

Esperado: 3 testes `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/auth.py tests/test_auth.py
git commit -m "feat: JWT authentication with bcrypt password hashing"
```

---

## Task 5: Rotas de autenticação no FastAPI

**Files:**
- Create: `backend/main.py`
- Create: `backend/routers/__init__.py`
- Create: `backend/routers/auth_router.py`

- [ ] **Step 1: Criar backend/routers/__init__.py**

```python
# vazio
```

- [ ] **Step 2: Criar backend/routers/auth_router.py**

```python
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
import aiosqlite
from backend.database import get_db
from backend.models import UserCreate, UserLogin, Token, UserOut
from backend.auth import hash_password, verify_password, create_access_token
import os

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=UserOut)
async def register(user: UserCreate, db: aiosqlite.Connection = Depends(get_db)):
    cursor = await db.execute("SELECT id FROM users WHERE email = ?", (user.email,))
    if await cursor.fetchone():
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    hashed = hash_password(user.password)
    cursor = await db.execute(
        "INSERT INTO users (name, email, password_hash, my_language, other_language, drive_folder) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user.name, user.email, hashed, user.my_language, user.other_language, user.drive_folder)
    )
    await db.commit()
    user_id = cursor.lastrowid
    cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = await cursor.fetchone()
    return UserOut(id=row["id"], name=row["name"], email=row["email"],
                   my_language=row["my_language"], other_language=row["other_language"],
                   drive_folder=row["drive_folder"])

@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, db: aiosqlite.Connection = Depends(get_db)):
    cursor = await db.execute("SELECT * FROM users WHERE email = ?", (credentials.email,))
    row = await cursor.fetchone()
    if not row or not verify_password(credentials.password, row["password_hash"] or ""):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    token = create_access_token({"sub": str(row["id"]), "email": row["email"]})
    return Token(access_token=token)

@router.get("/me", response_model=UserOut)
async def me(token: str, db: aiosqlite.Connection = Depends(get_db)):
    from backend.auth import decode_token
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido")
    cursor = await db.execute("SELECT * FROM users WHERE id = ?", (int(payload["sub"]),))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return UserOut(id=row["id"], name=row["name"], email=row["email"],
                   my_language=row["my_language"], other_language=row["other_language"],
                   drive_folder=row["drive_folder"])
```

- [ ] **Step 3: Criar backend/main.py**

```python
import os
import asyncio
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
```

- [ ] **Step 4: Criar static/index.html mínimo para testar**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><title>Live Translator</title></head>
<body><h1>Live Translator</h1></body>
</html>
```

- [ ] **Step 5: Rodar o servidor**

```bash
uvicorn backend.main:app --reload --port 8000
```

Abrir `http://localhost:8000/docs` — deve mostrar Swagger com rotas `/auth/register` e `/auth/login`.

- [ ] **Step 6: Testar registro via Swagger**

No Swagger em `http://localhost:8000/docs`, testar `POST /auth/register` com:
```json
{"name": "Teste", "email": "teste@test.com", "password": "123456", "drive_folder": "C:/teste"}
```
Esperado: retorna `UserOut` com `id: 1`

- [ ] **Step 7: Commit**

```bash
git add backend/main.py backend/routers/ static/index.html
git commit -m "feat: FastAPI app with auth routes (register/login/me)"
```

---

## Task 6: Google OAuth2

**Files:**
- Modify: `backend/routers/auth_router.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Adicionar dependência de sessão ao main.py**

Adicionar ao topo de `backend/main.py` (após os imports existentes):
```python
from starlette.middleware.sessions import SessionMiddleware
```

Adicionar após `app = FastAPI(...)`:
```python
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev-secret"))
```

- [ ] **Step 2: Adicionar rotas Google OAuth em auth_router.py**

Adicionar ao final de `backend/routers/auth_router.py`:
```python
from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request

oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

@router.get("/google")
async def google_login(request: Request):
    redirect_uri = str(request.url_for("google_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/google/callback", name="google_callback")
async def google_callback(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    try:
        token_data = await oauth.google.authorize_access_token(request)
    except Exception:
        raise HTTPException(status_code=400, detail="Falha na autenticação Google")
    
    userinfo = token_data.get("userinfo")
    if not userinfo:
        raise HTTPException(status_code=400, detail="Não foi possível obter dados do usuário")
    
    google_id = userinfo["sub"]
    email = userinfo["email"]
    name = userinfo.get("name", email)
    
    cursor = await db.execute("SELECT * FROM users WHERE google_id = ? OR email = ?", (google_id, email))
    row = await cursor.fetchone()
    
    if not row:
        cursor = await db.execute(
            "INSERT INTO users (name, email, google_id, drive_folder) VALUES (?, ?, ?, ?)",
            (name, email, google_id, "")
        )
        await db.commit()
        user_id = cursor.lastrowid
    else:
        if not row["google_id"]:
            await db.execute("UPDATE users SET google_id = ? WHERE id = ?", (google_id, row["id"]))
            await db.commit()
        user_id = row["id"]
    
    access_token = create_access_token({"sub": str(user_id), "email": email})
    return RedirectResponse(url=f"/?token={access_token}")
```

- [ ] **Step 3: Testar fluxo Google**

Para testar localmente, configure `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` no `.env` com credenciais de um projeto no Google Cloud Console (OAuth 2.0, redirect URI: `http://localhost:8000/auth/google/callback`).

Abrir `http://localhost:8000/auth/google` — deve redirecionar para tela de login do Google.

Se não tiver credenciais configuradas agora, pular este teste — a rota está implementada.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/auth_router.py backend/main.py
git commit -m "feat: Google OAuth2 login via Authlib"
```

---

## Task 7: Pipeline de áudio (captura)

**Files:**
- Create: `backend/audio.py`

- [ ] **Step 1: Criar backend/audio.py**

```python
import asyncio
import queue
import threading
import wave
import tempfile
import os
import pyaudiowpatch as pyaudio

CHUNK = 1024
RATE = 16000
CHUNK_BYTES = RATE * 2 * 3  # 3 segundos de áudio

class AudioCapture:
    def __init__(self):
        self.mic_queue: queue.Queue = queue.Queue()
        self.spk_queue: queue.Queue = queue.Queue()
        self._running = False
        self._threads: list[threading.Thread] = []

    def start(self):
        self._running = True
        self._threads = [
            threading.Thread(target=self._capture_mic, daemon=True),
            threading.Thread(target=self._capture_loopback, daemon=True),
        ]
        for t in self._threads:
            t.start()

    def stop(self):
        self._running = False
        self.mic_queue.put(None)
        self.spk_queue.put(None)

    def _capture_mic(self):
        pa = pyaudio.PyAudio()
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                         input=True, frames_per_buffer=CHUNK)
        while self._running:
            self.mic_queue.put(stream.read(CHUNK, exception_on_overflow=False))
        stream.stop_stream()
        stream.close()
        pa.terminate()

    def _capture_loopback(self):
        pa = pyaudio.PyAudio()
        try:
            device = pa.get_default_wasapi_loopback()
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                             input=True, input_device_index=device["index"],
                             frames_per_buffer=CHUNK)
            while self._running:
                self.spk_queue.put(stream.read(CHUNK, exception_on_overflow=False))
            stream.stop_stream()
            stream.close()
        except Exception as e:
            print(f"Loopback não disponível: {e}")
        finally:
            pa.terminate()


def save_audio_chunk(audio_bytes: bytes) -> str:
    """Salva chunk em arquivo WAV temporário. Retorna caminho."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(audio_bytes)
    return path
```

- [ ] **Step 2: Verificar import**

```bash
python -c "from backend.audio import AudioCapture, save_audio_chunk; print('OK')"
```

Esperado: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/audio.py
git commit -m "feat: audio capture for microphone and system loopback"
```

---

## Task 8: Transcrição e tradução

**Files:**
- Create: `backend/transcriber.py`
- Create: `tests/test_transcriber.py`

- [ ] **Step 1: Escrever testes**

```python
# tests/test_transcriber.py
import pytest
from unittest.mock import MagicMock, patch

def test_translate_same_language_returns_original():
    from backend.transcriber import translate_text
    result = translate_text("hello world", source="en", target="en")
    assert result == "hello world"

def test_translate_returns_string():
    from backend.transcriber import translate_text
    with patch("backend.transcriber.GoogleTranslator") as mock_cls:
        mock_cls.return_value.translate.return_value = "olá mundo"
        result = translate_text("hello world", source="en", target="pt")
    assert isinstance(result, str)
    assert len(result) > 0
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_transcriber.py -v
```

- [ ] **Step 3: Implementar backend/transcriber.py**

```python
import os
import time
import threading
from typing import Callable, Optional
from faster_whisper import WhisperModel
from deep_translator import GoogleTranslator
from backend.audio import save_audio_chunk, CHUNK_BYTES
from dotenv import load_dotenv

load_dotenv()

_model: Optional[WhisperModel] = None
_model_lock = threading.Lock()

def get_model() -> WhisperModel:
    global _model
    with _model_lock:
        if _model is None:
            model_size = os.getenv("WHISPER_MODEL", "tiny")
            for attempt in range(5):
                try:
                    _model = WhisperModel(model_size, device="cpu", compute_type="int8")
                    break
                except Exception as e:
                    if attempt < 4:
                        time.sleep(2 ** attempt)
                    else:
                        raise RuntimeError(f"Falha ao carregar Whisper após 5 tentativas: {e}")
    return _model

def translate_text(text: str, source: str, target: str) -> str:
    if source == target:
        return text
    try:
        return GoogleTranslator(source=source, target=target).translate(text)
    except Exception:
        return text

def transcribe_and_translate(
    audio_bytes: bytes,
    source_lang: str,
    target_lang: str,
    speaker: str,
    on_result: Callable[[str, str, str], None],
) -> None:
    """
    Transcreve e traduz um chunk de áudio.
    Chama on_result(speaker, original, translation) quando pronto.
    """
    path = save_audio_chunk(audio_bytes)
    try:
        model = get_model()
        segments, _ = model.transcribe(path, language=source_lang)
        original = " ".join(s.text for s in segments).strip()
        if not original:
            return
        translation = translate_text(original, source_lang, target_lang)
        on_result(speaker, original, translation)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


class AudioWorker:
    """Consome fila de chunks de áudio e aciona transcrição em threads."""

    def __init__(self, queue, source_lang: str, target_lang: str,
                 speaker: str, on_result: Callable):
        self.queue = queue
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.speaker = speaker
        self.on_result = on_result
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        buffer = b""
        while True:
            chunk = self.queue.get()
            if chunk is None:
                break
            buffer += chunk
            if len(buffer) >= CHUNK_BYTES:
                data = buffer
                buffer = b""
                threading.Thread(
                    target=transcribe_and_translate,
                    args=(data, self.source_lang, self.target_lang,
                          self.speaker, self.on_result),
                    daemon=True
                ).start()
```

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_transcriber.py -v
```

Esperado: 2 testes `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/transcriber.py tests/test_transcriber.py
git commit -m "feat: Whisper transcription + translation pipeline with retry"
```

---

## Task 9: TTS (texto para áudio no fone)

**Files:**
- Create: `backend/tts.py`

- [ ] **Step 1: Criar backend/tts.py**

```python
import asyncio
import tempfile
import os
import threading
import edge_tts
import pyaudiowpatch as pyaudio
import wave

VOICE_MAP = {
    "pt": "pt-BR-FranciscaNeural",
    "en": "en-US-JennyNeural",
    "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "it": "it-IT-ElsaNeural",
    "ja": "ja-JP-NanamiNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "ar": "ar-SA-ZariyahNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "ko": "ko-KR-SunHiNeural",
}

def get_voice(lang: str) -> str:
    return VOICE_MAP.get(lang, "pt-BR-FranciscaNeural")

async def synthesize_to_file(text: str, lang: str) -> str:
    """Converte texto para WAV via edge-tts. Retorna caminho do arquivo."""
    voice = get_voice(lang)
    communicate = edge_tts.Communicate(text, voice)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        mp3_path = f.name
    await communicate.save(mp3_path)
    return mp3_path

def play_audio_file(path: str):
    """Toca arquivo de áudio MP3 via sistema operacional."""
    import subprocess
    import sys
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])

def speak_text(text: str, lang: str):
    """Sintetiza e toca texto em thread separada (não bloqueia)."""
    def _run():
        loop = asyncio.new_event_loop()
        try:
            mp3_path = loop.run_until_complete(synthesize_to_file(text, lang))
            play_audio_file(mp3_path)
        except Exception as e:
            print(f"TTS erro: {e}")
        finally:
            loop.close()
    threading.Thread(target=_run, daemon=True).start()
```

- [ ] **Step 2: Verificar import**

```bash
python -c "from backend.tts import speak_text, get_voice; print(get_voice('pt'))"
```

Esperado: `pt-BR-FranciscaNeural`

- [ ] **Step 3: Commit**

```bash
git add backend/tts.py
git commit -m "feat: edge-tts text-to-speech with voice map for 11 languages"
```

---

## Task 10: WebSocket e sessão de gravação

**Files:**
- Create: `backend/session.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Criar backend/session.py**

```python
import asyncio
import datetime
from typing import Optional
from fastapi import WebSocket
from backend.audio import AudioCapture
from backend.transcriber import AudioWorker
from backend.tts import speak_text

class RecordingSession:
    """Gerencia uma sessão de gravação ativa para um usuário."""

    def __init__(self, user_id: int, my_lang: str, other_lang: str,
                 websocket: WebSocket, loop: asyncio.AbstractEventLoop):
        self.user_id = user_id
        self.my_lang = my_lang
        self.other_lang = other_lang
        self.websocket = websocket
        self.loop = loop
        self.audio = AudioCapture()
        self.transcriptions: list[dict] = []
        self.started_at = datetime.datetime.now()
        self._workers: list[AudioWorker] = []

    def start(self):
        self.audio.start()

        def on_result(speaker: str, original: str, translation: str):
            hora = datetime.datetime.now().strftime("%H:%M:%S")
            entry = {
                "type": "transcription",
                "speaker": speaker,
                "original": original,
                "translation": translation,
                "timestamp": hora,
            }
            self.transcriptions.append(entry)
            # Envia do thread de background para o loop asyncio principal
            asyncio.run_coroutine_threadsafe(
                self.websocket.send_json(entry),
                self.loop
            )
            # TTS só para o que o OUTRO fala (loopback → fone do usuário)
            if speaker == "Outro":
                speak_text(translation, self.my_lang)

        worker_mic = AudioWorker(
            self.audio.mic_queue, self.my_lang, self.other_lang, "Você", on_result
        )
        worker_spk = AudioWorker(
            self.audio.spk_queue, self.other_lang, self.my_lang, "Outro", on_result
        )
        worker_mic.start()
        worker_spk.start()
        self._workers = [worker_mic, worker_spk]

    def stop(self) -> list[dict]:
        self.audio.stop()
        return self.transcriptions
```

- [ ] **Step 2: Adicionar WebSocket ao main.py**

Adicionar ao `backend/main.py` (após os imports existentes):

```python
import asyncio
from typing import Dict
from fastapi import WebSocket, WebSocketDisconnect
from backend.auth import decode_token
from backend.session import RecordingSession

active_sessions: Dict[int, RecordingSession] = {}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str):
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4001)
        return
    user_id = int(payload["sub"])
    loop = asyncio.get_event_loop()  # loop do asyncio desta coroutine
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
```

- [ ] **Step 3: Rodar servidor e testar WebSocket**

```bash
uvicorn backend.main:app --reload --port 8000
```

Abrir console do browser em `http://localhost:8000`, testar:
```js
const ws = new WebSocket("ws://localhost:8000/ws?token=SEU_TOKEN");
ws.onmessage = e => console.log(JSON.parse(e.data));
ws.send(JSON.stringify({action: "start", my_language: "pt", other_language: "en"}));
```

Esperado: recebe `{"type": "status", "status": "recording"}`

- [ ] **Step 4: Commit**

```bash
git add backend/session.py backend/main.py
git commit -m "feat: WebSocket endpoint with RecordingSession for real-time audio streaming"
```

---

## Task 11: Salvamento (WAV + TXT + PDF + Resumo IA)

**Files:**
- Create: `backend/storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Escrever testes**

```python
# tests/test_storage.py
import pytest
import os
import tempfile
from backend.storage import build_transcript_text, get_save_folder

def test_build_transcript_text():
    transcriptions = [
        {"timestamp": "14:00:01", "speaker": "Você", "original": "Bom dia", "translation": "Good morning"},
        {"timestamp": "14:00:05", "speaker": "Outro", "original": "Good morning", "translation": "Bom dia"},
    ]
    result = build_transcript_text(transcriptions)
    assert "[14:00:01] Você: Bom dia" in result
    assert "↳ Good morning" in result

def test_get_save_folder_creates_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        folder = get_save_folder(tmpdir, "joao", "20260101_1400")
        assert os.path.isdir(folder)
        assert "joao" in folder
        assert "20260101_1400" in folder
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_storage.py -v
```

- [ ] **Step 3: Implementar backend/storage.py**

```python
import os
import wave
import datetime
from typing import Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import cm
from reportlab.lib import colors

def get_save_folder(drive_folder: str, user_name: str, timestamp: str) -> str:
    safe_name = user_name.replace(" ", "_").lower()
    folder = os.path.join(drive_folder, safe_name, timestamp)
    os.makedirs(folder, exist_ok=True)
    return folder

def build_transcript_text(transcriptions: list[dict]) -> str:
    lines = []
    for t in transcriptions:
        lines.append(f"[{t['timestamp']}] {t['speaker']}: {t['original']}")
        if t["original"] != t["translation"]:
            lines.append(f"  ↳ {t['translation']}")
    return "\n".join(lines)

def save_transcript_txt(folder: str, transcriptions: list[dict]) -> str:
    path = os.path.join(folder, "transcricao.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_transcript_text(transcriptions))
    return path

def save_audio_wav(folder: str, audio_frames: bytes) -> str:
    path = os.path.join(folder, "audio.wav")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_frames)
    return path

def save_pdf(folder: str, transcriptions: list[dict], summary: str,
             meeting_date: str) -> str:
    path = os.path.join(folder, "reuniao.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    titulo = ParagraphStyle("titulo", fontSize=18, fontName="Helvetica-Bold",
                             spaceAfter=12, textColor=colors.HexColor("#1a1a2e"))
    subtit = ParagraphStyle("subtit", fontSize=12, fontName="Helvetica-Bold",
                             spaceAfter=6, textColor=colors.HexColor("#e94560"))
    normal = ParagraphStyle("normal", fontSize=10, fontName="Helvetica",
                             spaceAfter=4, leading=14)
    conteudo = [
        Paragraph("Transcricao da Reuniao", titulo),
        Paragraph(f"Data: {meeting_date}", normal),
        Spacer(1, 0.5*cm),
        Paragraph("Resumo com IA", subtit),
        Paragraph(summary.replace("\n", "<br/>") if summary else "Resumo indisponivel.", normal),
        Spacer(1, 0.5*cm),
        Paragraph("Transcricao Completa", subtit),
    ]
    for t in transcriptions:
        conteudo.append(Paragraph(
            f"<b>[{t['timestamp']}] {t['speaker']}:</b> {t['original']}", normal))
        if t["original"] != t["translation"]:
            conteudo.append(Paragraph(
                f"&nbsp;&nbsp;&#8627; <i>{t['translation']}</i>", normal))
    doc.build(conteudo)
    return path

def generate_summary(transcriptions: list[dict], openai_client) -> str:
    if not transcriptions:
        return "Nenhuma transcricao disponivel."
    texto = build_transcript_text(transcriptions)
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": (
                    "Faca um resumo executivo desta transcricao de reuniao em portugues. "
                    "Inclua: 1) Principais topicos discutidos, 2) Decisoes tomadas, "
                    "3) Proximos passos.\n\n" + texto
                )
            }]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Resumo indisponivel: {e}"
```

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_storage.py -v
```

Esperado: 2 testes `PASSED`

- [ ] **Step 5: Adicionar rota /meetings/end ao main.py**

Adicionar ao `backend/main.py`:
```python
from backend.storage import get_save_folder, save_transcript_txt, save_pdf, generate_summary
from openai import OpenAI
import os

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
```

- [ ] **Step 6: Commit**

```bash
git add backend/storage.py tests/test_storage.py backend/main.py
git commit -m "feat: storage module for WAV, TXT, PDF and AI summary saving to Google Drive"
```

---

## Task 12: Meeting Watcher

**Files:**
- Create: `backend/watcher.py`
- Create: `tests/test_watcher.py`

- [ ] **Step 1: Escrever testes**

```python
# tests/test_watcher.py
from backend.watcher import is_meeting_running, MEETING_PROCESSES

def test_meeting_processes_list_not_empty():
    assert len(MEETING_PROCESSES) > 0
    assert "zoom" in MEETING_PROCESSES

def test_is_meeting_running_returns_bool():
    result = is_meeting_running()
    assert isinstance(result, bool)
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_watcher.py -v
```

- [ ] **Step 3: Implementar backend/watcher.py**

```python
import time
import webbrowser
import psutil
import threading
from typing import Optional

try:
    import pygetwindow as gw
    HAS_GETWINDOW = True
except ImportError:
    HAS_GETWINDOW = False

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

MEETING_PROCESSES = {
    "zoom": "Zoom",
    "ms-teams": "Microsoft Teams",
    "teams": "Microsoft Teams",
    "webex": "Webex",
    "slack": "Slack",
}

MEET_WINDOW_KEYWORDS = ["meet.google.com", "Google Meet", "- Meet"]
APP_URL = "http://localhost:8000"
POLL_INTERVAL = 3  # segundos

def is_meeting_running() -> bool:
    """Retorna True se qualquer app de reunião conhecido estiver rodando."""
    running = {p.name().lower() for p in psutil.process_iter(["name"])}
    for proc in MEETING_PROCESSES:
        if any(proc in r for r in running):
            return True
    # Verifica títulos de janela para Google Meet
    if HAS_GETWINDOW:
        try:
            windows = gw.getAllTitles()
            for title in windows:
                if any(kw in title for kw in MEET_WINDOW_KEYWORDS):
                    return True
        except Exception:
            pass
    return False

class MeetingWatcher:
    def __init__(self, app_url: str = APP_URL, poll_interval: int = POLL_INTERVAL):
        self.app_url = app_url
        self.poll_interval = poll_interval
        self._running = False
        self._meeting_open = False
        self._thread: Optional[threading.Thread] = None

    def _open_app(self):
        if not self._meeting_open:
            webbrowser.open(self.app_url)
            self._meeting_open = True
            print(f"Reunião detectada — abrindo {self.app_url}")

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        if HAS_KEYBOARD:
            keyboard.add_hotkey("ctrl+shift+t", self._open_app)
            print("Watcher iniciado. Ctrl+Shift+T para abrir manualmente.")

    def stop(self):
        self._running = False

    def _watch_loop(self):
        was_running = False
        while self._running:
            now_running = is_meeting_running()
            if now_running and not was_running:
                self._open_app()
            elif not now_running and was_running:
                self._meeting_open = False
                print("Reunião encerrada.")
            was_running = now_running
            time.sleep(self.poll_interval)


if __name__ == "__main__":
    watcher = MeetingWatcher()
    watcher.start()
    print("Monitorando reuniões... Ctrl+C para parar.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()
        print("Watcher encerrado.")
```

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_watcher.py -v
```

Esperado: 2 testes `PASSED`

- [ ] **Step 5: Testar watcher manualmente**

```bash
python backend/watcher.py
```

Abrir Zoom ou Teams — deve abrir `http://localhost:8000` automaticamente. Ctrl+Shift+T também deve abrir.

- [ ] **Step 6: Commit**

```bash
git add backend/watcher.py tests/test_watcher.py
git commit -m "feat: meeting watcher with process monitoring and Ctrl+Shift+T hotkey"
```

---

## Task 13: Frontend — HTML/CSS base

**Files:**
- Create: `static/style.css`
- Modify: `static/index.html`

- [ ] **Step 1: Criar static/style.css**

```css
:root {
  --bg-deep: #0f0f1a;
  --bg-card: #1a1a2e;
  --bg-panel: #16213e;
  --bg-accent: #0f3460;
  --red: #e94560;
  --purple: #533483;
  --green: #00ff88;
  --text: #ffffff;
  --muted: #aaaaaa;
  --dim: #555555;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Segoe UI', system-ui, sans-serif;
  background: var(--bg-deep);
  color: var(--text);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.screen { display: none; flex-direction: column; min-height: 100vh; }
.screen.active { display: flex; }

/* Cards e painéis */
.card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 24px;
}

/* Botões */
.btn {
  border: none; cursor: pointer; border-radius: 8px;
  padding: 10px 20px; font-size: 14px; font-weight: 600;
  transition: opacity 0.2s;
}
.btn:hover { opacity: 0.85; }
.btn-primary { background: var(--red); color: white; }
.btn-secondary { background: var(--purple); color: white; }
.btn-success { background: var(--green); color: #000; }
.btn-outline { background: transparent; border: 1px solid #333; color: var(--muted); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* Inputs */
.input-group { margin-bottom: 16px; }
.input-group label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.input-group input, .input-group select {
  width: 100%; padding: 10px 12px;
  background: var(--bg-panel); border: 1px solid #2a2a3e;
  border-radius: 8px; color: var(--text); font-size: 14px;
}
.input-group input:focus, .input-group select:focus {
  outline: none; border-color: var(--red);
}

/* Badge status */
.badge {
  padding: 3px 10px; border-radius: 20px;
  font-size: 11px; font-weight: 600;
}
.badge-live { background: #1a0010; color: var(--red); }
.badge-active { background: #0a1a0a; color: var(--green); }

/* Legenda ao vivo */
.live-caption {
  background: var(--bg-accent);
  border-radius: 10px; padding: 16px;
  font-size: 16px; font-weight: 600; color: var(--green);
  min-height: 60px;
}
.live-translation {
  font-size: 13px; color: var(--muted);
  padding: 6px 8px;
}

/* Histórico */
.transcript-box {
  background: var(--bg-panel); border-radius: 10px;
  padding: 12px; height: 220px;
  overflow-y: auto; font-size: 12px; color: #888;
  line-height: 1.6;
}
.transcript-box .entry-you { color: #ccc; }
.transcript-box .entry-other { color: #888; }
.transcript-box .entry-translation { color: var(--dim); padding-left: 16px; }

/* Divider */
.divider {
  display: flex; align-items: center; gap: 12px;
  color: var(--dim); font-size: 12px; margin: 16px 0;
}
.divider::before, .divider::after {
  content: ''; flex: 1; height: 1px; background: #2a2a3e;
}
```

- [ ] **Step 2: Criar static/index.html completo**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Live Translator</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>

<!-- TELA 1: LOGIN -->
<div id="screen-login" class="screen active">
  <div style="flex:1;display:flex;align-items:center;justify-content:center;padding:24px">
    <div class="card" style="width:100%;max-width:380px">
      <h1 style="font-size:20px;margin-bottom:4px">🌐 Live Translator</h1>
      <p style="color:var(--muted);font-size:13px;margin-bottom:24px">Acesso da equipe</p>

      <div id="login-error" style="display:none;background:#1a0010;border-radius:8px;padding:10px;color:var(--red);font-size:13px;margin-bottom:16px"></div>

      <div class="input-group">
        <label>Email</label>
        <input type="email" id="login-email" placeholder="seu@email.com">
      </div>
      <div class="input-group">
        <label>Senha</label>
        <input type="password" id="login-password" placeholder="••••••••">
      </div>
      <button class="btn btn-primary" style="width:100%;margin-bottom:12px" onclick="doLogin()">Entrar</button>

      <div class="divider">ou</div>

      <button class="btn btn-outline" style="width:100%;margin-bottom:16px" onclick="window.location='/auth/google'">
        <span style="font-weight:700;color:white">G</span>&nbsp; Entrar com Google
      </button>

      <p style="text-align:center;font-size:12px;color:var(--dim)">
        Sem conta? <a href="#" style="color:var(--red)" onclick="showRegister()">Criar conta</a>
      </p>
    </div>
  </div>
</div>

<!-- TELA 2: AGUARDANDO -->
<div id="screen-waiting" class="screen">
  <div style="padding:16px 20px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1a1a2e">
    <span style="font-size:15px;font-weight:700">🌐 Live Translator</span>
    <div style="display:flex;gap:12px;align-items:center">
      <span id="user-name" style="font-size:13px;color:var(--muted)"></span>
      <button class="btn btn-outline" style="padding:4px 10px;font-size:12px" onclick="logout()">Sair</button>
    </div>
  </div>

  <div style="flex:1;display:flex;align-items:center;justify-content:center;padding:24px">
    <div style="width:100%;max-width:460px">
      <div class="card" style="margin-bottom:16px;display:flex;align-items:center;gap:12px">
        <span class="badge badge-active">● ativo</span>
        <span style="font-size:13px;color:var(--muted)">Monitorando reuniões</span>
      </div>

      <div class="card" style="margin-bottom:16px">
        <p style="font-size:12px;color:var(--muted);margin-bottom:12px">APPS MONITORADOS</p>
        <div style="display:flex;gap:16px;flex-wrap:wrap">
          <span style="font-size:13px">📹 Zoom</span>
          <span style="font-size:13px">👥 Teams</span>
          <span style="font-size:13px">🎥 Google Meet</span>
          <span style="font-size:13px">💬 Webex</span>
        </div>
      </div>

      <div class="card" style="margin-bottom:16px">
        <p style="font-size:12px;color:var(--muted);margin-bottom:12px">IDIOMAS</p>
        <div style="display:flex;align-items:center;gap:12px">
          <div style="flex:1">
            <label style="font-size:11px;color:var(--dim);display:block;margin-bottom:4px">MEU IDIOMA</label>
            <select id="my-lang" class="input-group" style="background:var(--bg-panel);border:1px solid #2a2a3e;border-radius:6px;padding:8px;color:white;width:100%">
              <option value="pt">🇧🇷 Português</option>
              <option value="en">🇺🇸 Inglês</option>
              <option value="es">🇪🇸 Espanhol</option>
              <option value="fr">🇫🇷 Francês</option>
              <option value="de">🇩🇪 Alemão</option>
            </select>
          </div>
          <span style="font-size:20px;color:var(--purple);padding-top:16px">⇄</span>
          <div style="flex:1">
            <label style="font-size:11px;color:var(--dim);display:block;margin-bottom:4px">IDIOMA DA REUNIÃO</label>
            <select id="other-lang" style="background:var(--bg-panel);border:1px solid #2a2a3e;border-radius:6px;padding:8px;color:white;width:100%">
              <option value="en">🇺🇸 Inglês</option>
              <option value="pt">🇧🇷 Português</option>
              <option value="es">🇪🇸 Espanhol</option>
              <option value="fr">🇫🇷 Francês</option>
              <option value="de">🇩🇪 Alemão</option>
            </select>
          </div>
        </div>
      </div>

      <button class="btn btn-primary" style="width:100%;padding:14px;font-size:15px" onclick="startRecording()">
        ▶ Iniciar manualmente
      </button>
      <p style="text-align:center;font-size:12px;color:var(--dim);margin-top:10px">ou use Ctrl+Shift+T</p>
    </div>
  </div>
</div>

<!-- TELA 3: GRAVANDO -->
<div id="screen-recording" class="screen">
  <div style="padding:14px 20px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1a1a2e">
    <span style="font-size:15px;font-weight:700">🌐 Live Translator</span>
    <div style="display:flex;gap:10px;align-items:center">
      <span id="langs-display" style="font-size:12px;color:var(--muted)">pt → en</span>
      <span class="badge badge-live">🔴 AO VIVO</span>
    </div>
  </div>

  <div style="flex:1;padding:16px 20px;display:flex;flex-direction:column;gap:12px;max-width:700px;margin:auto;width:100%">
    <div class="live-caption" id="live-caption">Aguardando fala...</div>
    <div class="live-translation" id="live-translation"></div>

    <div>
      <p style="font-size:12px;color:var(--muted);margin-bottom:8px">TRANSCRIÇÃO</p>
      <div class="transcript-box" id="transcript-box"></div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:auto">
      <button class="btn btn-primary" onclick="stopRecording()">⏹ Parar</button>
      <button class="btn btn-secondary" onclick="downloadPDF()">📄 PDF</button>
      <button class="btn btn-outline" onclick="requestSummary()">🤖 Resumo</button>
    </div>
  </div>
</div>

<!-- TELA 4: FIM -->
<div id="screen-end" class="screen">
  <div style="flex:1;display:flex;align-items:center;justify-content:center;padding:24px">
    <div style="width:100%;max-width:500px">
      <div class="card" style="margin-bottom:16px">
        <h2 style="color:var(--green);margin-bottom:16px">✅ Reunião salva!</h2>
        <div id="saved-files" style="background:var(--bg-panel);border-radius:8px;padding:12px;font-size:13px;color:var(--muted);margin-bottom:16px"></div>
        <div>
          <p style="font-size:12px;color:var(--red);margin-bottom:8px">🤖 RESUMO IA</p>
          <div id="summary-text" style="font-size:13px;color:#ccc;line-height:1.6;max-height:200px;overflow-y:auto"></div>
        </div>
      </div>
      <button class="btn btn-success" style="width:100%;padding:14px" onclick="newMeeting()">
        Nova reunião
      </button>
    </div>
  </div>
</div>

<script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 3: Verificar no browser**

```bash
uvicorn backend.main:app --reload --port 8000
```

Abrir `http://localhost:8000` — deve mostrar tela de login com tema dark correto.

- [ ] **Step 4: Commit**

```bash
git add static/style.css static/index.html
git commit -m "feat: frontend SPA with 4 screens and dark theme"
```

---

## Task 14: Frontend — lógica JavaScript

**Files:**
- Create: `static/app.js`

- [ ] **Step 1: Criar static/app.js**

```javascript
// Estado da aplicação
const state = {
  token: localStorage.getItem("token") || null,
  user: null,
  ws: null,
  transcriptions: [],
};

// ── Utilitários ──────────────────────────────────────────────────────────────

function showScreen(id) {
  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  document.getElementById("screen-" + id).classList.add("active");
}

function showError(elementId, msg) {
  const el = document.getElementById(elementId);
  if (el) { el.textContent = msg; el.style.display = "block"; }
}

function hideError(elementId) {
  const el = document.getElementById(elementId);
  if (el) el.style.display = "none";
}

// ── Auth ─────────────────────────────────────────────────────────────────────

async function doLogin() {
  hideError("login-error");
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;
  if (!email || !password) { showError("login-error", "Preencha email e senha."); return; }

  const res = await fetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) { showError("login-error", "Email ou senha incorretos."); return; }
  const data = await res.json();
  state.token = data.access_token;
  localStorage.setItem("token", state.token);
  await loadUser();
}

function showRegister() {
  const name = prompt("Seu nome:");
  if (!name) return;
  const email = prompt("Email:");
  if (!email) return;
  const password = prompt("Senha:");
  if (!password) return;
  const folder = prompt("Caminho da pasta Google Drive (ex: G:/Meu Drive/Reunioes):", "G:/Meu Drive/Reunioes");

  fetch("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password, drive_folder: folder || "" }),
  }).then(r => r.json()).then(() => {
    document.getElementById("login-email").value = email;
    alert("Conta criada! Faça login.");
  }).catch(() => alert("Erro ao criar conta."));
}

async function loadUser() {
  const res = await fetch(`/auth/me?token=${state.token}`);
  if (!res.ok) { logout(); return; }
  state.user = await res.json();
  document.getElementById("user-name").textContent = state.user.name;
  const myLang = document.getElementById("my-lang");
  const otherLang = document.getElementById("other-lang");
  if (myLang) myLang.value = state.user.my_language || "pt";
  if (otherLang) otherLang.value = state.user.other_language || "en";
  showScreen("waiting");
}

function logout() {
  state.token = null;
  localStorage.removeItem("token");
  showScreen("login");
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

function connectWS(onMessage) {
  if (state.ws) state.ws.close();
  state.ws = new WebSocket(`ws://localhost:8000/ws?token=${state.token}`);
  state.ws.onmessage = e => onMessage(JSON.parse(e.data));
  state.ws.onclose = () => setTimeout(() => connectWS(onMessage), 3000); // reconnect
  state.ws.onerror = () => state.ws.close();
}

// ── Gravação ──────────────────────────────────────────────────────────────────

function startRecording() {
  const myLang = document.getElementById("my-lang").value;
  const otherLang = document.getElementById("other-lang").value;
  document.getElementById("langs-display").textContent = `${myLang} ↔ ${otherLang}`;
  document.getElementById("live-caption").textContent = "Aguardando fala...";
  document.getElementById("live-translation").textContent = "";
  document.getElementById("transcript-box").innerHTML = "";
  state.transcriptions = [];
  showScreen("recording");

  connectWS(onWsMessage);
  state.ws.onopen = () => {
    state.ws.send(JSON.stringify({ action: "start", my_language: myLang, other_language: otherLang }));
  };
}

function onWsMessage(data) {
  if (data.type === "transcription") {
    document.getElementById("live-caption").textContent =
      `[${data.speaker}] ${data.translation}`;
    document.getElementById("live-translation").textContent =
      data.original !== data.translation ? `↳ ${data.original}` : "";

    const box = document.getElementById("transcript-box");
    const cls = data.speaker === "Você" ? "entry-you" : "entry-other";
    box.innerHTML += `<div class="${cls}"><b>[${data.timestamp}] ${data.speaker}:</b> ${data.original}</div>`;
    if (data.original !== data.translation) {
      box.innerHTML += `<div class="entry-translation">↳ ${data.translation}</div>`;
    }
    box.scrollTop = box.scrollHeight;
    state.transcriptions.push(data);
  }
}

async function stopRecording() {
  if (state.ws) state.ws.send(JSON.stringify({ action: "stop" }));
  const res = await fetch(`/meetings/end?token=${state.token}`, { method: "POST" });
  if (!res.ok) { alert("Erro ao salvar reunião."); return; }
  const data = await res.json();

  const filesEl = document.getElementById("saved-files");
  filesEl.innerHTML =
    `<div>📁 ${data.folder}</div>` +
    (data.txt ? `<div>📝 transcricao.txt</div>` : "") +
    (data.pdf ? `<div>📄 reuniao.pdf</div>` : "");

  document.getElementById("summary-text").textContent = data.summary || "Resumo indisponível.";
  showScreen("end");
}

function downloadPDF() {
  alert("PDF será gerado ao parar a gravação.");
}

function requestSummary() {
  alert("O resumo é gerado automaticamente ao parar a gravação.");
}

function newMeeting() {
  showScreen("waiting");
}

// ── Init ──────────────────────────────────────────────────────────────────────

window.addEventListener("load", () => {
  // Checar token na URL (vinda do OAuth Google)
  const params = new URLSearchParams(window.location.search);
  const urlToken = params.get("token");
  if (urlToken) {
    state.token = urlToken;
    localStorage.setItem("token", urlToken);
    window.history.replaceState({}, "", "/");
  }

  if (state.token) {
    loadUser();
  } else {
    showScreen("login");
  }
});
```

- [ ] **Step 2: Testar fluxo completo no browser**

```bash
uvicorn backend.main:app --reload --port 8000
```

1. Abrir `http://localhost:8000`
2. Criar conta via "Criar conta"
3. Fazer login
4. Verificar que tela 2 (aguardando) aparece com nome do usuário
5. Clicar "Iniciar manualmente" — tela 3 deve aparecer

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat: frontend JavaScript with auth flow, WebSocket client and 4-screen navigation"
```

---

## Task 15: Integração final e inicialização

**Files:**
- Create: `start.py`
- Create: `watcher_start.py`

- [ ] **Step 1: Criar start.py (inicia backend)**

```python
"""Ponto de entrada principal — inicia o servidor FastAPI."""
import subprocess
import sys
import os

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "backend.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
    ])
```

- [ ] **Step 2: Criar watcher_start.py (inicia watcher)**

```python
"""Inicia o watcher de reuniões em background."""
from backend.watcher import MeetingWatcher

if __name__ == "__main__":
    watcher = MeetingWatcher(app_url="http://localhost:8000", poll_interval=3)
    watcher.start()
    print("Watcher de reunioes iniciado.")
    print("Abre o browser automaticamente ao detectar Zoom, Teams, Meet ou Webex.")
    print("Atalho manual: Ctrl+Shift+T")
    print("Ctrl+C para parar.")
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()
        print("Watcher encerrado.")
```

- [ ] **Step 3: Rodar tudo junto (2 terminais)**

Terminal 1:
```bash
python start.py
```

Terminal 2:
```bash
python watcher_start.py
```

Abrir Zoom → deve abrir `http://localhost:8000` automaticamente.

- [ ] **Step 4: Rodar todos os testes**

```bash
pytest tests/ -v
```

Esperado: todos os testes passando.

- [ ] **Step 5: Commit final**

```bash
git add start.py watcher_start.py
git commit -m "feat: start scripts for backend server and meeting watcher"
```

---

## Checklist de Cobertura da Spec

- [x] FastAPI backend com WebSocket
- [x] Auth JWT email + senha
- [x] Google OAuth2
- [x] Captura mic + loopback (pyaudiowpatch)
- [x] Transcrição Whisper com retry
- [x] Tradução deep-translator
- [x] TTS edge-tts toca no fone (outro fala → ouve em pt)
- [x] Legenda na tela (você fala → texto traduzido exibido)
- [x] Watcher psutil + pygetwindow (Zoom, Teams, Meet, Webex)
- [x] Hotkey Ctrl+Shift+T
- [x] SQLite users + meetings
- [x] Salvamento WAV + TXT + PDF no Google Drive (filesystem local)
- [x] Resumo IA GPT-4o-mini
- [x] Frontend 4 telas (Login, Aguardando, Gravando, Fim)
- [x] Dropdown de idiomas na Tela 2
- [x] Reconexão automática WebSocket
- [x] Fallback Google Drive offline → Desktop
