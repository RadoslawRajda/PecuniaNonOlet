import hashlib
import sqlite3
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from app.accounts import initialize_user_accounts
from app.admin import create_analyst
from app.authorization import require_roles
from app.main import app
from app.schemas import User
from fastapi import HTTPException
from fastapi.testclient import TestClient


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
    assert "/local-root-ca.cer" in page.text
    assert "SHA-256" in page.text
    assert "zaufania" in page.text
    assert "VPN i urządzenia zarządzane" in page.text
    assert "https://pecunianonolet.local:8000/" in page.text
    assert "pecunianonolet.local" in page.text
    assert "https://pecunianonolet.local:8000/docs" in page.text
    assert "HTTPS — bezpieczne połączenie aplikacji" in page.text
    assert "<style" not in page.text
    assert page.headers["Cache-Control"] == "no-store"
    assert page.headers["X-Content-Type-Options"] == "nosniff"
    assert page.headers["Referrer-Policy"] == "no-referrer"
    assert page.headers["X-Frame-Options"] == "DENY"
    assert page.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert "unsafe-inline" not in page.headers["Content-Security-Policy"]
    certificate = client.get("/local-root-ca.cer")
    assert certificate.status_code == 200
    assert certificate.headers["content-type"] == "application/pkix-cert"
    assert certificate.headers["content-disposition"].endswith(
        'filename="pecunianonolet-local-root-ca.cer"'
    )
    assert certificate.content
    fingerprint = re.search(r"Odcisk SHA-256 CA:</strong><br><code>([^<]+)", page.text)
    assert fingerprint is not None
    assert fingerprint.group(1) == ":".join(
        f"{byte:02X}" for byte in hashlib.sha256(certificate.content).digest()
    )


def test_security_headers_are_applied_to_api_docs_and_https_responses(client):
    api_response = client.get("/health")
    assert api_response.headers["X-Content-Type-Options"] == "nosniff"
    assert api_response.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert "Strict-Transport-Security" not in api_response.headers

    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "Content-Security-Policy" in docs.headers
    assert "object-src 'none'" in docs.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in docs.headers["Content-Security-Policy"]

    with TestClient(app, base_url="https://pecunianonolet.local") as https_client:
        secure_response = https_client.get("/health")
    assert secure_response.headers["Strict-Transport-Security"] == (
        "max-age=31536000; includeSubDomains"
    )


def test_security_events_record_auth_and_access_failures_without_credentials(client, tmp_path):
    assert (
        client.post(
            "/api/login",
            json={"email": "unknown@example.com", "password": "do-not-log-this-password"},
        ).status_code
        == 401
    )
    registered = client.post(
        "/api/register",
        json={
            "email": "security-events@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    )
    assert registered.status_code == 201
    assert client.get("/api/accounts").status_code == 401

    with sqlite3.connect(tmp_path / "test.db") as db:
        events = db.execute(
            """SELECT event_type,outcome,authentication_method,endpoint
               FROM security_events ORDER BY id"""
        ).fetchall()
    assert ("authentication", "failure", "password", "/api/login") in events
    assert ("authentication", "success", "password", "/api/register") in events
    assert ("authorization", "failure", "bearer", "/api/accounts") in events
    assert "do-not-log-this-password" not in repr(events)


def test_local_domain_association_documents_match_development_apps(client):
    apple = client.get("/.well-known/apple-app-site-association")
    assert apple.status_code == 200
    assert apple.json() == {"webcredentials": {"apps": ["96UM85TJJ7.com.rajda.pecunianonolet"]}}
    assert apple.headers["Cache-Control"] == "no-store"

    android = client.get("/.well-known/assetlinks.json")
    assert android.status_code == 200
    assert android.json()[0]["target"]["package_name"] == "com.pecunianonolet"
    assert android.json()[0]["target"]["sha256_cert_fingerprints"]


def test_register_login_logout_and_persistence(client, tmp_path):
    payload = {"email": "TEST@example.com", "password": "violet-bridge-2026!"}
    registered = client.post("/api/register", json={**payload, "captcha_token": "test-token"})
    assert registered.status_code == 201
    assert registered.headers["Cache-Control"] == "no-store"
    body = registered.json()
    assert body["user"]["email"] == "test@example.com"
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert body["refresh_expires_in"] == 30 * 24 * 60 * 60
    token = body["access_token"]
    refresh_token = body["refresh_token"]
    assert client.get("/api/me", headers=auth(token)).json() == body["user"]
    assert client.get("/api/me", headers=auth(token)).headers["Cache-Control"] == "no-store"

    with sqlite3.connect(tmp_path / "test.db") as db:
        user = db.execute("SELECT password_hash FROM users").fetchone()[0]
        saved_token = db.execute("SELECT access_token_hash FROM auth_sessions").fetchone()[0]
    assert user != payload["password"]
    assert saved_token != token

    assert (
        client.post("/api/register", json={**payload, "captcha_token": "test-token"}).status_code
        == 409
    )
    assert client.post("/api/login", json={**payload, "password": "wrongpass"}).status_code == 401
    logged_in = client.post("/api/login", json=payload)
    assert logged_in.status_code == 200
    other_token = logged_in.json()["access_token"]
    assert other_token != token

    assert client.post("/api/logout", json={"refresh_token": refresh_token}).status_code == 204
    assert client.get("/api/me", headers=auth(token)).status_code == 401
    assert client.get("/api/me", headers=auth(other_token)).status_code == 200


def test_refresh_rotates_both_tokens_and_replay_revokes_the_session_family(client):
    registered = client.post(
        "/api/register",
        json={
            "email": "refresh@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    original_access = registered["access_token"]
    original_refresh = registered["refresh_token"]

    refreshed = client.post("/api/refresh", json={"refresh_token": original_refresh})
    assert refreshed.status_code == 200
    rotated = refreshed.json()
    assert rotated["access_token"] != original_access
    assert rotated["refresh_token"] != original_refresh
    assert rotated["expires_in"] == 15 * 60
    assert rotated["refresh_expires_in"] <= 30 * 24 * 60 * 60
    assert client.get("/api/me", headers=auth(original_access)).status_code == 401
    assert client.get("/api/me", headers=auth(rotated["access_token"])).status_code == 200

    replay = client.post("/api/refresh", json={"refresh_token": original_refresh})
    assert replay.status_code == 401
    assert client.get("/api/me", headers=auth(rotated["access_token"])).status_code == 401


def test_refresh_rejects_expired_token_and_logout_revokes_rotated_family(client, tmp_path):
    registered = client.post(
        "/api/register",
        json={
            "email": "logout@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    rotated = client.post(
        "/api/refresh", json={"refresh_token": registered["refresh_token"]}
    ).json()
    assert (
        client.post("/api/logout", json={"refresh_token": rotated["refresh_token"]}).status_code
        == 204
    )
    assert client.get("/api/me", headers=auth(rotated["access_token"])).status_code == 401
    assert (
        client.post("/api/logout", json={"refresh_token": rotated["refresh_token"]}).status_code
        == 204
    )

    expired = client.post(
        "/api/register",
        json={
            "email": "expired-refresh@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.execute(
            "UPDATE auth_sessions SET access_expires_at=1,refresh_expires_at=1,absolute_expires_at=1 "
            "WHERE refresh_token_hash != ''"
        )
    assert (
        client.post("/api/refresh", json={"refresh_token": expired["refresh_token"]}).status_code
        == 401
    )


def test_sessions_can_be_listed_and_other_sessions_revoked_after_recent_auth(client):
    credentials = {"email": "session-list@example.com", "password": "violet-bridge-2026!"}
    first = client.post("/api/register", json={**credentials, "captcha_token": "test-token"}).json()
    second = client.post("/api/login", json=credentials).json()
    first_auth = auth(first["access_token"])

    listed = client.get("/api/sessions", headers=first_auth)
    assert listed.status_code == 200
    assert len(listed.json()["sessions"]) == 2
    assert sum(item["current"] for item in listed.json()["sessions"]) == 1
    assert listed.headers["Cache-Control"] == "no-store"
    second_session_id = next(
        item["session_id"] for item in listed.json()["sessions"] if not item["current"]
    )

    revoked = client.delete(f"/api/sessions/{second_session_id}", headers=first_auth)
    assert revoked.status_code == 204
    assert client.get("/api/me", headers=auth(second["access_token"])).status_code == 401
    assert client.get("/api/me", headers=first_auth).status_code == 200

    client.post("/api/login", json=credentials)
    revoke_response = client.post("/api/sessions/revoke-others", headers=first_auth)
    assert revoke_response.status_code == 200
    assert revoke_response.json()["revoked_count"] == 1
    assert len(client.get("/api/sessions", headers=first_auth).json()["sessions"]) == 1


def test_session_revocation_requires_recent_authentication_and_is_owner_scoped(client, tmp_path):
    first = client.post(
        "/api/register",
        json={
            "email": "session-owner@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    other = client.post(
        "/api/register",
        json={
            "email": "session-other@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    other_session_id = client.get("/api/sessions", headers=auth(other["access_token"])).json()[
        "current_session_id"
    ]
    first_session_id = client.get("/api/sessions", headers=auth(first["access_token"])).json()[
        "current_session_id"
    ]

    # A fresh session cannot revoke another user's session or use IDs as an oracle.
    response = client.delete(
        f"/api/sessions/{other_session_id}", headers=auth(first["access_token"])
    )
    assert response.status_code == 404
    assert client.get("/api/me", headers=auth(other["access_token"])).status_code == 200

    with sqlite3.connect(tmp_path / "test.db") as db:
        db.execute(
            "UPDATE auth_sessions SET authenticated_at=1 WHERE session_id=?",
            (first_session_id,),
        )

    response = client.delete(
        f"/api/sessions/{other_session_id}", headers=auth(first["access_token"])
    )
    assert response.status_code == 401
    assert client.get("/api/me", headers=auth(other["access_token"])).status_code == 200


def test_missing_expired_and_invalid_token(client, tmp_path):
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/logout", json={}).status_code == 204
    assert client.get("/api/me", headers=auth("invalid")).status_code == 401

    token = client.post(
        "/api/register",
        json={
            "email": "user@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()["access_token"]
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.execute("UPDATE auth_sessions SET access_expires_at = 1")
    assert client.get("/api/me", headers=auth(token)).status_code == 401


def test_registration_validation(client):
    assert (
        client.request(
            "POST",
            "/api/register",
            json={"email": "ok@example.com", "password": "violet-bridge-2026!"},
        ).status_code
        == 422
    )
    for payload in (
        {"email": "not-an-email", "password": "violet-bridge-2026!"},
        {"email": "ok@example.com", "password": "short"},
    ):
        assert (
            client.post(
                "/api/register", json={**payload, "captcha_token": "test-token"}
            ).status_code
            == 422
        )


def test_password_policy_rejects_common_and_application_specific_passwords(client):
    common = client.post(
        "/api/register",
        json={
            "email": "common@example.com",
            "password": "Password!",
            "captcha_token": "test-token",
        },
    )
    contextual = client.post(
        "/api/register",
        json={
            "email": "context@example.com",
            "password": "Pecunia2026!",
            "captcha_token": "test-token",
        },
    )
    assert common.status_code == 422
    assert contextual.status_code == 422

    registered = client.post(
        "/api/register",
        json={
            "email": "change-policy@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    assert (
        client.post(
            "/api/change-password",
            headers=auth(registered["access_token"]),
            json={"current_password": "violet-bridge-2026!", "new_password": "Password!"},
        ).status_code
        == 422
    )


def test_user_role_is_default_and_cannot_be_selected_by_registration(client, tmp_path):
    registered = client.post(
        "/api/register",
        json={
            "email": "role@example.com",
            "password": "violet-bridge-2026!",
            "role": "analyst",
            "captcha_token": "test-token",
        },
    )
    assert registered.status_code == 422
    registered = client.post(
        "/api/register",
        json={
            "email": "role@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    )
    assert registered.status_code == 201
    assert registered.json()["user"]["role"] == "user"
    token = registered.json()["access_token"]
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
    analyst_id = create_analyst("analyst@example.com", "violet-bridge-2026!")
    with sqlite3.connect(tmp_path / "test.db") as db:
        assert db.execute(
            "SELECT role_name FROM user_roles WHERE user_id = ?", (analyst_id,)
        ).fetchone() == ("analyst",)
    logged_in = client.post(
        "/api/login", json={"email": "analyst@example.com", "password": "violet-bridge-2026!"}
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["role"] == "analyst"
    assert (
        client.get("/api/me", headers=auth(logged_in.json()["access_token"])).json()["role"]
        == "analyst"
    )


def test_role_dependency_denies_users_from_analyst_operations():
    from app.authorization import AuthenticatedSession
    from pydantic import SecretStr

    user = User(id=1, email="user@example.com", role="user")
    analyst = User(id=2, email="analyst@example.com", role="analyst")
    user_session = AuthenticatedSession("session-user", user, SecretStr("opaque-token"))
    analyst_session = AuthenticatedSession("session-analyst", analyst, SecretStr("opaque-token"))
    assert require_roles("user")(user_session) == user
    with pytest.raises(HTTPException) as error:
        require_roles("analyst")(user_session)
    assert getattr(error.value, "status_code", None) == 403
    assert require_roles("analyst")(analyst_session) == analyst


def test_analyst_creation_rejects_invalid_password_and_duplicate_email(client):
    with pytest.raises(ValueError):
        create_analyst("weak@example.com", "short")
    create_analyst("existing@example.com", "violet-bridge-2026!")
    with pytest.raises(ValueError, match="już istnieje"):
        create_analyst("existing@example.com", "violet-bridge-2026!")


def test_change_password_revokes_all_sessions_and_requires_reauthentication(client):
    payload = {"email": "password@example.com", "password": "violet-bridge-2026!"}
    first = client.post("/api/register", json={**payload, "captcha_token": "test-token"}).json()
    second = client.post("/api/login", json=payload).json()
    other = client.post(
        "/api/register",
        json={
            "email": "other@example.com",
            "password": "amber-river-2027#",
            "captcha_token": "test-token",
        },
    ).json()

    response = client.post(
        "/api/change-password",
        headers=auth(first["access_token"]),
        json={"current_password": "violet-bridge-2026!", "new_password": "amber-river-2027#"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "message": "Hasło zostało zmienione. Zaloguj się ponownie.",
        "reauthentication_required": True,
    }
    assert client.get("/api/me", headers=auth(first["access_token"])).status_code == 401
    assert client.get("/api/me", headers=auth(second["access_token"])).status_code == 401
    assert client.get("/api/me", headers=auth(other["access_token"])).status_code == 200
    assert client.post("/api/login", json=payload).status_code == 401
    new_login = client.post(
        "/api/login", json={"email": "password@example.com", "password": "amber-river-2027#"}
    )
    assert new_login.status_code == 200


def test_login_racing_password_change_does_not_issue_a_stale_session(client, monkeypatch):
    from app.routes import auth as auth_routes

    credentials = {"email": "racing-password@example.com", "password": "violet-bridge-2026!"}
    registered = client.post(
        "/api/register", json={**credentials, "captcha_token": "test-token"}
    ).json()
    original_hasher = auth_routes.password_hasher
    login_verified_old_hash = Event()
    resume_login = Event()

    class PausingHasher:
        def hash(self, value):
            return original_hasher.hash(value)

        def verify(self, password, password_hash):
            result = original_hasher.verify(password, password_hash)
            if password == credentials["password"] and not login_verified_old_hash.is_set():
                login_verified_old_hash.set()
                assert resume_login.wait(timeout=10)
            return result

    monkeypatch.setattr(auth_routes, "password_hasher", PausingHasher())
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending_login = executor.submit(client.post, "/api/login", json=credentials)
        assert login_verified_old_hash.wait(timeout=10)
        changed = client.post(
            "/api/change-password",
            headers=auth(registered["access_token"]),
            json={"current_password": "violet-bridge-2026!", "new_password": "amber-river-2027#"},
        )
        assert changed.status_code == 200
        resume_login.set()
        login_response = pending_login.result(timeout=10)

    assert login_response.status_code == 401
    assert (
        client.post(
            "/api/login",
            json={"email": credentials["email"], "password": "amber-river-2027#"},
        ).status_code
        == 200
    )


def test_database_write_contention_returns_retryable_503(client, tmp_path, monkeypatch):
    from app import database

    sender = client.post(
        "/api/register",
        json={
            "email": "busy-sender@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    client.post(
        "/api/register",
        json={
            "email": "busy-recipient@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    )
    monkeypatch.setattr(database, "SQLITE_BUSY_TIMEOUT_MS", 20)
    lock = sqlite3.connect(tmp_path / "test.db", timeout=1)
    try:
        lock.execute("BEGIN IMMEDIATE")
        lock.execute("UPDATE accounts SET balance_minor = balance_minor WHERE id = 1")
        response = client.post(
            "/api/transfers",
            headers={**auth(sender["access_token"]), "Idempotency-Key": "db-busy-test"},
            json={
                "recipient_email": "busy-recipient@example.com",
                "source_account_id": 1,
                "currency_code": "PLN",
                "amount_minor": 1,
            },
        )
    finally:
        lock.rollback()
        lock.close()
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"


def test_change_password_requires_session_and_current_password(client):
    assert (
        client.post(
            "/api/change-password",
            json={"current_password": "violet-bridge-2026!", "new_password": "amber-river-2027#"},
        ).status_code
        == 401
    )
    credentials = {"email": "wrong-current@example.com", "password": "violet-bridge-2026!"}
    token = client.post(
        "/api/register", json={**credentials, "captcha_token": "test-token"}
    ).json()["access_token"]
    response = client.post(
        "/api/change-password",
        headers=auth(token),
        json={"current_password": "wrong-password", "new_password": "amber-river-2027#"},
    )
    assert response.status_code == 401
    assert client.get("/api/me", headers=auth(token)).status_code == 200
    assert client.post("/api/login", json=credentials).status_code == 200


def test_change_password_validates_new_password_and_rejects_reuse(client):
    credentials = {"email": "validation@example.com", "password": "violet-bridge-2026!"}
    token = client.post(
        "/api/register", json={**credentials, "captcha_token": "test-token"}
    ).json()["access_token"]
    headers = auth(token)
    for password in ("short", "x" * 129):
        response = client.post(
            "/api/change-password",
            headers=headers,
            json={"current_password": "violet-bridge-2026!", "new_password": password},
        )
        assert response.status_code == 422
    same_password = client.post(
        "/api/change-password",
        headers=headers,
        json={"current_password": "violet-bridge-2026!", "new_password": "violet-bridge-2026!"},
    )
    assert same_password.status_code == 400
    assert client.get("/api/me", headers=headers).status_code == 200


def test_change_password_rolls_back_session_revocation_if_password_update_fails(client, tmp_path):
    credentials = {"email": "atomic@example.com", "password": "violet-bridge-2026!"}
    token = client.post(
        "/api/register", json={**credentials, "captcha_token": "test-token"}
    ).json()["access_token"]
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.execute(
            """
            CREATE TRIGGER reject_password_update BEFORE UPDATE OF password_hash ON users
            BEGIN SELECT RAISE(ABORT, 'update rejected'); END
            """
        )
    with pytest.raises(sqlite3.IntegrityError):
        client.post(
            "/api/change-password",
            headers=auth(token),
            json={"current_password": "violet-bridge-2026!", "new_password": "amber-river-2027#"},
        )
    assert client.get("/api/me", headers=auth(token)).status_code == 200
    assert client.post("/api/login", json=credentials).status_code == 200


def test_registration_creates_independent_currency_accounts_and_initial_ledger(client, tmp_path):
    response = client.post(
        "/api/register",
        json={
            "email": "accounts@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    )
    assert response.status_code == 201
    user_id = response.json()["user"]["id"]
    with sqlite3.connect(tmp_path / "test.db") as db:
        balances = dict(
            db.execute(
                "SELECT currency_code, balance_minor FROM accounts WHERE user_id = ?", (user_id,)
            ).fetchall()
        )
        assert balances == {"PLN": 100_000, "EUR": 0, "USD": 0, "GBP": 0, "CZK": 0}
        assert db.execute(
            "SELECT kind, destination_amount_minor, destination_currency_code FROM transactions WHERE sender_user_id = ?",
            (user_id,),
        ).fetchall() == [("opening", 100_000, "PLN")]
        assert db.execute(
            "SELECT amount_minor FROM ledger_entries WHERE transaction_id IN (SELECT id FROM transactions WHERE sender_user_id = ?)",
            (user_id,),
        ).fetchall() == [(100_000,)]


def test_initial_account_provisioning_is_idempotent(client, tmp_path):
    response = client.post(
        "/api/register",
        json={
            "email": "idempotent@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    )
    user_id = response.json()["user"]["id"]
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.row_factory = sqlite3.Row
        db.execute(
            "UPDATE accounts SET balance_minor = 250 WHERE user_id = ? AND currency_code = 'EUR'",
            (user_id,),
        )
        initialize_user_accounts(db, user_id, 123)
        balances = db.execute(
            "SELECT currency_code, balance_minor FROM accounts WHERE user_id = ? ORDER BY currency_code",
            (user_id,),
        ).fetchall()
        assert {row["currency_code"]: row["balance_minor"] for row in balances} == {
            "CZK": 0,
            "EUR": 250,
            "GBP": 0,
            "PLN": 100_000,
            "USD": 0,
        }
        assert (
            db.execute(
                "SELECT count(*) FROM transactions WHERE sender_user_id = ? AND idempotency_key = ?",
                (user_id, "opening-balance-pln-v1"),
            ).fetchone()[0]
            == 1
        )


def test_registration_rolls_back_user_accounts_and_grant_on_ledger_failure(client, tmp_path):
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.execute(
            """
            CREATE TRIGGER reject_opening_entry BEFORE INSERT ON ledger_entries
            BEGIN SELECT RAISE(ABORT, 'entry rejected'); END
            """
        )
    with pytest.raises(sqlite3.IntegrityError):
        client.post(
            "/api/register",
            json={
                "email": "rollback@example.com",
                "password": "violet-bridge-2026!",
                "captcha_token": "test-token",
            },
        )
    with sqlite3.connect(tmp_path / "test.db") as db:
        assert db.execute(
            "SELECT count(*) FROM users WHERE email = 'rollback@example.com'"
        ).fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM accounts").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM transactions").fetchone() == (0,)


def add_financial_transaction(
    db,
    *,
    transaction_id,
    sender_id,
    recipient_id,
    source_account,
    source_owner,
    destination_account,
    destination_owner,
    kind,
    source_currency,
    destination_currency,
    source_minor,
    destination_minor,
    exchange_rate,
    idempotency_key,
    created_at,
):
    db.execute(
        """
        INSERT INTO transactions(
            id, kind, status, sender_user_id, recipient_user_id,
            source_account_id, source_account_user_id,
            destination_account_id, destination_account_user_id,
            source_currency_code, destination_currency_code,
            source_amount_minor, destination_amount_minor, exchange_rate,
            idempotency_key, created_at
        ) VALUES (?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transaction_id,
            kind,
            sender_id,
            recipient_id,
            source_account,
            source_owner,
            destination_account,
            destination_owner,
            source_currency,
            destination_currency,
            source_minor,
            destination_minor,
            exchange_rate,
            idempotency_key,
            created_at,
        ),
    )
    if source_account is not None:
        db.execute(
            "INSERT INTO ledger_entries(transaction_id, account_id, account_user_id, amount_minor, created_at) VALUES (?, ?, ?, ?, ?)",
            (transaction_id, source_account, source_owner, -source_minor, created_at),
        )
    db.execute(
        "INSERT INTO ledger_entries(transaction_id, account_id, account_user_id, amount_minor, created_at) VALUES (?, ?, ?, ?, ?)",
        (transaction_id, destination_account, destination_owner, destination_minor, created_at),
    )


def test_accounts_endpoint_returns_each_currency_for_the_authenticated_owner(client):
    first = client.post(
        "/api/register",
        json={
            "email": "first-account@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    second = client.post(
        "/api/register",
        json={
            "email": "second-account@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    first_response = client.get("/api/accounts", headers=auth(first["access_token"]))
    assert first_response.status_code == 200
    accounts = first_response.json()["accounts"]
    assert {row["currency_code"]: row["balance"] for row in accounts} == {
        "PLN": "1000.00",
        "EUR": "0.00",
        "USD": "0.00",
        "GBP": "0.00",
        "CZK": "0.00",
    }
    assert all(isinstance(row["balance_minor"], int) for row in accounts)
    second_account_ids = {
        row["id"]
        for row in client.get("/api/accounts", headers=auth(second["access_token"])).json()[
            "accounts"
        ]
    }
    assert not ({row["id"] for row in accounts} & second_account_ids)
    assert client.get("/api/accounts").status_code == 401
    analyst_id = create_analyst("read-only-analyst@example.com", "violet-bridge-2026!")
    assert analyst_id > 0
    analyst_login = client.post(
        "/api/login",
        json={"email": "read-only-analyst@example.com", "password": "violet-bridge-2026!"},
    ).json()
    assert (
        client.get("/api/accounts", headers=auth(analyst_login["access_token"])).status_code == 403
    )


def test_transaction_history_is_paginated_sorted_and_shows_both_transfer_sides(client, tmp_path):
    sender = client.post(
        "/api/register",
        json={
            "email": "sender@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    recipient = client.post(
        "/api/register",
        json={
            "email": "recipient@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    sender_id = sender["user"]["id"]
    recipient_id = recipient["user"]["id"]
    with sqlite3.connect(tmp_path / "test.db") as db:
        sender_pln = db.execute(
            "SELECT id FROM accounts WHERE user_id = ? AND currency_code = 'PLN'", (sender_id,)
        ).fetchone()[0]
        recipient_pln = db.execute(
            "SELECT id FROM accounts WHERE user_id = ? AND currency_code = 'PLN'", (recipient_id,)
        ).fetchone()[0]
        sender_eur = db.execute(
            "SELECT id FROM accounts WHERE user_id = ? AND currency_code = 'EUR'", (sender_id,)
        ).fetchone()[0]
        created_at = 2_000_000_000
        add_financial_transaction(
            db,
            transaction_id="transfer-a",
            sender_id=sender_id,
            recipient_id=recipient_id,
            source_account=sender_pln,
            source_owner=sender_id,
            destination_account=recipient_pln,
            destination_owner=recipient_id,
            kind="transfer",
            source_currency="PLN",
            destination_currency="PLN",
            source_minor=1_000,
            destination_minor=1_000,
            exchange_rate=None,
            idempotency_key="transfer-a",
            created_at=created_at,
        )
        add_financial_transaction(
            db,
            transaction_id="transfer-z",
            sender_id=sender_id,
            recipient_id=recipient_id,
            source_account=sender_pln,
            source_owner=sender_id,
            destination_account=recipient_pln,
            destination_owner=recipient_id,
            kind="transfer",
            source_currency="PLN",
            destination_currency="PLN",
            source_minor=500,
            destination_minor=500,
            exchange_rate=None,
            idempotency_key="transfer-z",
            created_at=created_at,
        )
        add_financial_transaction(
            db,
            transaction_id="exchange-1",
            sender_id=sender_id,
            recipient_id=None,
            source_account=sender_pln,
            source_owner=sender_id,
            destination_account=sender_eur,
            destination_owner=sender_id,
            kind="exchange",
            source_currency="PLN",
            destination_currency="EUR",
            source_minor=2_500,
            destination_minor=610,
            exchange_rate="0.2440000000000000001",
            idempotency_key="exchange-1",
            created_at=created_at + 1,
        )

    first_page = client.get(
        "/api/transactions?limit=2&offset=0", headers=auth(sender["access_token"])
    ).json()
    assert first_page["total"] == 4
    assert [item["id"] for item in first_page["transactions"]] == ["exchange-1", "transfer-z"]
    exchange = first_page["transactions"][0]
    assert exchange["direction"] == "internal"
    assert exchange["currency_code"] == "PLN"
    assert exchange["amount"] == "25.00"
    assert exchange["source_amount"] == "25.00"
    assert exchange["destination_amount"] == "6.10"
    assert exchange["exchange_rate"] == "0.2440000000000000001"
    transfer = first_page["transactions"][1]
    assert transfer["direction"] == "outgoing"
    assert transfer["amount"] == "5.00"
    assert transfer["counterparty_email"] == "recipient@example.com"
    assert transfer["source_account_id"] == sender_pln
    assert transfer["destination_account_id"] == recipient_pln
    assert transfer["created_at"].endswith("Z")

    second_page = client.get(
        "/api/transactions?limit=2&offset=2", headers=auth(sender["access_token"])
    ).json()
    assert second_page["transactions"][0]["id"] == "transfer-a"
    assert second_page["transactions"][1]["type"] == "opening"
    incoming = client.get("/api/transactions", headers=auth(recipient["access_token"])).json()
    transfer_records = [item for item in incoming["transactions"] if item["type"] == "transfer"]
    assert len(transfer_records) == 2
    assert all(item["direction"] == "incoming" for item in transfer_records)
    assert all(item["counterparty_email"] == "sender@example.com" for item in transfer_records)
    assert (
        client.get(
            f"/api/transactions/{incoming['transactions'][-1]['id']}",
            headers=auth(sender["access_token"]),
        ).status_code
        == 404
    )


def test_transaction_details_are_owner_scoped_and_pagination_is_validated(client, tmp_path):
    sender = client.post(
        "/api/register",
        json={
            "email": "detail-sender@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    recipient = client.post(
        "/api/register",
        json={
            "email": "detail-recipient@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    sender_id, recipient_id = sender["user"]["id"], recipient["user"]["id"]
    with sqlite3.connect(tmp_path / "test.db") as db:
        sender_account = db.execute(
            "SELECT id FROM accounts WHERE user_id = ? AND currency_code = 'EUR'", (sender_id,)
        ).fetchone()[0]
        recipient_account = db.execute(
            "SELECT id FROM accounts WHERE user_id = ? AND currency_code = 'EUR'", (recipient_id,)
        ).fetchone()[0]
        add_financial_transaction(
            db,
            transaction_id="visible-transfer",
            sender_id=sender_id,
            recipient_id=recipient_id,
            source_account=sender_account,
            source_owner=sender_id,
            destination_account=recipient_account,
            destination_owner=recipient_id,
            kind="transfer",
            source_currency="EUR",
            destination_currency="EUR",
            source_minor=2_000,
            destination_minor=2_000,
            exchange_rate=None,
            idempotency_key="visible-transfer",
            created_at=123,
        )
    detail = client.get(
        "/api/transactions/visible-transfer", headers=auth(recipient["access_token"])
    )
    assert detail.status_code == 200
    assert detail.json()["direction"] == "incoming"
    assert detail.json()["amount"] == "20.00"
    assert (
        client.get(
            "/api/transactions/visible-transfer", headers=auth(sender["access_token"])
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/transactions/{sender['user']['id']}", headers=auth(recipient["access_token"])
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/api/transactions", headers=auth(sender["access_token"]), params={"limit": 101}
        ).status_code
        == 422
    )
    assert (
        client.get("/api/transactions?offset=-1", headers=auth(sender["access_token"])).status_code
        == 422
    )


def test_transfer_moves_same_currency_atomically_and_replays_idempotently(client, tmp_path):
    sender = client.post(
        "/api/register",
        json={
            "email": "transfer-sender@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    recipient = client.post(
        "/api/register",
        json={
            "email": "transfer-recipient@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    source_id = next(
        account["id"]
        for account in client.get("/api/accounts", headers=auth(sender["access_token"])).json()[
            "accounts"
        ]
        if account["currency_code"] == "PLN"
    )
    payload = {
        "recipient_email": "TRANSFER-RECIPIENT@example.com",
        "source_account_id": source_id,
        "currency_code": "PLN",
        "amount_minor": 2_000,
    }
    headers = {**auth(sender["access_token"]), "Idempotency-Key": "transfer-request-001"}
    response = client.post("/api/transfers", headers=headers, json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["amount"] == "20.00"
    assert body["amount_minor"] == 2_000
    assert body["recipient_email"] == "transfer-recipient@example.com"
    assert body["idempotent_replay"] is False

    sender_accounts = client.get("/api/accounts", headers=auth(sender["access_token"])).json()[
        "accounts"
    ]
    recipient_accounts = client.get(
        "/api/accounts", headers=auth(recipient["access_token"])
    ).json()["accounts"]
    assert (
        next(a["balance_minor"] for a in sender_accounts if a["currency_code"] == "PLN") == 98_000
    )
    assert (
        next(a["balance_minor"] for a in recipient_accounts if a["currency_code"] == "PLN")
        == 102_000
    )

    replay = client.post("/api/transfers", headers=headers, json=payload)
    assert replay.status_code == 201
    assert replay.json()["transaction_id"] == body["transaction_id"]
    assert replay.json()["idempotent_replay"] is True
    changed_request = client.post(
        "/api/transfers", headers=headers, json={**payload, "amount_minor": 2_001}
    )
    assert changed_request.status_code == 409
    with sqlite3.connect(tmp_path / "test.db") as db:
        assert db.execute(
            "SELECT count(*) FROM ledger_entries WHERE transaction_id = ?",
            (body["transaction_id"],),
        ).fetchone() == (2,)
        entries = db.execute(
            "SELECT amount_minor FROM ledger_entries WHERE transaction_id = ? ORDER BY amount_minor",
            (body["transaction_id"],),
        ).fetchall()
        assert entries == [(-2_000,), (2_000,)]
        assert sum(row[0] for row in entries) == 0

    sender_history = client.get("/api/transactions", headers=auth(sender["access_token"])).json()
    recipient_history = client.get(
        "/api/transactions", headers=auth(recipient["access_token"])
    ).json()
    sent = next(
        item for item in sender_history["transactions"] if item["id"] == body["transaction_id"]
    )
    received = next(
        item for item in recipient_history["transactions"] if item["id"] == body["transaction_id"]
    )
    assert sent["direction"] == "outgoing"
    assert received["direction"] == "incoming"


def test_transfer_rejects_invalid_targets_currency_and_insufficient_funds(client):
    sender = client.post(
        "/api/register",
        json={
            "email": "validation-sender@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    recipient = client.post(
        "/api/register",
        json={
            "email": "validation-recipient@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    sender_accounts = client.get("/api/accounts", headers=auth(sender["access_token"])).json()[
        "accounts"
    ]
    recipient_accounts = client.get(
        "/api/accounts", headers=auth(recipient["access_token"])
    ).json()["accounts"]
    pln_id = next(a["id"] for a in sender_accounts if a["currency_code"] == "PLN")
    eur_id = next(a["id"] for a in sender_accounts if a["currency_code"] == "EUR")
    recipient_pln_id = next(a["id"] for a in recipient_accounts if a["currency_code"] == "PLN")
    headers = auth(sender["access_token"])
    valid = {
        "recipient_email": "validation-recipient@example.com",
        "source_account_id": pln_id,
        "currency_code": "PLN",
        "amount_minor": 100,
    }
    assert client.post("/api/transfers", headers=headers, json=valid).status_code == 422
    assert (
        client.post(
            "/api/transfers",
            headers={**headers, "Idempotency-Key": "self"},
            json={**valid, "recipient_email": "validation-sender@example.com"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/transfers",
            headers={**headers, "Idempotency-Key": "missing"},
            json={**valid, "recipient_email": "nobody@example.com"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/transfers",
            headers={**headers, "Idempotency-Key": "foreign-account"},
            json={**valid, "source_account_id": recipient_pln_id},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/transfers",
            headers={**headers, "Idempotency-Key": "currency-mismatch"},
            json={**valid, "currency_code": "EUR"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/transfers",
            headers={**headers, "Idempotency-Key": "invalid-currency"},
            json={**valid, "currency_code": "CAD"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/transfers",
            headers={**headers, "Idempotency-Key": "negative"},
            json={**valid, "amount_minor": -1},
        ).status_code
        == 422
    )
    no_eur_fallback = client.post(
        "/api/transfers",
        headers={**headers, "Idempotency-Key": "no-fallback"},
        json={**valid, "source_account_id": eur_id, "currency_code": "EUR", "amount_minor": 1},
    )
    assert no_eur_fallback.status_code == 409
    after = client.get("/api/accounts", headers=headers).json()["accounts"]
    assert next(a["balance_minor"] for a in after if a["currency_code"] == "PLN") == 100_000
    analyst_id = create_analyst("transfer-analyst@example.com", "violet-bridge-2026!")
    assert analyst_id > 0
    analyst = client.post(
        "/api/login",
        json={"email": "transfer-analyst@example.com", "password": "violet-bridge-2026!"},
    ).json()
    assert (
        client.post(
            "/api/transfers",
            headers={**auth(analyst["access_token"]), "Idempotency-Key": "analyst"},
            json=valid,
        ).status_code
        == 403
    )


def test_transfer_rejects_recipient_balance_overflow(client, tmp_path):
    sender = client.post(
        "/api/register",
        json={
            "email": "overflow-sender@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    recipient = client.post(
        "/api/register",
        json={
            "email": "overflow-recipient@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    source_id = next(
        a["id"]
        for a in client.get("/api/accounts", headers=auth(sender["access_token"])).json()[
            "accounts"
        ]
        if a["currency_code"] == "PLN"
    )
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.execute(
            "UPDATE accounts SET balance_minor = 9000000000000000 WHERE user_id = ? AND currency_code = 'PLN'",
            (recipient["user"]["id"],),
        )
    response = client.post(
        "/api/transfers",
        headers={**auth(sender["access_token"]), "Idempotency-Key": "overflow"},
        json={
            "recipient_email": recipient["user"]["email"],
            "source_account_id": source_id,
            "currency_code": "PLN",
            "amount_minor": 1,
        },
    )
    assert response.status_code == 409
    sender_after = client.get("/api/accounts", headers=auth(sender["access_token"])).json()[
        "accounts"
    ]
    assert next(a["balance_minor"] for a in sender_after if a["currency_code"] == "PLN") == 100_000


def test_concurrent_transfers_cannot_overdraw_source_account(client):
    sender = client.post(
        "/api/register",
        json={
            "email": "race-sender@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    recipients = [
        client.post(
            "/api/register",
            json={
                "email": f"race-{index}@example.com",
                "password": "violet-bridge-2026!",
                "captcha_token": "test-token",
            },
        ).json()
        for index in range(2)
    ]
    pln_id = next(
        a["id"]
        for a in client.get("/api/accounts", headers=auth(sender["access_token"])).json()[
            "accounts"
        ]
        if a["currency_code"] == "PLN"
    )

    def send(index):
        return client.post(
            "/api/transfers",
            headers={**auth(sender["access_token"]), "Idempotency-Key": f"race-{index}"},
            json={
                "recipient_email": recipients[index]["user"]["email"],
                "source_account_id": pln_id,
                "currency_code": "PLN",
                "amount_minor": 70_000,
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(send, range(2)))
    assert sorted(response.status_code for response in results) == [201, 409]
    sender_accounts = client.get("/api/accounts", headers=auth(sender["access_token"])).json()[
        "accounts"
    ]
    assert (
        next(a["balance_minor"] for a in sender_accounts if a["currency_code"] == "PLN") == 30_000
    )
    received_totals = [
        next(
            a["balance_minor"]
            for a in client.get("/api/accounts", headers=auth(recipient["access_token"])).json()[
                "accounts"
            ]
            if a["currency_code"] == "PLN"
        )
        - 100_000
        for recipient in recipients
    ]
    assert sorted(received_totals) == [0, 70_000]


def test_transfer_failure_after_balance_updates_rolls_back_everything(client, tmp_path):
    sender = client.post(
        "/api/register",
        json={
            "email": "rollback-sender@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    recipient = client.post(
        "/api/register",
        json={
            "email": "rollback-recipient@example.com",
            "password": "violet-bridge-2026!",
            "captcha_token": "test-token",
        },
    ).json()
    pln_id = next(
        a["id"]
        for a in client.get("/api/accounts", headers=auth(sender["access_token"])).json()[
            "accounts"
        ]
        if a["currency_code"] == "PLN"
    )
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.execute(
            """
            CREATE TRIGGER reject_transfer_debit BEFORE INSERT ON ledger_entries
            WHEN NEW.amount_minor < 0
            BEGIN SELECT RAISE(ABORT, 'debit rejected'); END
            """
        )
    with pytest.raises(sqlite3.IntegrityError):
        client.post(
            "/api/transfers",
            headers={**auth(sender["access_token"]), "Idempotency-Key": "rollback"},
            json={
                "recipient_email": recipient["user"]["email"],
                "source_account_id": pln_id,
                "currency_code": "PLN",
                "amount_minor": 1_000,
            },
        )
    sender_after = client.get("/api/accounts", headers=auth(sender["access_token"])).json()[
        "accounts"
    ]
    recipient_after = client.get("/api/accounts", headers=auth(recipient["access_token"])).json()[
        "accounts"
    ]
    assert next(a["balance_minor"] for a in sender_after if a["currency_code"] == "PLN") == 100_000
    assert (
        next(a["balance_minor"] for a in recipient_after if a["currency_code"] == "PLN") == 100_000
    )
    assert (
        client.get("/api/transactions", headers=auth(sender["access_token"])).json()["total"] == 1
    )
