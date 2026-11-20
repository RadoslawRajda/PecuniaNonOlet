import base64
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.database import connect_db
from app.main import app
from app.sessions import issue_token


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "identity.db"))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_IDS", "ios.apps.googleusercontent.com,android.apps.googleusercontent.com")
    monkeypatch.setenv(
        "WEBAUTHN_ALLOWED_ORIGINS",
        "https://pecunianonolet.local,https://pecunianonolet.local:8000,android:apk-key-hash:test",
    )
    with TestClient(app) as test_client:
        yield test_client


def make_user(email="owner@example.com"):
    with connect_db() as db, db:
        cursor = db.execute(
            "INSERT INTO users(email,password_hash,created_at) VALUES (?,?,1)", (email, "not-used")
        )
        user_id = int(cursor.lastrowid)
        db.execute("INSERT INTO user_roles(user_id,role_name) VALUES (?,'user')", (user_id,))
        token = issue_token(db, user_id)
    return user_id, token


def google_claims(monkeypatch, claims):
    from google.oauth2 import id_token

    monkeypatch.setattr(id_token, "verify_oauth2_token", lambda *args, **kwargs: claims)


def credential_json(challenge, *, origin="https://pecunianonolet.local"):
    from webauthn.helpers import bytes_to_base64url

    client_data = json.dumps({"type": "webauthn.create", "challenge": challenge, "origin": origin}).encode()
    return {
        "id": "credential-id",
        "rawId": "credential-id",
        "type": "public-key",
        "response": {"clientDataJSON": bytes_to_base64url(client_data), "attestationObject": "AA"},
    }


def test_google_oidc_nonce_audience_email_and_replay(client, monkeypatch):
    nonce = client.post("/api/auth/google/nonce").json()["nonce"]
    claims = {
        "iss": "https://accounts.google.com", "sub": "google-sub-1", "email": "person@gmail.com",
        "email_verified": True, "aud": "ios.apps.googleusercontent.com", "nonce": nonce,
    }
    google_claims(monkeypatch, claims)
    response = client.post("/api/auth/google/login", json={"id_token": "signed-token-placeholder-long", "nonce": nonce})
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "person@gmail.com"
    assert response.json()["token"]
    replay = client.post("/api/auth/google/login", json={"id_token": "signed-token-placeholder-long", "nonce": nonce})
    assert replay.status_code == 401
    with connect_db() as db:
        assert db.execute("SELECT count(*) FROM oauth_identities WHERE subject='google-sub-1'").fetchone()[0] == 1


@pytest.mark.parametrize(
    "claim_patch",
    [
        {"aud": "untrusted.apps.googleusercontent.com"},
        {"iss": "https://evil.example"},
        {"email_verified": False},
    ],
)
def test_google_rejects_bad_issuer_audience_or_unverified_email(client, monkeypatch, claim_patch):
    nonce = client.post("/api/auth/google/nonce").json()["nonce"]
    claims = {
        "iss": "https://accounts.google.com", "sub": "subject", "email": "person@gmail.com",
        "email_verified": True, "aud": "ios.apps.googleusercontent.com", "nonce": nonce,
    }
    claims.update(claim_patch)
    google_claims(monkeypatch, claims)
    response = client.post("/api/auth/google/login", json={"id_token": "signed-token-placeholder-long", "nonce": nonce})
    assert response.status_code == 401
    with connect_db() as db:
        assert db.execute("SELECT count(*) FROM oauth_identities").fetchone()[0] == 0


def test_google_does_not_link_an_existing_local_account_by_email(client, monkeypatch):
    make_user("person@gmail.com")
    nonce = client.post("/api/auth/google/nonce").json()["nonce"]
    google_claims(monkeypatch, {
        "iss": "accounts.google.com", "sub": "different-google-sub", "email": "person@gmail.com",
        "email_verified": True, "aud": "android.apps.googleusercontent.com", "nonce": nonce,
    })
    response = client.post("/api/auth/google/login", json={"id_token": "signed-token-placeholder-long", "nonce": nonce})
    assert response.status_code == 409
    with connect_db() as db:
        assert db.execute("SELECT count(*) FROM oauth_identities").fetchone()[0] == 0


def test_google_link_requires_fresh_session_and_binds_verified_subject(client, monkeypatch):
    from app.authorization import token_hash

    user_id, token = make_user("local@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    nonce = client.post("/api/auth/google/link/nonce", headers=headers).json()["nonce"]
    google_claims(monkeypatch, {
        "iss": "https://accounts.google.com", "sub": "linked-sub", "email": "different@workspace.example",
        "email_verified": True, "hd": "workspace.example", "aud": "ios.apps.googleusercontent.com", "nonce": nonce,
    })
    linked = client.post("/api/auth/google/link", headers=headers, json={"id_token": "signed-token-placeholder-long", "nonce": nonce})
    assert linked.status_code == 204
    with connect_db() as db:
        assert tuple(db.execute("SELECT user_id,subject FROM oauth_identities").fetchone()) == (user_id, "linked-sub")
        db.execute("UPDATE sessions SET authenticated_at=1 WHERE token_hash=?", (token_hash(token),))
    assert client.post("/api/auth/google/link/nonce", headers=headers).status_code == 401


def test_google_identity_uses_stable_subject_after_email_change(client, monkeypatch):
    nonce = client.post("/api/auth/google/nonce").json()["nonce"]
    google_claims(monkeypatch, {
        "iss": "accounts.google.com", "sub": "stable-sub", "email": "first@gmail.com",
        "email_verified": True, "aud": "ios.apps.googleusercontent.com", "nonce": nonce,
    })
    first = client.post("/api/auth/google/login", json={"id_token": "signed-token-placeholder-long", "nonce": nonce})
    assert first.status_code == 200
    nonce2 = client.post("/api/auth/google/nonce").json()["nonce"]
    google_claims(monkeypatch, {
        "iss": "https://accounts.google.com", "sub": "stable-sub", "email": "changed@gmail.com",
        "email_verified": True, "aud": "android.apps.googleusercontent.com", "nonce": nonce2,
    })
    second = client.post("/api/auth/google/login", json={"id_token": "signed-token-placeholder-long", "nonce": nonce2})
    assert second.status_code == 200
    assert second.json()["user"]["email"] == "first@gmail.com"


def test_passkey_registration_options_require_fresh_auth_and_set_uv_rk(client, monkeypatch):
    from app.authorization import token_hash

    _user_id, token = make_user()
    response = client.post("/api/passkeys/registration/options", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    options = response.json()
    assert options["rp"]["id"] == "pecunianonolet.local"
    assert options["authenticatorSelection"]["userVerification"] == "required"
    assert options["authenticatorSelection"]["residentKey"] == "required"
    with connect_db() as db:
        challenge = db.execute("SELECT * FROM auth_challenges WHERE kind='passkey_register'").fetchone()
        assert challenge["challenge_value"] == options["challenge"]
        db.execute("UPDATE sessions SET authenticated_at=1 WHERE token_hash=?", (token_hash(token),))
    stale = client.post("/api/passkeys/registration/options", headers={"Authorization": f"Bearer {token}"})
    assert stale.status_code == 401


def test_registration_verifies_fixed_rp_origin_and_uv_and_consumes_challenge(client, monkeypatch):
    import app.routes.passkeys as route

    _, token = make_user()
    headers = {"Authorization": f"Bearer {token}"}
    options = client.post("/api/passkeys/registration/options", headers=headers).json()
    credential = credential_json(options["challenge"])
    call = {}

    def verify(**kwargs):
        call.update(kwargs)
        return SimpleNamespace(credential_id=b"test-credential", credential_public_key=b"public-key", sign_count=0)

    monkeypatch.setattr(route, "_rp_id", lambda: "pecunianonolet.local")
    monkeypatch.setattr(route, "_origins", lambda: ["https://pecunianonolet.local"])
    monkeypatch.setattr("webauthn.verify_registration_response", verify)
    body = {"credential": credential, "label": "iPhone"}
    created = client.post("/api/passkeys/registration/verify", headers=headers, json=body)
    assert created.status_code == 201, created.text
    assert call["expected_rp_id"] == "pecunianonolet.local"
    assert call["expected_origin"] == ["https://pecunianonolet.local"]
    assert call["require_user_verification"] is True
    assert client.post("/api/passkeys/registration/verify", headers=headers, json=body).status_code == 400
    with connect_db() as db:
        assert db.execute("SELECT count(*) FROM passkeys").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM auth_challenges WHERE kind='passkey_register'").fetchone()[0] == 0


def test_passkey_authentication_consumes_challenge_and_preserves_totp(client, monkeypatch):
    import app.routes.passkeys as route

    user_id, _ = make_user()
    with connect_db() as db, db:
        db.execute(
            "INSERT INTO passkeys(credential_id,user_id,public_key,sign_count,label,transports,created_at) VALUES (?,?,?,?,?,?,?)",
            ("Y3JlZA", user_id, b"pub", 0, "Laptop", "[]", 1),
        )
        db.execute(
            "INSERT INTO user_totp(user_id,secret_ciphertext,enabled_at) VALUES (?,?,?)",
            (user_id, b"encrypted", 1),
        )
    options = client.post("/api/passkeys/authentication/options").json()
    credential = credential_json(options["challenge"])
    credential["id"] = "Y3JlZA"
    credential["rawId"] = "Y3JlZA"
    credential["response"].update({"authenticatorData": "AA", "signature": "AA", "userHandle": base64.urlsafe_b64encode(user_id.to_bytes(8, "big")).decode().rstrip("=")})
    call = {}

    def verify(**kwargs):
        call.update(kwargs)
        return SimpleNamespace(new_sign_count=1)

    monkeypatch.setattr(route, "_rp_id", lambda: "pecunianonolet.local")
    monkeypatch.setattr(route, "_origins", lambda: ["https://pecunianonolet.local"])
    monkeypatch.setattr("webauthn.verify_authentication_response", verify)
    response = client.post("/api/passkeys/authentication/verify", json={"credential": credential})
    assert response.status_code == 200
    assert response.json()["mfa_required"] is True
    assert "token" not in response.json()
    assert call["require_user_verification"] is True
    assert call["expected_rp_id"] == "pecunianonolet.local"
    assert client.post("/api/passkeys/authentication/verify", json={"credential": credential}).status_code == 401
    with connect_db() as db:
        assert db.execute("SELECT sign_count FROM passkeys WHERE credential_id='Y3JlZA'").fetchone()[0] == 1


def test_passkey_delete_is_owner_scoped_and_requires_recent_auth(client):
    from app.authorization import token_hash

    owner_id, owner_token = make_user("owner@example.com")
    _, other_token = make_user("other@example.com")
    with connect_db() as db, db:
        db.execute(
            "INSERT INTO passkeys(credential_id,user_id,public_key,sign_count,label,transports,created_at) VALUES (?,?,?,?,?,?,?)",
            ("owned-key", owner_id, b"pub", 0, "Device", "[]", 1),
        )
    endpoint = "/api/passkeys/owned-key"
    assert client.delete(endpoint, headers={"Authorization": f"Bearer {other_token}"}).status_code == 404
    assert client.delete(endpoint, headers={"Authorization": f"Bearer {owner_token}"}).status_code == 204
    with connect_db() as db, db:
        assert db.execute("SELECT count(*) FROM passkeys WHERE credential_id='owned-key'").fetchone()[0] == 0
        db.execute("INSERT INTO passkeys(credential_id,user_id,public_key,sign_count,label,transports,created_at) VALUES (?,?,?,?,?,?,?)", ("stale-key",owner_id,b"pub",0,"Device","[]",1))
        db.execute("UPDATE sessions SET authenticated_at=1 WHERE token_hash=?", (token_hash(owner_token),))
    assert client.delete("/api/passkeys/stale-key", headers={"Authorization": f"Bearer {owner_token}"}).status_code == 401


def test_local_association_documents_are_served_for_ios_and_android(client):
    aasa = client.get("/.well-known/apple-app-site-association")
    links = client.get("/.well-known/assetlinks.json")
    assert aasa.status_code == links.status_code == 200
    assert aasa.json()["webcredentials"]["apps"] == ["96UM85TJJ7.com.rajda.pecunianonolet"]
    assert links.json()[0]["target"]["package_name"] == "com.pecunianonolet"
    assert links.headers["Cache-Control"] == "no-store"
