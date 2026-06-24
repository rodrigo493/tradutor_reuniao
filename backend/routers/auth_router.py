from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse
import asyncpg
from backend.database import get_db
from backend.models import UserCreate, UserLogin, Token, UserOut
from backend.auth import hash_password, verify_password, create_access_token, decode_token
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
async def register(user: UserCreate, db: asyncpg.Connection = Depends(get_db)):
    existing = await db.fetchrow("SELECT id FROM users WHERE email = $1", user.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    user_id = await db.fetchval(
        "INSERT INTO users (name, email, password_hash, my_language, other_language, drive_folder) "
        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
        user.name, user.email, hash_password(user.password),
        user.my_language, user.other_language, user.drive_folder,
    )
    row = await db.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    return UserOut(id=row["id"], name=row["name"], email=row["email"],
                   my_language=row["my_language"], other_language=row["other_language"],
                   drive_folder=row["drive_folder"])

@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, db: asyncpg.Connection = Depends(get_db)):
    row = await db.fetchrow("SELECT * FROM users WHERE email = $1", credentials.email)
    if not row or not row["password_hash"] or not verify_password(credentials.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    token = create_access_token({"sub": str(row["id"]), "email": row["email"]})
    return Token(access_token=token)

@router.get("/me", response_model=UserOut)
async def me(token: str = Query(...), db: asyncpg.Connection = Depends(get_db)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido")
    row = await db.fetchrow("SELECT * FROM users WHERE id = $1", int(payload["sub"]))
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
async def google_callback(request: Request, db: asyncpg.Connection = Depends(get_db)):
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

    row = await db.fetchrow(
        "SELECT * FROM users WHERE google_id = $1 OR email = $2", google_id, email)

    if not row:
        user_id = await db.fetchval(
            "INSERT INTO users (name, email, google_id, drive_folder) "
            "VALUES ($1, $2, $3, $4) RETURNING id",
            name, email, google_id, "",
        )
    else:
        user_id = row["id"]
        if not row["google_id"]:
            await db.execute(
                "UPDATE users SET google_id = $1 WHERE id = $2", google_id, row["id"])

    access_token = create_access_token({"sub": str(user_id), "email": email})
    return RedirectResponse(url=f"/?token={access_token}")
