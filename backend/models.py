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
