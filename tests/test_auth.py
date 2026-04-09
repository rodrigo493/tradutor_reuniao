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
