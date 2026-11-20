import base64
import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pyotp
import pytest
from app.main import app
from app.routes import mfa as mfa_routes
from app.services import authentication as auth_service
from app.totp import decrypt_secret, matching_totp_step
from fastapi.testclient import TestClient

TEST_KEY = base64.urlsafe_b64encode(b"test-only-totp-key-material-32b!").decode()
NOW = 1_700_000_000
PASSWORD = "correct-password-123"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "mfa-test.db"))
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", TEST_KEY)
    monkeypatch.setattr(auth_service, "current_timestamp", lambda: NOW)
    with TestClient(app) as test_client:
        yield test_client


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def register(client, email="mfa@example.com"):
    response = client.post(
        "/api/register", json={"email": email, "password": PASSWORD, "captcha_token": "test-token"}
    )
    assert response.status_code == 201
    return response.json()


def enable_totp(client, token, monkeypatch, *, now=NOW, email="mfa@example.com"):
    monkeypatch.setattr(mfa_routes, "unix_time", lambda: now)
    setup = client.post(
        "/api/mfa/totp/setup",
        headers=auth(token),
        json={"current_password": PASSWORD},
    )
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    parsed = pyotp.parse_uri(setup.json()["provisioning_uri"])
    assert parsed.secret == secret
    assert parsed.name == email
    assert parsed.digits == 6
    assert parsed.interval == 30
    assert parsed.digest().name == "sha1"
    assert setup.headers["cache-control"] == "no-store"
    code = pyotp.TOTP(secret).at(now)
    enabled = client.post("/api/mfa/totp/confirm", headers=auth(token), json={"code": code})
    assert enabled.status_code == 200, enabled.text
    return secret, enabled.json()["recovery_codes"]


def login_challenge(client, email="mfa@example.com", password=PASSWORD):
    response = client.post("/api/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mfa_required"] is True
    assert "access_token" not in body
    return body["challenge_token"]


def test_rfc6238_sha1_vectors_and_adjacent_step_window():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    vectors = (
        (59, "287082"),
        (1_111_111_109, "081804"),
        (1_111_111_111, "050471"),
        (1_234_567_890, "005924"),
        (2_000_000_000, "279037"),
        (20_000_000_000, "353130"),
    )
    for timestamp, code in vectors:
        assert matching_totp_step(secret, code, now=timestamp) == timestamp // 30
    assert matching_totp_step(secret, "287082", now=59 + 30) == 59 // 30
    # OWASP's window is current plus one previous step, not a symmetric window.
    assert matching_totp_step(secret, pyotp.TOTP(secret).at(60), now=59) is None
    assert matching_totp_step(secret, "287082", now=59 + 60) is None
    assert matching_totp_step(secret, "bad-code", now=59) is None


def test_enrollment_encrypts_secret_issues_recovery_codes_and_requires_mfa_login(
    client, tmp_path, monkeypatch
):
    registered = register(client)
    token = registered["access_token"]
    assert client.get("/api/mfa", headers=auth(token)).json() == {"totp_enabled": False}
    assert (
        client.post(
            "/api/mfa/totp/setup", headers=auth(token), json={"current_password": "wrong"}
        ).status_code
        == 401
    )

    secret, recovery_codes = enable_totp(client, token, monkeypatch)
    assert len(recovery_codes) == 10
    assert len(set(recovery_codes)) == 10
    assert client.get("/api/mfa", headers=auth(token)).status_code == 401

    with sqlite3.connect(tmp_path / "mfa-test.db") as db:
        stored = db.execute(
            "SELECT secret_ciphertext FROM user_totp WHERE user_id = ?",
            (registered["user"]["id"],),
        ).fetchone()[0]
        hashes = [row[0] for row in db.execute("SELECT code_hash FROM totp_recovery_codes")]
    assert secret.encode() not in stored
    assert decrypt_secret(registered["user"]["id"], stored, purpose="active") == secret
    assert all(code not in hashes for code in recovery_codes)
    assert all(hashlib.sha256(code.encode()).hexdigest() in hashes for code in recovery_codes)

    challenge = login_challenge(client)
    with sqlite3.connect(tmp_path / "mfa-test.db") as db:
        challenge_hash = hashlib.sha256(challenge.encode()).hexdigest()
        assert db.execute(
            "SELECT 1 FROM totp_login_challenges WHERE challenge_hash = ?", (challenge_hash,)
        ).fetchone()
        assert challenge not in {
            row[0] for row in db.execute("SELECT challenge_hash FROM totp_login_challenges")
        }

    monkeypatch.setattr(mfa_routes, "unix_time", lambda: NOW + 30)
    code = pyotp.TOTP(secret).at(NOW + 30)
    completed = client.post("/api/login/mfa", json={"challenge_token": challenge, "code": code})
    assert completed.status_code == 200, completed.text
    session_token = completed.json()["access_token"]
    assert client.get("/api/me", headers=auth(session_token)).status_code == 200
    assert (
        client.post("/api/login/mfa", json={"challenge_token": challenge, "code": code}).status_code
        == 401
    )

    # A valid TOTP time step cannot be replayed through a fresh password challenge.
    replay_challenge = login_challenge(client)
    replay = client.post("/api/login/mfa", json={"challenge_token": replay_challenge, "code": code})
    assert replay.status_code == 401

    # Recovery codes work once, and can recover the account if the authenticator is lost.
    recovery_challenge = login_challenge(client)
    recovery_login = client.post(
        "/api/login/mfa",
        json={"challenge_token": recovery_challenge, "code": recovery_codes[0]},
    )
    assert recovery_login.status_code == 200
    again_challenge = login_challenge(client)
    assert (
        client.post(
            "/api/login/mfa",
            json={"challenge_token": again_challenge, "code": recovery_codes[0]},
        ).status_code
        == 401
    )


def test_disabling_totp_requires_password_and_fresh_code_then_revokes_sessions(client, monkeypatch):
    registered = register(client)
    secret, _ = enable_totp(client, registered["access_token"], monkeypatch)
    challenge = login_challenge(client)
    now = NOW + 30
    monkeypatch.setattr(mfa_routes, "unix_time", lambda: now)
    login = client.post(
        "/api/login/mfa",
        json={"challenge_token": challenge, "code": pyotp.TOTP(secret).at(now)},
    ).json()
    session_token = login["access_token"]

    assert (
        client.post(
            "/api/mfa/totp/disable",
            headers=auth(session_token),
            json={"current_password": "wrong", "code": "000000"},
        ).status_code
        == 401
    )
    now += 30
    disabled = client.post(
        "/api/mfa/totp/disable",
        headers=auth(session_token),
        json={"current_password": PASSWORD, "code": pyotp.TOTP(secret).at(now)},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json() == {"totp_enabled": False, "reauthentication_required": True}
    assert client.get("/api/mfa", headers=auth(session_token)).status_code == 401
    logged_in = client.post("/api/login", json={"email": "mfa@example.com", "password": PASSWORD})
    assert logged_in.status_code == 200
    assert "access_token" in logged_in.json()


def test_failed_codes_are_rate_limited_across_challenges(client, monkeypatch):
    registered = register(client)
    enable_totp(client, registered["access_token"], monkeypatch)
    challenge = login_challenge(client)
    monkeypatch.setattr(mfa_routes, "unix_time", lambda: NOW)
    wrong_code = "000000"
    for attempt in range(4):
        response = client.post(
            "/api/login/mfa", json={"challenge_token": challenge, "code": wrong_code}
        )
        assert response.status_code == 401
    locked = client.post("/api/login/mfa", json={"challenge_token": challenge, "code": wrong_code})
    assert locked.status_code == 429
    assert locked.headers["Retry-After"] == "900"
    assert (
        client.post(
            "/api/login", json={"email": "mfa@example.com", "password": PASSWORD}
        ).status_code
        == 429
    )

    monkeypatch.setattr(mfa_routes, "unix_time", lambda: NOW + 900)
    monkeypatch.setattr(auth_service, "current_timestamp", lambda: NOW + 900)
    assert login_challenge(client)


def test_password_change_invalidates_pre_authentication_challenges(client, monkeypatch):
    registered = register(client)
    secret, _ = enable_totp(client, registered["access_token"], monkeypatch)
    monkeypatch.setattr(mfa_routes, "unix_time", lambda: NOW + 30)
    challenge = login_challenge(client)
    # The registration session was revoked at MFA activation; use a fresh completed login.
    first_login = client.post(
        "/api/login/mfa",
        json={"challenge_token": challenge, "code": pyotp.TOTP(secret).at(NOW + 30)},
    ).json()
    stale_challenge = login_challenge(client)
    changed = client.post(
        "/api/change-password",
        headers=auth(first_login["access_token"]),
        json={"current_password": PASSWORD, "new_password": "changed-password-456"},
    )
    assert changed.status_code == 200
    assert (
        client.post(
            "/api/login/mfa",
            json={"challenge_token": stale_challenge, "code": pyotp.TOTP(secret).at(NOW + 60)},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/login", json={"email": "mfa@example.com", "password": "changed-password-456"}
        ).json()["mfa_required"]
        is True
    )


def test_missing_encryption_key_fails_closed_for_setup_and_enabled_login(client, monkeypatch):
    registered = register(client)
    monkeypatch.delenv("MFA_ENCRYPTION_KEY")
    setup = client.post(
        "/api/mfa/totp/setup",
        headers=auth(registered["access_token"]),
        json={"current_password": PASSWORD},
    )
    assert setup.status_code == 503

    monkeypatch.setenv("MFA_ENCRYPTION_KEY", TEST_KEY)
    secret, _ = enable_totp(client, registered["access_token"], monkeypatch)
    monkeypatch.delenv("MFA_ENCRYPTION_KEY")
    login = client.post("/api/login", json={"email": "mfa@example.com", "password": PASSWORD})
    assert login.status_code == 200
    assert login.json()["mfa_required"] is True
    assert "access_token" not in login.json()
    second_factor = client.post(
        "/api/login/mfa",
        json={
            "challenge_token": login.json()["challenge_token"],
            "code": pyotp.TOTP(secret).at(NOW),
        },
    )
    assert second_factor.status_code == 503
    assert "access_token" not in second_factor.json()


def test_expired_setup_secret_cannot_be_confirmed(client, monkeypatch):
    registered = register(client)
    monkeypatch.setattr(mfa_routes, "unix_time", lambda: NOW)
    setup = client.post(
        "/api/mfa/totp/setup",
        headers=auth(registered["access_token"]),
        json={"current_password": PASSWORD},
    )
    assert setup.status_code == 200
    monkeypatch.setattr(mfa_routes, "unix_time", lambda: NOW + 601)
    response = client.post(
        "/api/mfa/totp/confirm",
        headers=auth(registered["access_token"]),
        json={"code": pyotp.TOTP(setup.json()["secret"]).at(NOW + 601)},
    )
    assert response.status_code == 409
    assert client.get("/api/mfa", headers=auth(registered["access_token"])).json() == {
        "totp_enabled": False
    }


def test_expired_login_challenge_cannot_issue_a_session(client, tmp_path, monkeypatch):
    registered = register(client)
    enable_totp(client, registered["access_token"], monkeypatch)
    challenge = login_challenge(client)
    with sqlite3.connect(tmp_path / "mfa-test.db") as db:
        sessions_before = db.execute("SELECT count(*) FROM auth_sessions").fetchone()[0]
    monkeypatch.setattr(mfa_routes, "unix_time", lambda: NOW + 300)

    response = client.post(
        "/api/login/mfa",
        json={"challenge_token": challenge, "code": "123456"},
    )

    assert response.status_code == 401
    assert "access_token" not in response.json()
    with sqlite3.connect(tmp_path / "mfa-test.db") as db:
        assert db.execute("SELECT count(*) FROM auth_sessions").fetchone()[0] == sessions_before
        assert (
            db.execute(
                "SELECT count(*) FROM totp_login_challenges WHERE challenge_hash = ?",
                (hashlib.sha256(challenge.encode()).hexdigest(),),
            ).fetchone()[0]
            == 0
        )


def test_tampered_totp_ciphertext_fails_closed_without_session(client, tmp_path, monkeypatch):
    registered = register(client)
    secret, _ = enable_totp(client, registered["access_token"], monkeypatch)
    with sqlite3.connect(tmp_path / "mfa-test.db") as db:
        ciphertext = bytearray(db.execute("SELECT secret_ciphertext FROM user_totp").fetchone()[0])
        ciphertext[-1] ^= 1
        db.execute("UPDATE user_totp SET secret_ciphertext = ?", (bytes(ciphertext),))
        sessions_before = db.execute("SELECT count(*) FROM auth_sessions").fetchone()[0]

    first_factor = client.post(
        "/api/login", json={"email": "mfa@example.com", "password": PASSWORD}
    )
    assert first_factor.status_code == 200
    response = client.post(
        "/api/login/mfa",
        json={
            "challenge_token": first_factor.json()["challenge_token"],
            "code": pyotp.TOTP(secret).at(NOW),
        },
    )

    assert response.status_code == 503
    assert "access_token" not in response.json()
    with sqlite3.connect(tmp_path / "mfa-test.db") as db:
        assert db.execute("SELECT count(*) FROM auth_sessions").fetchone()[0] == sessions_before


def test_concurrent_challenge_submission_issues_only_one_session(client, monkeypatch):
    registered = register(client)
    secret, _ = enable_totp(client, registered["access_token"], monkeypatch)
    challenge = login_challenge(client)
    monkeypatch.setattr(mfa_routes, "unix_time", lambda: NOW + 30)
    payload = {"challenge_token": challenge, "code": pyotp.TOTP(secret).at(NOW + 30)}

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post("/api/login/mfa", json=payload), range(2)))
    assert sorted(response.status_code for response in results) == [200, 401]


def test_enabling_mfa_revokes_all_previous_sessions(client, monkeypatch):
    first = register(client)
    second = client.post(
        "/api/login", json={"email": "mfa@example.com", "password": PASSWORD}
    ).json()
    enable_totp(client, first["access_token"], monkeypatch)
    assert client.get("/api/me", headers=auth(first["access_token"])).status_code == 401
    assert client.get("/api/me", headers=auth(second["access_token"])).status_code == 401
