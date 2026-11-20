import json
import sqlite3

import pytest
from app.main import app
from app.request_limits import (
    MAX_AUTH_REQUEST_BYTES,
    MAX_GENERAL_REQUEST_BYTES,
    MAX_WEBAUTHN_REQUEST_BYTES,
    RequestBodyLimitMiddleware,
)
from fastapi.testclient import TestClient


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "request-limits.db"))
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    ("path", "size"),
    [
        ("/api/passkeys/authentication/verify", MAX_WEBAUTHN_REQUEST_BYTES + 1),
        ("/api/auth/google/login", 10 * 1024 + 1),
        ("/api/login", MAX_AUTH_REQUEST_BYTES + 1),
        ("/api/transfers", MAX_GENERAL_REQUEST_BYTES + 1),
    ],
)
def test_auth_endpoints_reject_oversized_content_length(client, path, size):
    response = client.post(path, content=b"x" * size, headers={"Content-Type": "application/json"})
    assert response.status_code == 413


@pytest.mark.anyio
async def test_auth_body_limit_counts_streamed_chunks_without_content_length():
    chunks = [
        {"type": "http.request", "body": b"a" * 16_000, "more_body": True},
        {"type": "http.request", "body": b"b" * 17_000, "more_body": True},
        {"type": "http.request", "body": b"unused", "more_body": False},
    ]
    received = []
    sent = []

    async def receive():
        return chunks.pop(0)

    async def send(message):
        sent.append(message)

    async def downstream(scope, body_receive, response_send):
        while True:
            event = await body_receive()
            received.append(event["type"])
            if event["type"] == "http.disconnect" or not event.get("more_body", False):
                break
        await response_send({"type": "http.response.start", "status": 400, "headers": []})
        await response_send({"type": "http.response.body", "body": b""})

    middleware = RequestBodyLimitMiddleware(downstream)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/passkeys/authentication/verify",
        "headers": [],
    }
    await middleware(scope, receive, send)

    starts = [message for message in sent if message["type"] == "http.response.start"]
    assert len(starts) == 1
    assert starts[0]["status"] == 413
    assert received == []
    body = next(message["body"] for message in sent if message["type"] == "http.response.body")
    assert json.loads(body)["detail"]


@pytest.mark.anyio
async def test_final_oversized_chunk_does_not_register_user(client, tmp_path):
    payload = json.dumps(
        {
            "email": "oversized@example.com",
            "password": "A strong unique password 2026!",
            "captcha_token": "test-token",
        }
    ).encode()
    body = payload + b" " * (MAX_AUTH_REQUEST_BYTES + 1 - len(payload))
    events = [
        {"type": "http.request", "body": payload, "more_body": True},
        {"type": "http.request", "body": body[len(payload) :], "more_body": False},
    ]
    sent = []

    async def receive():
        return events.pop(0)

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/register",
        "raw_path": b"/api/register",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    await client.app(scope, receive, send)

    assert [event["status"] for event in sent if event["type"] == "http.response.start"] == [413]
    with sqlite3.connect(tmp_path / "request-limits.db") as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM users WHERE email=?", ("oversized@example.com",)
            ).fetchone()[0]
            == 0
        )
        assert db.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 0


def test_valid_registration_at_body_limit(client, tmp_path):
    payload = json.dumps(
        {
            "email": "boundary@example.com",
            "password": "A strong unique password 2026!",
            "captcha_token": "test-token",
        }
    ).encode()
    body = payload + b" " * (MAX_AUTH_REQUEST_BYTES - len(payload))
    response = client.post(
        "/api/register", content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 201
    with sqlite3.connect(tmp_path / "request-limits.db") as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM users WHERE email=?", ("boundary@example.com",)
            ).fetchone()[0]
            == 1
        )
