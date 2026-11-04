import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LAN_IP", "192.168.1.45")
    with TestClient(app) as test_client:
        yield test_client


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_diagnostics_and_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    page = client.get("/")
    assert page.status_code == 200
    assert "192.168.1.45" in page.text
    assert "_pecunianonolet._tcp.local." in page.text
    assert "SQLite" in page.text
    assert "<style" not in page.text


def test_register_login_logout_and_persistence(client, tmp_path):
    payload = {"email": "TEST@example.com", "password": "test12345"}
    registered = client.post("/api/register", json=payload)
    assert registered.status_code == 201
    body = registered.json()
    assert body["user"]["email"] == "test@example.com"
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 7 * 24 * 60 * 60
    token = body["token"]
    assert client.get("/api/me", headers=auth(token)).json() == body["user"]

    with sqlite3.connect(tmp_path / "test.db") as db:
        user = db.execute("SELECT password_hash FROM users").fetchone()[0]
        saved_token = db.execute("SELECT token_hash FROM sessions").fetchone()[0]
    assert user != payload["password"]
    assert saved_token != token

    assert client.post("/api/register", json=payload).status_code == 409
    assert client.post("/api/login", json={**payload, "password": "wrongpass"}).status_code == 401
    logged_in = client.post("/api/login", json=payload)
    assert logged_in.status_code == 200
    other_token = logged_in.json()["token"]
    assert other_token != token

    assert client.post("/api/logout", headers=auth(token)).status_code == 204
    assert client.get("/api/me", headers=auth(token)).status_code == 401
    assert client.get("/api/me", headers=auth(other_token)).status_code == 200


def test_missing_expired_and_invalid_token(client, tmp_path):
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/logout").status_code == 401
    assert client.get("/api/me", headers=auth("invalid")).status_code == 401

    token = client.post(
        "/api/register", json={"email": "user@example.com", "password": "test12345"}
    ).json()["token"]
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.execute("UPDATE sessions SET expires_at = 1")
    assert client.get("/api/me", headers=auth(token)).status_code == 401


def test_registration_validation(client):
    for payload in (
        {"email": "not-an-email", "password": "test12345"},
        {"email": "ok@example.com", "password": "short"},
    ):
        assert client.post("/api/register", json=payload).status_code == 422
