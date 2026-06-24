# Supabase Migration — Fase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrar a persistência de SQLite (aiosqlite) para Supabase Postgres usando asyncpg + connection pool, mantendo login e histórico na nuvem.

**Architecture:** Pool asyncpg global em `backend/database.py` (criado/fechado no lifespan do FastAPI). `get_db` entrega conexão do pool. Todas as queries portadas para placeholders Postgres (`$1`), `RETURNING id` no lugar de `lastrowid`, e API asyncpg (`fetch/fetchrow/fetchval/execute`). Tabela `meetings` vira `conversations`. Sem fallback SQLite. Banco começa do zero.

**Tech Stack:** Python 3.14, FastAPI, asyncpg==0.31.0 (instalado), Supabase Postgres 17.6 via Session Pooler.

## Global Constraints

- Plataforma de execução: **Python 3.14** (`py -3.14`). Rodar testes: `py -3.14 -m pytest <arquivo> -v`.
- Driver: **asyncpg==0.31.0** (já instalado). Remover `aiosqlite` ao final.
- Conexão: **Session Pooler** do Supabase. DSN no `.env` como `SUPABASE_DB_URL` (já configurada e validada: `aws-1-sa-east-1.pooler.supabase.com:5432`, user `postgres.<ref>`, Postgres 17.6). **Nunca** hardcodar a DSN/segredo no código.
- Conectar SEMPRE com `ssl="require"` e `statement_cache_size=0` (robustez com pooler).
- asyncpg `Record` suporta `row["coluna"]` — manter esse padrão de acesso.
- asyncpg autocommita comandos fora de transação explícita — **não** chamar `commit()`.
- Tabela `meetings` → `conversations` (DDL nova; sem migração de dados; banco do zero).
- DDL Postgres: `BIGINT GENERATED ALWAYS AS IDENTITY` (não AUTOINCREMENT), `TIMESTAMPTZ` (não DATETIME), `now()` (não CURRENT_TIMESTAMP).
- Testes que tocam o banco são **de integração** contra o Supabase real (precisam de internet + `SUPABASE_DB_URL` no `.env`); usar prefixos únicos para não colidir.
- Commits frequentes, um por task. Sem atribuição.

---

### Task 1: Reescrever `database.py` para asyncpg (pool + DDL Postgres)

**Files:**
- Modify: `backend/database.py`
- Test: `tests/test_database.py` (substituir o conteúdo — o teste antigo usa aiosqlite)

**Interfaces:**
- Produces:
  - `connect_pool() -> asyncpg.Pool` (async) — cria e guarda o pool global a partir de `SUPABASE_DB_URL`.
  - `close_pool() -> None` (async) — fecha o pool.
  - `get_pool() -> asyncpg.Pool` — retorna o pool global (para uso no WebSocket).
  - `init_db(conn) -> None` (async) — cria tabelas `users` e `conversations` (idempotente).
  - `get_db()` (async generator) — `yield` de uma conexão adquirida do pool (dependency FastAPI).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_database.py
import os
import pytest
import asyncpg
from dotenv import load_dotenv
from backend.database import connect_pool, close_pool, init_db

load_dotenv()
pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_DB_URL"), reason="SUPABASE_DB_URL não configurada"
)


@pytest.mark.asyncio
async def test_init_db_creates_tables():
    pool = await connect_pool()
    try:
        async with pool.acquire() as conn:
            await init_db(conn)
            rows = await conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            tables = {r["table_name"] for r in rows}
            assert "users" in tables
            assert "conversations" in tables
    finally:
        await close_pool()


@pytest.mark.asyncio
async def test_init_db_is_idempotent():
    pool = await connect_pool()
    try:
        async with pool.acquire() as conn:
            await init_db(conn)
            await init_db(conn)  # segunda vez não deve falhar
    finally:
        await close_pool()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.14 -m pytest tests/test_database.py -v`
Expected: FAIL (ImportError: `connect_pool` não existe).

- [ ] **Step 3: Write minimal implementation**

```python
# backend/database.py
import os
from typing import AsyncGenerator, Optional
import asyncpg

_pool: Optional[asyncpg.Pool] = None


async def connect_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.environ["SUPABASE_DB_URL"],
            ssl="require",
            min_size=1,
            max_size=5,
            statement_cache_size=0,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool não inicializado")
    return _pool


async def init_db(conn: asyncpg.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name           TEXT NOT NULL,
            email          TEXT UNIQUE NOT NULL,
            password_hash  TEXT,
            google_id      TEXT,
            my_language    TEXT DEFAULT 'pt',
            other_language TEXT DEFAULT 'en',
            drive_folder   TEXT NOT NULL DEFAULT '',
            created_at     TIMESTAMPTZ DEFAULT now()
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id         BIGINT REFERENCES users(id),
            started_at      TIMESTAMPTZ NOT NULL,
            ended_at        TIMESTAMPTZ,
            audio_path      TEXT,
            transcript_path TEXT,
            pdf_path        TEXT,
            summary         TEXT
        )
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversations_user_id "
        "ON conversations(user_id)"
    )


async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    async with get_pool().acquire() as conn:
        yield conn
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.14 -m pytest tests/test_database.py -v`
Expected: PASS (2 passed) — cria as tabelas no Supabase real.

- [ ] **Step 5: Commit**

```bash
git add backend/database.py tests/test_database.py
git commit -m "feat: asyncpg pool and Postgres schema for Supabase (users, conversations)"
```

---

### Task 2: Portar queries de `auth_router.py` para asyncpg

**Files:**
- Modify: `backend/routers/auth_router.py`
- Test: `tests/test_auth_router.py` (novo — integração contra Supabase)

**Interfaces:**
- Consumes: `get_db` (Task 1) — agora entrega `asyncpg.Connection`.
- Produces: endpoints `register`, `login`, `me`, `google_callback` funcionando sobre Postgres.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth_router.py
import os
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv()
pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_DB_URL"), reason="SUPABASE_DB_URL não configurada"
)


@pytest.fixture(scope="module")
def client():
    import backend.main as main
    with TestClient(main.app) as c:  # dispara lifespan (cria pool + tabelas)
        yield c


def test_register_login_me_flow(client):
    import uuid
    email = f"pytest_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "password": "senha12345", "name": "Pytest"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == email

    r = client.post("/auth/login", json={"email": email, "password": "senha12345"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert token

    r = client.get(f"/auth/me?token={token}")
    assert r.status_code == 200, r.text
    assert r.json()["email"] == email


def test_register_duplicate_email_rejected(client):
    import uuid
    email = f"pytest_{uuid.uuid4().hex[:8]}@example.com"
    payload = {"email": email, "password": "senha12345", "name": "Dup"}
    assert client.post("/auth/register", json=payload).status_code == 200
    assert client.post("/auth/register", json=payload).status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.14 -m pytest tests/test_auth_router.py -v`
Expected: FAIL (queries ainda usam sintaxe SQLite `?`/`lastrowid` → erro asyncpg, ou o lifespan ainda usa aiosqlite — falha até Task 3; ESTA falha é esperada agora).

> Nota para o implementer: os testes de Task 2 dependem do lifespan novo (Task 3) para o pool existir via TestClient. Se este teste não passar isoladamente por causa do lifespan antigo, implemente as queries desta task, confirme que o arquivo importa sem erro, e deixe o teste verde após Task 3. Marque como DONE_WITH_CONCERNS se o verde depender de Task 3, anotando isso.

- [ ] **Step 3: Write minimal implementation**

Substituir o corpo das funções em `backend/routers/auth_router.py` (manter imports de modelos/auth; trocar `import aiosqlite` por `import asyncpg`):

```python
# register
@router.post("/register", response_model=UserOut)
async def register(user: UserCreate, db: asyncpg.Connection = Depends(get_db)):
    existing = await db.fetchrow("SELECT id FROM users WHERE email = $1", user.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    user_id = await db.fetchval(
        "INSERT INTO users (name, email, password_hash, my_language, other_language, drive_folder) "
        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
        user.name, user.email, hash_password(user.password),
        "pt", "en", "",
    )
    row = await db.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    return dict(row)


# login
@router.post("/login")
async def login(credentials: UserLogin, db: asyncpg.Connection = Depends(get_db)):
    row = await db.fetchrow("SELECT * FROM users WHERE email = $1", credentials.email)
    if not row or not row["password_hash"] or not verify_password(credentials.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    token = create_access_token({"sub": str(row["id"]), "email": row["email"]})
    return {"access_token": token, "token_type": "bearer"}


# me
@router.get("/me", response_model=UserOut)
async def me(token: str = Query(...), db: asyncpg.Connection = Depends(get_db)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido")
    row = await db.fetchrow("SELECT * FROM users WHERE id = $1", int(payload["sub"]))
    if not row:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return dict(row)
```

E em `google_callback`, trocar o bloco de DB por:

```python
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
```

> Preserve a lógica/estrutura existente de `google_callback` ao redor (extração de `google_id`, `email`, `name`, criação do token e redirect). Apenas troque as chamadas de banco e remova `await db.commit()`. Confirme os nomes reais de `UserOut`/`UserCreate`/`UserLogin` no arquivo; se `response_model` já existir, mantenha. Se o retorno antigo usava `dict(row)` de `aiosqlite.Row`, `dict(asyncpg.Record)` também funciona.

- [ ] **Step 4: Run test (pode depender de Task 3 para o pool)**

Run: `py -3.14 -m pytest tests/test_auth_router.py -v`
Expected: PASS após Task 3 (lifespan cria o pool). Se ainda falhar só por causa do lifespan antigo, confirme `py -3.14 -c "import backend.routers.auth_router"` sem erro e prossiga (verde garantido na Task 3).

- [ ] **Step 5: Commit**

```bash
git add backend/routers/auth_router.py tests/test_auth_router.py
git commit -m "feat: port auth router queries to asyncpg/Postgres"
```

---

### Task 3: Atualizar `main.py` (lifespan + pool + queries + conversations)

**Files:**
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: `connect_pool`, `close_pool`, `get_pool`, `init_db`, `get_db` (Task 1); `auth_router` portado (Task 2).
- Produces: app inicializa o pool no startup; WS e `end_meeting` usam Postgres; tabela `conversations`.

- [ ] **Step 1: Write the failing test (reuso do health do auth_router)**

Não há teste novo nesta task; ela é validada pela passagem de `tests/test_auth_router.py` (Task 2) e `tests/test_database.py` (Task 1) via o lifespan, mais um import check.

Run agora (deve falhar enquanto o lifespan usa aiosqlite):
`py -3.14 -m pytest tests/test_auth_router.py -v`
Expected: FAIL antes desta task; PASS depois.

- [ ] **Step 2: Implement — lifespan e pool**

Trocar imports e o `lifespan` em `backend/main.py`:

```python
# remover: import aiosqlite
from backend.database import connect_pool, close_pool, get_pool, init_db, get_db
import asyncpg

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_pool()
    async with get_pool().acquire() as conn:
        await init_db(conn)
    yield
    await close_pool()
```

- [ ] **Step 3: Implement — query do WebSocket**

No bloco `start` do WebSocket, trocar a leitura do usuário:

```python
                async with get_pool().acquire() as conn:
                    row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
                other_lang = data.get("other_language", row["other_language"] if row else "en")
```

(Manter o restante do plumbing de dispositivos da Fase 1 igual.)

- [ ] **Step 4: Implement — `end_meeting` para conversations**

Trocar a assinatura/uso do `db` e o INSERT:

```python
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
```

> Nota: `started_at` é um `datetime` Python; asyncpg aceita `datetime` direto para `TIMESTAMPTZ` (não usar `.isoformat()`).

- [ ] **Step 5: Run tests + import check**

Run: `py -3.14 -c "import backend.main"` → sucesso.
Run: `py -3.14 -m pytest tests/test_database.py tests/test_auth_router.py tests/test_auth.py -v`
Expected: todos PASS (integração contra Supabase real).

- [ ] **Step 6: Commit**

```bash
git add backend/main.py
git commit -m "feat: main app lifespan pool, WS and end_meeting on Postgres/conversations"
```

---

### Task 4: Limpeza de dependências + verificação final da suíte

**Files:**
- Modify: `requirements.txt`

**Interfaces:** nenhuma nova.

- [ ] **Step 1: Atualizar requirements.txt**

Adicionar `asyncpg==0.31.0`; remover a linha `aiosqlite==0.20.0`.

- [ ] **Step 2: Garantir que nada mais importa aiosqlite**

Run: `py -3.14 -m pip uninstall -y aiosqlite` e depois rodar a suíte completa:
`py -3.14 -m pytest -q`
Expected: tudo verde sem `aiosqlite` instalado (prova que a migração está completa). Se algum import quebrar, há referência residual a aiosqlite — corrigir.

- [ ] **Step 3: Smoke manual contra Supabase**

Run: `py -3.14 -c "import asyncio,os; from dotenv import load_dotenv; load_dotenv(); from backend.database import connect_pool, get_pool, init_db, close_pool; asyncio.run((lambda: __import__('asyncio').get_event_loop())())" 2>&1 | head -1` (apenas confirmação de import).
Run (server): `py -3.14 -m uvicorn backend.main:app --port 8021` → deve subir com "Application startup complete"; `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8021/auth/me?token=x` retorna 401 (rota viva). Parar o server.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: pin asyncpg, drop aiosqlite after Supabase migration"
```

---

## Self-Review

**Spec coverage (design seção 7):**
- asyncpg + pool no lifespan → Task 1, 3. ✅
- DSN via .env, Session Pooler, ssl require → Global Constraints + Task 1. ✅
- DDL Postgres (IDENTITY, TIMESTAMPTZ) → Task 1. ✅
- Placeholders `$1`, RETURNING id, fetch/fetchrow/execute, sem commit → Tasks 2, 3. ✅
- meetings → conversations → Task 1 (DDL) + Task 3 (insert). ✅
- Começar do zero (sem migração de dados) → não há task de migração. ✅
- Remover aiosqlite → Task 4. ✅

**Placeholder scan:** sem TBD; código real em cada passo. As notas de dependência entre Task 2 (verde) e Task 3 (lifespan) estão explicitadas, não são placeholders.

**Type consistency:** `connect_pool/close_pool/get_pool/init_db/get_db` consistentes entre Tasks 1, 2, 3. `asyncpg.Connection` em todos os `Depends(get_db)`. `conversations` consistente entre Task 1 (DDL) e Task 3 (insert).

**Risco conhecido:** os testes de DB/auth são de integração (Supabase real) — exigem `SUPABASE_DB_URL` e internet; ficam `skip` se ausente. Anotado nos Global Constraints.
