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
