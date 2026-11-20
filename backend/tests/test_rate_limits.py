import pytest
from app.database import connect_db
from app.main import app
from app.rate_limits import enforce_rate_limit
from app.routes import auth as auth_routes
from fastapi import HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "rate-limits.db"))
    with TestClient(app) as test_client:
        yield test_client


def test_rate_limit_is_shared_by_database_connections_and_expires(client):
    enforce_rate_limit(["auth:test:ip:192.0.2.1"], limits=[2], window_seconds=60, now=100)
    enforce_rate_limit(["auth:test:ip:192.0.2.1"], limits=[2], window_seconds=60, now=101)

    with pytest.raises(HTTPException) as limited:
        enforce_rate_limit(["auth:test:ip:192.0.2.1"], limits=[2], window_seconds=60, now=102)
    assert limited.value.status_code == 429
    assert limited.value.headers["Retry-After"] == "58"
    with connect_db() as db:
        assert db.execute("SELECT attempts FROM auth_rate_limits").fetchone()[0] == 2

    enforce_rate_limit(["auth:test:ip:192.0.2.1"], limits=[2], window_seconds=60, now=160)
    with connect_db() as db:
        assert db.execute("SELECT attempts FROM auth_rate_limits").fetchone()[0] == 1


def test_rate_limit_commits_ip_bucket_when_identity_bucket_is_exhausted(client):
    enforce_rate_limit(
        ["auth:test:ip:192.0.2.2", "auth:test:email:user@example.com"], limits=[10, 1], now=100
    )
    with pytest.raises(HTTPException):
        enforce_rate_limit(
            ["auth:test:ip:192.0.2.2", "auth:test:email:user@example.com"], limits=[10, 1], now=101
        )

    with connect_db() as db:
        attempts = dict(db.execute("SELECT bucket_hash,attempts FROM auth_rate_limits").fetchall())
        assert sorted(attempts.values()) == [1, 2]


def test_password_login_stops_before_password_verification_after_limit(client, monkeypatch):
    verifications = 0

    def fake_verify(_password, _password_hash):
        nonlocal verifications
        verifications += 1
        return False

    monkeypatch.setattr(auth_routes.password_hasher, "verify", fake_verify)
    payload = {"email": "absent@example.com", "password": "not-a-valid-login"}
    for _ in range(10):
        assert client.post("/api/login", json=payload).status_code == 401

    limited = client.post("/api/login", json=payload)
    assert limited.status_code == 429
    assert limited.headers["Retry-After"]
    assert verifications == 10
