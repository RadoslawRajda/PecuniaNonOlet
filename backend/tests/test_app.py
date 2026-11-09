import sqlite3

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.admin import create_analyst
from app.authorization import require_roles
from app.main import app
from app.schemas import User


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


def test_user_role_is_default_and_cannot_be_selected_by_registration(client, tmp_path):
    registered = client.post(
        "/api/register",
        json={"email": "role@example.com", "password": "test12345", "role": "analyst"},
    )
    assert registered.status_code == 422
    registered = client.post(
        "/api/register", json={"email": "role@example.com", "password": "test12345"}
    )
    assert registered.status_code == 201
    assert registered.json()["user"]["role"] == "user"
    token = registered.json()["token"]
    assert client.get("/api/me", headers=auth(token)).json() == {
        "id": registered.json()["user"]["id"],
        "email": "role@example.com",
        "role": "user",
    }
    with sqlite3.connect(tmp_path / "test.db") as db:
        assert db.execute(
            "SELECT role_name FROM user_roles WHERE user_id = ?",
            (registered.json()["user"]["id"],),
        ).fetchone() == ("user",)


def test_analyst_accounts_are_created_by_trusted_local_process(client, tmp_path):
    analyst_id = create_analyst("analyst@example.com", "analyst-password")
    with sqlite3.connect(tmp_path / "test.db") as db:
        assert db.execute("SELECT role_name FROM user_roles WHERE user_id = ?", (analyst_id,)).fetchone() == ("analyst",)
    logged_in = client.post(
        "/api/login", json={"email": "analyst@example.com", "password": "analyst-password"}
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["role"] == "analyst"
    assert client.get("/api/me", headers=auth(logged_in.json()["token"])).json()["role"] == "analyst"


def test_role_dependency_denies_users_from_analyst_operations():
    user = User(id=1, email="user@example.com", role="user")
    analyst = User(id=2, email="analyst@example.com", role="analyst")
    assert require_roles("user")(("token", user)) == user
    with pytest.raises(HTTPException) as error:
        require_roles("analyst")(("token", user))
    assert getattr(error.value, "status_code", None) == 403
    assert require_roles("analyst")(("token", analyst)) == analyst


def test_analyst_creation_rejects_invalid_password_and_duplicate_email(client):
    with pytest.raises(ValueError):
        create_analyst("weak@example.com", "short")
    create_analyst("existing@example.com", "password-123")
    with pytest.raises(ValueError, match="już istnieje"):
        create_analyst("existing@example.com", "password-123")
