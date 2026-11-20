"""Regression coverage for accounts created before password origin was recorded."""

import base64
import sqlite3
import time

from alembic import command
from alembic.config import Config
from app.config import Settings
from app.main import create_app
from app.passwords import password_hasher
from app.sessions import issue_session
from fastapi.testclient import TestClient


def test_upgrade_keeps_ambiguous_google_accounts_and_allows_fresh_recovery(tmp_path):
    database = tmp_path / "legacy-google.db"
    configuration = Config("alembic.ini")
    configuration.attributes["database_path"] = database
    command.upgrade(configuration, "0009_google_passkeys")
    local_password = "known-local-password-2026!"
    with sqlite3.connect(database) as db:
        db.execute(
            "INSERT INTO users(id,email,password_hash,created_at) VALUES (1,?,?,?)",
            ("old-google@example.com", password_hasher.hash("never-shown-random-secret"), 100),
        )
        db.execute(
            "INSERT INTO users(id,email,password_hash,created_at) VALUES (2,?,?,?)",
            ("linked@example.com", password_hasher.hash(local_password), 100),
        )
        for user_id in (1, 2):
            db.execute("INSERT INTO user_roles(user_id,role_name) VALUES (?,'user')", (user_id,))
            db.execute(
                """INSERT INTO oauth_identities(
                       user_id,provider,issuer,subject,email_at_link,created_at
                   ) VALUES (?,'google','https://accounts.google.com',?,?,?)""",
                (user_id, f"subject-{user_id}", f"user-{user_id}@example.com", 100),
            )
            db.execute(
                "INSERT INTO accounts(user_id,currency_code,balance_minor) VALUES (?,'PLN',12345)",
                (user_id,),
            )
        db.execute(
            """INSERT INTO passkeys(credential_id,user_id,public_key,label,created_at)
               VALUES ('legacy-passkey',1,?,'Existing key',100)""",
            (b"old-public-key",),
        )
    application = create_app(
        Settings(
            app_env="test",
            database_path=database,
            mfa_encryption_key=base64.urlsafe_b64encode(b"k" * 32).decode(),
        )
    )
    with TestClient(application) as client:
        with sqlite3.connect(database) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT id,password_origin,has_local_password,webauthn_user_handle FROM users ORDER BY id"
            ).fetchall()
            assert [row["password_origin"] for row in rows] == ["legacy_unknown"] * 2
            assert all(row["has_local_password"] == 1 for row in rows)
            assert all(row["webauthn_user_handle"] for row in rows)
            assert db.execute("SELECT SUM(balance_minor) FROM accounts").fetchone()[0] == 24690
            assert db.execute("SELECT public_key FROM passkeys").fetchone()[0] == b"old-public-key"
            now = int(time.time())
            old_tokens = issue_session(
                db, 1, authentication_method="google", provider_authenticated_at=now, now=now
            )
            linked_tokens = issue_session(
                db, 2, authentication_method="google", provider_authenticated_at=now, now=now
            )
            stale_tokens = issue_session(
                db, 2, authentication_method="google", provider_authenticated_at=now - 301, now=now
            )
            db.commit()

        recovered = client.post(
            "/api/change-password",
            headers={"Authorization": f"Bearer {old_tokens.access_token}"},
            json={"new_password": "new-known-password-2026!"},
        )
        assert recovered.status_code == 200
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT password_origin FROM users WHERE id=1").fetchone() == (
                "local",
            )
            assert db.execute("SELECT SUM(balance_minor) FROM accounts").fetchone()[0] == 24690

        wrong_password = client.post(
            "/api/change-password",
            headers={"Authorization": f"Bearer {linked_tokens.access_token}"},
            json={"current_password": "wrong", "new_password": "another-local-password-2026!"},
        )
        assert wrong_password.status_code == 401
        stale = client.post(
            "/api/mfa/totp/setup",
            headers={"Authorization": f"Bearer {stale_tokens.access_token}"},
            json={},
        )
        assert stale.status_code == 401
        stale_password_change = client.post(
            "/api/change-password",
            headers={"Authorization": f"Bearer {stale_tokens.access_token}"},
            json={"new_password": "another-local-password-2026!"},
        )
        assert stale_password_change.status_code == 401
        setup = client.post(
            "/api/mfa/totp/setup",
            headers={"Authorization": f"Bearer {linked_tokens.access_token}"},
            json={},
        )
        assert setup.status_code == 200
        login = client.post(
            "/api/login", json={"email": "linked@example.com", "password": local_password}
        )
        assert login.status_code == 200
        changed = client.post(
            "/api/change-password",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
            json={
                "current_password": local_password,
                "new_password": "updated-local-password-2026!",
            },
        )
        assert changed.status_code == 200
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT password_origin FROM users WHERE id=2").fetchone() == (
                "local",
            )


def test_upgrade_from_already_applied_0014_preserves_mfa_and_recovery_data(tmp_path):
    database = tmp_path / "already-upgraded.db"
    configuration = Config("alembic.ini")
    configuration.attributes["database_path"] = database
    command.upgrade(configuration, "0014_security_events")
    with sqlite3.connect(database) as db:
        db.execute(
            """INSERT INTO users(
                   id,email,password_hash,created_at,webauthn_user_handle,has_local_password
               ) VALUES (1,'existing@example.com','historical-hash',100,?,1)""",
            (b"h" * 32,),
        )
        db.execute(
            """INSERT INTO oauth_identities(
                   user_id,provider,issuer,subject,email_at_link,created_at
               ) VALUES (1,'google','https://accounts.google.com','old-subject',
                         'existing@example.com',100)"""
        )
        db.execute(
            """INSERT INTO user_totp(user_id,secret_ciphertext,enabled_at)
               VALUES (1,?,100)""",
            (b"encrypted-secret",),
        )
        db.execute(
            "INSERT INTO totp_recovery_codes(code_hash,user_id,created_at) VALUES (?,1,100)",
            ("a" * 64,),
        )
        db.execute(
            "INSERT INTO accounts(user_id,currency_code,balance_minor) VALUES (1,'PLN',12345)"
        )
    command.upgrade(configuration, "head")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT password_origin FROM users").fetchone() == ("legacy_unknown",)
        assert db.execute("SELECT webauthn_user_handle FROM users").fetchone() == (b"h" * 32,)
        assert db.execute("SELECT secret_ciphertext FROM user_totp").fetchone() == (
            b"encrypted-secret",
        )
        assert db.execute("SELECT code_hash FROM totp_recovery_codes").fetchone() == ("a" * 64,)
        assert db.execute("SELECT balance_minor FROM accounts").fetchone() == (12345,)
