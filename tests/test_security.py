"""Tests de cifrado y hashing."""
from app.core.security import (
    hash_password, verify_password,
    encrypt_secret, decrypt_secret,
    create_access_token, create_refresh_token, decode_token,
)


def test_hash_password_diferente_cada_vez():
    h1 = hash_password("mismo-secreto")
    h2 = hash_password("mismo-secreto")
    assert h1 != h2  # bcrypt incluye salt aleatorio


def test_verify_password_correcta():
    h = hash_password("secreto123")
    assert verify_password("secreto123", h) is True


def test_verify_password_incorrecta():
    h = hash_password("real")
    assert verify_password("falso", h) is False


def test_encrypt_decrypt_roundtrip():
    original = "sk-ant-supersecreto-12345"
    cifrado = encrypt_secret(original)
    assert cifrado != original
    descifrado = decrypt_secret(cifrado)
    assert descifrado == original


def test_jwt_access_token_decode():
    token = create_access_token({"sub": "abc-123"})
    payload = decode_token(token)
    assert payload["sub"] == "abc-123"
    assert payload["type"] == "access"


def test_jwt_refresh_token_decode():
    token = create_refresh_token({"sub": "xyz"})
    payload = decode_token(token)
    assert payload["type"] == "refresh"
