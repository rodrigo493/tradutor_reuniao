from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse
import aiosqlite
from backend.database import get_db
from backend.models import UserCreate, UserLogin, Token, UserOut
from backend.auth import hash_password, verify_password, create_access_token
import os

from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request

router = APIRouter(prefix="/auth", tags=["auth"])

oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

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
