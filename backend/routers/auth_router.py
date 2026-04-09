from fastapi import APIRouter, HTTPException, Depends, Query
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
async def me(token: str = Query(...), db: aiosqlite.Connection = Depends(get_db)):
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
