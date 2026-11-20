import base64
import hashlib
import json
import sqlite3
import time
from datetime import UTC
from types import SimpleNamespace

import pyotp
import pytest
from app.authorization import token_hash
from app.database import connect_db
from app.main import app
from app.sessions import issue_session
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "identity.db"))
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", "dGVzdC1vbmx5LXRvdHAta2V5LW1hdGVyaWFsLTMyYiE=")
    monkeypatch.setenv(
        "GOOGLE_OAUTH_CLIENT_IDS",
        "ios.apps.googleusercontent.com,android.apps.googleusercontent.com",
    )
    monkeypatch.setenv(
        "WEBAUTHN_ALLOWED_ORIGINS",
        "https://pecunianonolet.local,https://pecunianonolet.local:8000,android:apk-key-hash:test",
    )
    with TestClient(app) as test_client:
        yield test_client


def make_user(email="owner@example.com"):
    with connect_db() as db, db:
        cursor = db.execute(
            "INSERT INTO users(email,password_hash,webauthn_user_handle,created_at) VALUES (?,?,?,1)",
            (
                email,
                "not-used",
                (int.from_bytes(email.encode()[:4].ljust(4, b"0"), "big") + 1).to_bytes(8, "big"),
            ),
        )
        user_id = int(cursor.lastrowid)
        db.execute("INSERT INTO user_roles(user_id,role_name) VALUES (?,'user')", (user_id,))
        token = issue_session(db, user_id).access_token
    return user_id, token


def google_claims(monkeypatch, claims):
    from google.oauth2 import id_token

    monkeypatch.setattr(id_token, "verify_oauth2_token", lambda *args, **kwargs: claims)


def credential_json(challenge, *, origin="https://pecunianonolet.local"):
    from webauthn.helpers import bytes_to_base64url

    client_data = json.dumps(
        {"type": "webauthn.create", "challenge": challenge, "origin": origin}
    ).encode()
    return {
        "id": "credential-id",
        "rawId": "credential-id",
        "type": "public-key",
        "response": {"clientDataJSON": bytes_to_base64url(client_data), "attestationObject": "AA"},
    }


class TestAuthenticator:
    """Minimal local WebAuthn authenticator used to create real signed ceremonies."""

    __test__ = False

    def __init__(self):
        from cryptography.hazmat.primitives.asymmetric import ec

        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = b"local-test-authenticator-key"

    def _client_data(self, ceremony, challenge, origin):
        return json.dumps(
            {"type": ceremony, "challenge": challenge, "origin": origin},
            separators=(",", ":"),
        ).encode()

    def _cose_public_key(self):
        import cbor2

        numbers = self.private_key.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,  # EC2
                3: -7,  # ES256
                -1: 1,  # P-256
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def registration(self, challenge, *, origin="https://pecunianonolet.local"):
        import cbor2
        from webauthn.helpers import bytes_to_base64url

        client_data = self._client_data("webauthn.create", challenge, origin)
        rp_hash = hashlib.sha256(b"pecunianonolet.local").digest()
        flags = 0x01 | 0x04 | 0x40  # UP, UV, AT
        auth_data = (
            rp_hash
            + bytes([flags])
            + (0).to_bytes(4, "big")
            + bytes(16)
            + len(self.credential_id).to_bytes(2, "big")
            + self.credential_id
            + self._cose_public_key()
        )
        attestation = cbor2.dumps({"fmt": "none", "authData": auth_data, "attStmt": {}})
        encoded_id = bytes_to_base64url(self.credential_id)
        return {
            "id": encoded_id,
            "rawId": encoded_id,
            "type": "public-key",
            "authenticatorAttachment": "platform",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "attestationObject": bytes_to_base64url(attestation),
                "transports": ["internal"],
            },
        }

    def assertion(
        self,
        challenge,
        user_handle,
        *,
        origin="https://pecunianonolet.local",
        sign_count=0,
        bad_signature=False,
    ):
        import hashlib

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from webauthn.helpers import bytes_to_base64url

        client_data = self._client_data("webauthn.get", challenge, origin)
        auth_data = (
            hashlib.sha256(b"pecunianonolet.local").digest()
            + bytes([0x01 | 0x04])
            + sign_count.to_bytes(4, "big")
        )
        signed_data = auth_data + hashlib.sha256(client_data).digest()
        signature = self.private_key.sign(signed_data, ec.ECDSA(hashes.SHA256()))
        if bad_signature:
            signature = signature[:-1] + bytes([signature[-1] ^ 1])
        encoded_id = bytes_to_base64url(self.credential_id)
        return {
            "id": encoded_id,
            "rawId": encoded_id,
            "type": "public-key",
            "authenticatorAttachment": "platform",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
                "userHandle": bytes_to_base64url(user_handle),
            },
        }


def set_client_data_type(credential, value):
    client_data = json.loads(
        base64.urlsafe_b64decode(credential["response"]["clientDataJSON"] + "==")
    )
    client_data["type"] = value
    credential["response"]["clientDataJSON"] = (
        base64.urlsafe_b64encode(json.dumps(client_data).encode()).decode().rstrip("=")
    )


def test_google_oidc_nonce_audience_email_and_replay(client, monkeypatch):
    nonce = client.post("/api/auth/google/nonce").json()["nonce"]
    claims = {
        "iss": "https://accounts.google.com",
        "sub": "google-sub-1",
        "email": "person@gmail.com",
        "email_verified": True,
        "aud": "ios.apps.googleusercontent.com",
        "nonce": nonce,
        "auth_time": int(time.time()),
    }
    google_claims(monkeypatch, claims)
    response = client.post(
        "/api/auth/google/login", json={"id_token": "signed-token-placeholder-long", "nonce": nonce}
    )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "person@gmail.com"
    assert response.json()["access_token"]
    replay = client.post(
        "/api/auth/google/login", json={"id_token": "signed-token-placeholder-long", "nonce": nonce}
    )
    assert replay.status_code == 401
    with connect_db() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM oauth_identities WHERE subject='google-sub-1'"
            ).fetchone()[0]
            == 1
        )


def test_google_login_stops_verifying_after_challenge_attempt_limit(client, monkeypatch):
    from app.routes import google_auth
    from fastapi import HTTPException

    nonce = client.post("/api/auth/google/nonce").json()["nonce"]
    verifications = 0

    def reject_google_token(_payload):
        nonlocal verifications
        verifications += 1
        raise HTTPException(status_code=401, detail="invalid test token")

    monkeypatch.setattr(google_auth, "_verify_google_id_token", reject_google_token)
    payload = {"id_token": "signed-token-placeholder-long", "nonce": nonce}
    for _ in range(5):
        assert client.post("/api/auth/google/login", json=payload).status_code == 401
    assert verifications == 5

    exhausted = client.post("/api/auth/google/login", json=payload)
    assert exhausted.status_code == 401
    assert verifications == 5
    with connect_db() as db:
        challenge = db.execute(
            "SELECT attempts FROM auth_challenges WHERE challenge_value=?", (nonce,)
        ).fetchone()
    assert challenge["attempts"] == 5


def test_google_oidc_uses_google_auth_to_verify_real_signature_and_expiry(monkeypatch):
    from datetime import datetime, timedelta

    import google.auth.crypt
    import google.auth.jwt
    import google.oauth2.id_token
    from app.routes.google_auth import GoogleTokenRequest, _verify_google_id_token
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from fastapi import HTTPException

    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_IDS", "ios.apps.googleusercontent.com")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Google OIDC test key")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .sign(private_key, hashes.SHA256())
    )
    pem_certificate = certificate.public_bytes(serialization.Encoding.PEM).decode()
    monkeypatch.setattr(
        google.oauth2.id_token, "_fetch_certs", lambda *_: {"test-key": pem_certificate}
    )
    signer = google.auth.crypt.RSASigner.from_string(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    nonce = "a" * 32
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "ios.apps.googleusercontent.com",
        "sub": "stable-google-subject",
        "email": "verified@gmail.com",
        "email_verified": True,
        "nonce": nonce,
        "iat": int(time.time()),
        "exp": int(time.time()) + 60,
        "auth_time": int(time.time()),
    }
    token = google.auth.jwt.encode(signer, claims, key_id="test-key").decode()
    request = GoogleTokenRequest(id_token=token, nonce=nonce)
    identity = _verify_google_id_token(request)
    assert identity.subject == "stable-google-subject"
    assert identity.authenticated_at == claims["auth_time"]

    tampered = token.rsplit(".", 1)[0] + "." + ("A" if token[-1] != "A" else "B")
    with pytest.raises(HTTPException) as invalid_signature:
        _verify_google_id_token(GoogleTokenRequest(id_token=tampered, nonce=nonce))
    assert invalid_signature.value.status_code == 401

    claims["exp"] = int(time.time()) - 60
    expired = google.auth.jwt.encode(signer, claims, key_id="test-key").decode()
    with pytest.raises(HTTPException) as expired_token:
        _verify_google_id_token(GoogleTokenRequest(id_token=expired, nonce=nonce))
    assert expired_token.value.status_code == 401


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
        "iss": "https://accounts.google.com",
        "sub": "subject",
        "email": "person@gmail.com",
        "email_verified": True,
        "aud": "ios.apps.googleusercontent.com",
        "nonce": nonce,
        "auth_time": int(time.time()),
    }
    claims.update(claim_patch)
    google_claims(monkeypatch, claims)
    response = client.post(
        "/api/auth/google/login", json={"id_token": "signed-token-placeholder-long", "nonce": nonce}
    )
    assert response.status_code == 401
    with connect_db() as db:
        assert db.execute("SELECT count(*) FROM oauth_identities").fetchone()[0] == 0


def test_google_does_not_link_an_existing_local_account_by_email(client, monkeypatch):
    make_user("person@gmail.com")
    nonce = client.post("/api/auth/google/nonce").json()["nonce"]
    google_claims(
        monkeypatch,
        {
            "iss": "accounts.google.com",
            "sub": "different-google-sub",
            "email": "person@gmail.com",
            "email_verified": True,
            "aud": "android.apps.googleusercontent.com",
            "nonce": nonce,
        },
    )
    response = client.post(
        "/api/auth/google/login", json={"id_token": "signed-token-placeholder-long", "nonce": nonce}
    )
    assert response.status_code == 409
    with connect_db() as db:
        assert db.execute("SELECT count(*) FROM oauth_identities").fetchone()[0] == 0


def test_google_only_account_has_undisclosed_local_credential_and_cannot_password_login(
    client, monkeypatch
):
    from app.routes import mfa as mfa_routes

    monkeypatch.setenv("MFA_ENCRYPTION_KEY", "dGVzdC1vbmx5LXRvdHAta2V5LW1hdGVyaWFsLTMyYiE=")
    totp_now = int(time.time())
    monkeypatch.setattr(mfa_routes, "unix_time", lambda: totp_now)
    nonce = client.post("/api/auth/google/nonce").json()["nonce"]
    google_claims(
        monkeypatch,
        {
            "iss": "https://accounts.google.com",
            "sub": "google-only-sub",
            "email": "person@gmail.com",
            "email_verified": True,
            "aud": "ios.apps.googleusercontent.com",
            "nonce": nonce,
            "auth_time": int(time.time()),
        },
    )
    response = client.post(
        "/api/auth/google/login", json={"id_token": "signed-token-placeholder-long", "nonce": nonce}
    )
    assert response.status_code == 200
    with connect_db() as db:
        row = db.execute(
            "SELECT password_hash,webauthn_user_handle,has_local_password,password_origin FROM users WHERE email='person@gmail.com'"
        ).fetchone()
        assert row["password_hash"]
        assert row["has_local_password"] == 0
        assert row["password_origin"] == "google_generated"
        assert len(row["webauthn_user_handle"]) == 32
    password_login = client.post(
        "/api/login", json={"email": "person@gmail.com", "password": "anything"}
    )
    assert password_login.status_code == 401
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    setup = client.post("/api/mfa/totp/setup", headers=headers, json={})
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    confirmed = client.post(
        "/api/mfa/totp/confirm",
        headers=headers,
        json={"code": pyotp.TOTP(secret).at(totp_now)},
    )
    assert confirmed.status_code == 200, confirmed.text

    login_nonce = client.post("/api/auth/google/nonce").json()["nonce"]
    claims = {
        "iss": "https://accounts.google.com",
        "sub": "google-only-sub",
        "email": "person@gmail.com",
        "email_verified": True,
        "aud": "ios.apps.googleusercontent.com",
        "nonce": login_nonce,
        "auth_time": int(time.time()),
    }
    google_claims(monkeypatch, claims)
    second_factor = client.post(
        "/api/auth/google/login",
        json={"id_token": "signed-token-placeholder-long", "nonce": login_nonce},
    )
    assert second_factor.status_code == 200
    assert second_factor.json()["mfa_required"] is True
    challenge_hash = hashlib.sha256(second_factor.json()["challenge_token"].encode()).hexdigest()
    with connect_db() as db:
        challenge = db.execute(
            "SELECT authentication_method,provider_authenticated_at FROM totp_login_challenges WHERE challenge_hash=?",
            (challenge_hash,),
        ).fetchone()
        assert challenge["authentication_method"] == "google"
        assert challenge["provider_authenticated_at"] == claims["auth_time"]
    monkeypatch.setattr(mfa_routes, "unix_time", lambda: totp_now + 30)
    completed = client.post(
        "/api/login/mfa",
        json={
            "challenge_token": second_factor.json()["challenge_token"],
            "code": pyotp.TOTP(secret).at(totp_now + 30),
        },
    )
    assert completed.status_code == 200, completed.text
    headers = {"Authorization": f"Bearer {completed.json()['access_token']}"}
    with connect_db() as db:
        session_auth = db.execute(
            "SELECT authentication_method,provider_authenticated_at FROM auth_sessions WHERE access_token_hash=?",
            (token_hash(completed.json()["access_token"]),),
        ).fetchone()
        assert session_auth["authentication_method"] == "google"
        assert session_auth["provider_authenticated_at"] == claims["auth_time"]
    first_password = client.post(
        "/api/change-password",
        headers=headers,
        json={"new_password": "new-local-violet-bridge-2026!"},
    )
    assert first_password.status_code == 200, first_password.text
    assert (
        client.post(
            "/api/login",
            json={"email": "person@gmail.com", "password": "new-local-violet-bridge-2026!"},
        ).status_code
        == 200
    )


def test_google_only_management_rejects_session_without_recent_provider_auth_time(
    client, monkeypatch
):
    nonce = client.post("/api/auth/google/nonce").json()["nonce"]
    google_claims(
        monkeypatch,
        {
            "iss": "https://accounts.google.com",
            "sub": "google-stale-auth-sub",
            "email": "stale-person@gmail.com",
            "email_verified": True,
            "aud": "ios.apps.googleusercontent.com",
            "nonce": nonce,
            "auth_time": int(time.time()) - 600,
        },
    )
    login = client.post(
        "/api/auth/google/login", json={"id_token": "signed-token-placeholder-long", "nonce": nonce}
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert client.post("/api/mfa/totp/setup", headers=headers, json={}).status_code == 401
    assert (
        client.post(
            "/api/change-password",
            headers=headers,
            json={"new_password": "new-local-violet-bridge-2026!"},
        ).status_code
        == 401
    )


def test_validation_errors_do_not_echo_submitted_password(client):
    secret = "not-a-valid-password-token-value"
    response = client.post("/api/login", json={"email": "not-an-email", "password": secret})
    assert response.status_code == 422
    assert secret not in response.text


def test_audit_rejects_nested_sensitive_keys():
    from app.audit import write_audit_event

    with connect_db() as db, pytest.raises(ValueError, match="Sensitive authentication data"):
        write_audit_event(
            db,
            actor_user_id=1,
            actor_role="user",
            action="auth.test",
            entity_type="user",
            entity_id="1",
            details={"metadata": [{"access_token": "must-not-be-stored"}]},
            created_at=1,
        )


def test_google_link_requires_fresh_session_and_binds_verified_subject(client, monkeypatch):
    from app.authorization import token_hash

    user_id, token = make_user("local@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    nonce = client.post("/api/auth/google/link/nonce", headers=headers).json()["nonce"]
    google_claims(
        monkeypatch,
        {
            "iss": "https://accounts.google.com",
            "sub": "linked-sub",
            "email": "different@workspace.example",
            "email_verified": True,
            "hd": "workspace.example",
            "aud": "ios.apps.googleusercontent.com",
            "nonce": nonce,
            "auth_time": int(time.time()),
        },
    )
    linked = client.post(
        "/api/auth/google/link",
        headers=headers,
        json={"id_token": "signed-token-placeholder-long", "nonce": nonce},
    )
    assert linked.status_code == 204
    with connect_db() as db:
        assert tuple(db.execute("SELECT user_id,subject FROM oauth_identities").fetchone()) == (
            user_id,
            "linked-sub",
        )
        assert (
            db.execute(
                "SELECT action FROM audit_events WHERE action='auth.google_linked'"
            ).fetchone()[0]
            == "auth.google_linked"
        )
        db.execute(
            "UPDATE auth_sessions SET authenticated_at=1 WHERE access_token_hash=?",
            (token_hash(token),),
        )
    assert client.post("/api/auth/google/link/nonce", headers=headers).status_code == 401


def test_google_link_audit_failure_rolls_back_identity_and_nonce(client, monkeypatch):
    from app.services import google_accounts

    _, token = make_user("rollback-link@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    nonce = client.post("/api/auth/google/link/nonce", headers=headers).json()["nonce"]
    google_claims(
        monkeypatch,
        {
            "iss": "https://accounts.google.com",
            "sub": "rollback-sub",
            "email": "linked@workspace.example",
            "email_verified": True,
            "hd": "workspace.example",
            "aud": "ios.apps.googleusercontent.com",
            "nonce": nonce,
            "auth_time": int(time.time()),
        },
    )

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(google_accounts, "write_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="audit write failed"):
        client.post(
            "/api/auth/google/link",
            headers=headers,
            json={"id_token": "signed-token-placeholder-long", "nonce": nonce},
        )
    with connect_db() as db:
        assert db.execute("SELECT count(*) FROM oauth_identities").fetchone()[0] == 0
        assert (
            db.execute(
                "SELECT count(*) FROM auth_challenges WHERE challenge_value=?", (nonce,)
            ).fetchone()[0]
            == 1
        )


def test_google_link_challenge_is_bound_to_starting_session(client, monkeypatch):
    from app.authorization import token_hash

    user_id, first_token = make_user("bound-link@example.com")
    nonce = client.post(
        "/api/auth/google/link/nonce", headers={"Authorization": f"Bearer {first_token}"}
    ).json()["nonce"]
    with connect_db() as db, db:
        second_token = issue_session(db, user_id).access_token
    claims = {
        "iss": "https://accounts.google.com",
        "sub": "session-bound-sub",
        "email": "linked@workspace.example",
        "email_verified": True,
        "hd": "workspace.example",
        "aud": "ios.apps.googleusercontent.com",
        "nonce": nonce,
    }
    google_claims(monkeypatch, claims)
    response = client.post(
        "/api/auth/google/link",
        headers={"Authorization": f"Bearer {second_token}"},
        json={"id_token": "signed-token-placeholder-long", "nonce": nonce},
    )
    assert response.status_code == 401
    with connect_db() as db:
        challenge = db.execute(
            "SELECT session_hash FROM auth_challenges WHERE challenge_value=?", (nonce,)
        ).fetchone()
        session_id = db.execute(
            "SELECT session_id FROM auth_sessions WHERE access_token_hash=?",
            (token_hash(first_token),),
        ).fetchone()[0]
        assert challenge["session_hash"] == session_id


def test_linked_external_google_email_can_log_in_by_stable_subject(client, monkeypatch):
    user_id, token = make_user("local-account@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    nonce = client.post("/api/auth/google/link/nonce", headers=headers).json()["nonce"]
    claims = {
        "iss": "https://accounts.google.com",
        "sub": "external-email-subject",
        "email": "person@independent-mail.example",
        "email_verified": True,
        "aud": "ios.apps.googleusercontent.com",
        "nonce": nonce,
        "auth_time": int(time.time()),
    }
    google_claims(monkeypatch, claims)
    linked = client.post(
        "/api/auth/google/link",
        headers=headers,
        json={"id_token": "signed-token-placeholder-long", "nonce": nonce},
    )
    assert linked.status_code == 204

    login_nonce = client.post("/api/auth/google/nonce").json()["nonce"]
    claims["nonce"] = login_nonce
    google_claims(monkeypatch, claims)
    logged_in = client.post(
        "/api/auth/google/login",
        json={"id_token": "signed-token-placeholder-long", "nonce": login_nonce},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["id"] == user_id


def test_passkeys_use_real_registration_and_assertion_signatures(client):
    user_id, token = make_user("webauthn-real@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    authenticator = TestAuthenticator()

    registration_options = client.post("/api/passkeys/registration/options", headers=headers)
    assert registration_options.status_code == 200, registration_options.text
    registration = authenticator.registration(registration_options.json()["challenge"])
    created = client.post(
        "/api/passkeys/registration/verify",
        headers=headers,
        json={"credential": registration, "label": "Test authenticator"},
    )
    assert created.status_code == 201, created.text

    with connect_db() as db:
        row = db.execute(
            "SELECT credential_id,user_id,public_key,sign_count FROM passkeys WHERE user_id=?",
            (user_id,),
        ).fetchone()
        handle = db.execute(
            "SELECT webauthn_user_handle FROM users WHERE id=?", (user_id,)
        ).fetchone()[0]
        assert row["user_id"] == user_id
        assert row["sign_count"] == 0
        assert row["public_key"]

    assertion_options = client.post("/api/passkeys/authentication/options")
    assert assertion_options.status_code == 200
    assertion = authenticator.assertion(assertion_options.json()["challenge"], handle)
    authenticated = client.post(
        "/api/passkeys/authentication/verify", json={"credential": assertion}
    )
    assert authenticated.status_code == 200, authenticated.text
    assert authenticated.json()["user"]["id"] == user_id
    with connect_db() as db:
        session = db.execute(
            "SELECT authentication_method FROM auth_sessions WHERE access_token_hash=?",
            (token_hash(authenticated.json()["access_token"]),),
        ).fetchone()
        assert session["authentication_method"] == "passkey"

    # Synced authenticators may legitimately keep signCount at zero across assertions.
    repeat_options = client.post("/api/passkeys/authentication/options")
    repeated_assertion = authenticator.assertion(repeat_options.json()["challenge"], handle)
    repeated_login = client.post(
        "/api/passkeys/authentication/verify", json={"credential": repeated_assertion}
    )
    assert repeated_login.status_code == 200, repeated_login.text
    with connect_db() as db:
        assert (
            db.execute("SELECT sign_count FROM passkeys WHERE user_id=?", (user_id,)).fetchone()[0]
            == 0
        )

    invalid_options = client.post("/api/passkeys/authentication/options").json()
    invalid_signature = authenticator.assertion(
        invalid_options["challenge"], handle, bad_signature=True
    )
    rejected = client.post(
        "/api/passkeys/authentication/verify", json={"credential": invalid_signature}
    )
    assert rejected.status_code == 401
    assert "token" not in rejected.json()


def test_passkey_rejects_non_ascii_challenge_without_internal_error(client):
    import base64

    credential = credential_json("ignored")
    client_data = json.dumps(
        {"type": "webauthn.get", "challenge": "żółć", "origin": "https://pecunianonolet.local"}
    ).encode()
    credential["response"]["clientDataJSON"] = (
        base64.urlsafe_b64encode(client_data).decode().rstrip("=")
    )
    credential.update({"id": "Y3JlZA", "rawId": "Y3JlZA", "type": "public-key"})
    response = client.post("/api/passkeys/authentication/verify", json={"credential": credential})
    assert response.status_code == 400


def test_discoverable_passkey_login_requires_matching_user_handle(client, monkeypatch):
    import app.routes.passkeys as route

    user_id, _ = make_user()
    with connect_db() as db, db:
        db.execute(
            "INSERT INTO passkeys(credential_id,user_id,public_key,sign_count,label,transports,created_at) VALUES (?,?,?,?,?,?,?)",
            ("Y3JlZA", user_id, b"pub", 0, "Laptop", "[]", 1),
        )
    options = client.post("/api/passkeys/authentication/options").json()
    credential = credential_json(options["challenge"])
    set_client_data_type(credential, "webauthn.get")
    credential.update({"id": "Y3JlZA", "rawId": "Y3JlZA", "type": "public-key"})
    credential["response"].update({"authenticatorData": "AA", "signature": "AA"})
    monkeypatch.setattr(route, "_rp_id", lambda: "pecunianonolet.local")
    monkeypatch.setattr(route, "_origins", lambda: ["https://pecunianonolet.local"])
    monkeypatch.setattr(
        "webauthn.verify_authentication_response",
        lambda **_: SimpleNamespace(new_sign_count=1),
    )
    response = client.post("/api/passkeys/authentication/verify", json={"credential": credential})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "client_data_patch",
    [
        {"crossOrigin": True, "topOrigin": "https://attacker.example"},
        {"crossOrigin": True},
        {"crossOrigin": False, "topOrigin": "https://attacker.example"},
    ],
)
def test_passkey_registration_rejects_cross_origin_client_data(
    client, monkeypatch, client_data_patch
):
    import base64

    import app.routes.passkeys as route

    _, token = make_user()
    headers = {"Authorization": f"Bearer {token}"}
    options = client.post("/api/passkeys/registration/options", headers=headers).json()
    credential = credential_json(options["challenge"])
    set_client_data_type(credential, "webauthn.create")
    client_data = {
        "type": "webauthn.create",
        "challenge": options["challenge"],
        "origin": "https://pecunianonolet.local",
        **client_data_patch,
    }
    credential["response"]["clientDataJSON"] = (
        base64.urlsafe_b64encode(json.dumps(client_data).encode()).decode().rstrip("=")
    )
    monkeypatch.setattr(route, "_rp_id", lambda: "pecunianonolet.local")
    monkeypatch.setattr(route, "_origins", lambda: ["https://pecunianonolet.local"])
    monkeypatch.setattr(
        "webauthn.verify_registration_response",
        lambda **_: SimpleNamespace(
            credential_id=b"test-credential",
            credential_public_key=b"public-key",
            sign_count=0,
        ),
    )
    response = client.post(
        "/api/passkeys/registration/verify",
        headers=headers,
        json={"credential": credential},
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "client_data_patch",
    [
        {"crossOrigin": True, "topOrigin": "https://attacker.example"},
        {"crossOrigin": True},
        {"crossOrigin": False, "topOrigin": "https://attacker.example"},
    ],
)
def test_passkey_authentication_rejects_cross_origin_client_data(client, client_data_patch):
    import base64

    options = client.post("/api/passkeys/authentication/options")
    assert options.status_code == 200
    credential = credential_json(options.json()["challenge"])
    client_data = {
        "type": "webauthn.get",
        "challenge": options.json()["challenge"],
        "origin": "https://pecunianonolet.local",
        **client_data_patch,
    }
    credential["response"]["clientDataJSON"] = (
        base64.urlsafe_b64encode(json.dumps(client_data).encode()).decode().rstrip("=")
    )

    response = client.post("/api/passkeys/authentication/verify", json={"credential": credential})
    assert response.status_code == 400


def test_google_identity_uses_stable_subject_after_email_change(client, monkeypatch):
    nonce = client.post("/api/auth/google/nonce").json()["nonce"]
    google_claims(
        monkeypatch,
        {
            "iss": "accounts.google.com",
            "sub": "stable-sub",
            "email": "first@gmail.com",
            "email_verified": True,
            "aud": "ios.apps.googleusercontent.com",
            "nonce": nonce,
        },
    )
    first = client.post(
        "/api/auth/google/login", json={"id_token": "signed-token-placeholder-long", "nonce": nonce}
    )
    assert first.status_code == 200
    nonce2 = client.post("/api/auth/google/nonce").json()["nonce"]
    google_claims(
        monkeypatch,
        {
            "iss": "https://accounts.google.com",
            "sub": "stable-sub",
            "email": "changed@gmail.com",
            "email_verified": True,
            "aud": "android.apps.googleusercontent.com",
            "nonce": nonce2,
        },
    )
    second = client.post(
        "/api/auth/google/login",
        json={"id_token": "signed-token-placeholder-long", "nonce": nonce2},
    )
    assert second.status_code == 200
    assert second.json()["user"]["email"] == "first@gmail.com"


def test_passkey_registration_options_require_fresh_auth_and_set_uv_rk(client, monkeypatch):
    from app.authorization import token_hash

    _user_id, token = make_user()
    response = client.post(
        "/api/passkeys/registration/options", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    options = response.json()
    assert options["rp"]["id"] == "pecunianonolet.local"
    assert options["authenticatorSelection"]["userVerification"] == "required"
    assert options["authenticatorSelection"]["residentKey"] == "required"
    with connect_db() as db:
        challenge = db.execute(
            "SELECT * FROM auth_challenges WHERE kind='passkey_register'"
        ).fetchone()
        assert challenge["challenge_value"] == options["challenge"]
        db.execute(
            "UPDATE auth_sessions SET authenticated_at=1 WHERE access_token_hash=?",
            (token_hash(token),),
        )
    stale = client.post(
        "/api/passkeys/registration/options", headers={"Authorization": f"Bearer {token}"}
    )
    assert stale.status_code == 401


def test_registration_verifies_fixed_rp_origin_and_uv_and_consumes_challenge(client, monkeypatch):
    import app.routes.passkeys as route

    _, token = make_user()
    headers = {"Authorization": f"Bearer {token}"}
    options = client.post("/api/passkeys/registration/options", headers=headers).json()
    credential = credential_json(options["challenge"])
    set_client_data_type(credential, "webauthn.create")
    call = {}

    def verify(**kwargs):
        call.update(kwargs)
        return SimpleNamespace(
            credential_id=b"test-credential", credential_public_key=b"public-key", sign_count=0
        )

    monkeypatch.setattr(route, "_rp_id", lambda: "pecunianonolet.local")
    monkeypatch.setattr(route, "_origins", lambda: ["https://pecunianonolet.local"])
    monkeypatch.setattr("webauthn.verify_registration_response", verify)
    body = {"credential": credential, "label": "iPhone"}
    created = client.post("/api/passkeys/registration/verify", headers=headers, json=body)
    assert created.status_code == 201, created.text
    assert call["expected_rp_id"] == "pecunianonolet.local"
    assert call["expected_origin"] == ["https://pecunianonolet.local"]
    assert call["require_user_verification"] is True
    assert (
        client.post("/api/passkeys/registration/verify", headers=headers, json=body).status_code
        == 400
    )
    with connect_db() as db:
        assert db.execute("SELECT count(*) FROM passkeys").fetchone()[0] == 1
        assert (
            db.execute(
                "SELECT count(*) FROM audit_events WHERE action='auth.passkey_registered'"
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT count(*) FROM auth_challenges WHERE kind='passkey_register'"
            ).fetchone()[0]
            == 0
        )


def test_passkey_registration_audit_failure_rolls_back_credential_and_challenge(
    client, monkeypatch
):
    from app.services import passkey_registration

    _, token = make_user()
    headers = {"Authorization": f"Bearer {token}"}
    options = client.post("/api/passkeys/registration/options", headers=headers).json()
    credential = credential_json(options["challenge"])
    set_client_data_type(credential, "webauthn.create")
    monkeypatch.setattr(
        "webauthn.verify_registration_response",
        lambda **_: SimpleNamespace(
            credential_id=b"test-credential", credential_public_key=b"public-key", sign_count=0
        ),
    )

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(passkey_registration, "write_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="audit write failed"):
        client.post(
            "/api/passkeys/registration/verify",
            headers=headers,
            json={"credential": credential},
        )
    with connect_db() as db:
        assert db.execute("SELECT count(*) FROM passkeys").fetchone()[0] == 0
        assert (
            db.execute(
                "SELECT count(*) FROM auth_challenges WHERE kind='passkey_register'"
            ).fetchone()[0]
            == 1
        )


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
    set_client_data_type(credential, "webauthn.get")
    credential["id"] = "Y3JlZA"
    credential["rawId"] = "Y3JlZA"
    with connect_db() as db:
        handle = db.execute(
            "SELECT webauthn_user_handle FROM users WHERE id=?", (user_id,)
        ).fetchone()[0]
    credential["response"].update(
        {
            "authenticatorData": "AA",
            "signature": "AA",
            "userHandle": base64.urlsafe_b64encode(handle).decode().rstrip("="),
        }
    )
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
    assert (
        client.post(
            "/api/passkeys/authentication/verify", json={"credential": credential}
        ).status_code
        == 401
    )
    with connect_db() as db:
        assert (
            db.execute("SELECT sign_count FROM passkeys WHERE credential_id='Y3JlZA'").fetchone()[0]
            == 1
        )


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
    assert (
        client.delete(endpoint, headers={"Authorization": f"Bearer {other_token}"}).status_code
        == 404
    )
    assert (
        client.delete(endpoint, headers={"Authorization": f"Bearer {owner_token}"}).status_code
        == 204
    )
    with connect_db() as db, db:
        assert (
            db.execute("SELECT count(*) FROM passkeys WHERE credential_id='owned-key'").fetchone()[
                0
            ]
            == 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM audit_events WHERE action='auth.passkey_deleted'"
            ).fetchone()[0]
            == 1
        )
        db.execute(
            "INSERT INTO passkeys(credential_id,user_id,public_key,sign_count,label,transports,created_at) VALUES (?,?,?,?,?,?,?)",
            ("stale-key", owner_id, b"pub", 0, "Device", "[]", 1),
        )
        db.execute(
            "UPDATE auth_sessions SET authenticated_at=1 WHERE access_token_hash=?",
            (token_hash(owner_token),),
        )
    assert (
        client.delete(
            "/api/passkeys/stale-key", headers={"Authorization": f"Bearer {owner_token}"}
        ).status_code
        == 401
    )


def test_local_association_documents_are_served_for_ios_and_android(client):
    aasa = client.get("/.well-known/apple-app-site-association")
    links = client.get("/.well-known/assetlinks.json")
    assert aasa.status_code == links.status_code == 200
    assert aasa.json()["webcredentials"]["apps"] == ["96UM85TJJ7.com.rajda.pecunianonolet"]
    assert links.json()[0]["target"]["package_name"] == "com.pecunianonolet"
    assert links.headers["Cache-Control"] == "no-store"


def test_google_reauthentication_requires_bound_challenge_matching_identity_and_fresh_auth_time(
    client, monkeypatch
):
    from app.authorization import token_hash

    user_id, token = make_user("reauth@example.com")
    _, other_token = make_user("other-reauth@example.com")
    with connect_db() as db, db:
        db.execute(
            """INSERT INTO oauth_identities(
                   user_id,provider,issuer,subject,email_at_link,created_at
               ) VALUES (?,'google','https://accounts.google.com','linked-subject',?,?)""",
            (user_id, "reauth@example.com", int(time.time())),
        )
        db.execute(
            "UPDATE auth_sessions SET authenticated_at=1 WHERE access_token_hash=?",
            (token_hash(token),),
        )
    headers = {"Authorization": f"Bearer {token}"}
    nonce_response = client.post("/api/auth/google/reauth/nonce", headers=headers)
    assert nonce_response.status_code == 200
    assert client.post("/api/passkeys/registration/options", headers=headers).status_code == 401
    nonce = nonce_response.json()["nonce"]
    payload = {"id_token": "signed-token-placeholder-long", "nonce": nonce}
    assert (
        client.post(
            "/api/auth/google/reauth",
            headers={"Authorization": f"Bearer {other_token}"},
            json=payload,
        ).status_code
        == 401
    )

    claims = {
        "iss": "https://accounts.google.com",
        "sub": "linked-subject",
        "email": "reauth@example.com",
        "email_verified": True,
        "aud": "ios.apps.googleusercontent.com",
        "nonce": nonce,
        "auth_time": int(time.time()) - 600,
    }
    google_claims(monkeypatch, claims)
    assert client.post("/api/auth/google/reauth", headers=headers, json=payload).status_code == 401
    claims.pop("auth_time")
    assert client.post("/api/auth/google/reauth", headers=headers, json=payload).status_code == 401
    claims["auth_time"] = "invalid"
    assert client.post("/api/auth/google/reauth", headers=headers, json=payload).status_code == 401
    claims["auth_time"] = int(time.time())
    claims["sub"] = "different-subject"
    assert client.post("/api/auth/google/reauth", headers=headers, json=payload).status_code == 401
    claims["sub"] = "linked-subject"
    reauthenticated = client.post("/api/auth/google/reauth", headers=headers, json=payload)
    assert reauthenticated.status_code == 200
    new_session = reauthenticated.json()
    assert new_session["access_token"] != token
    assert new_session["refresh_token"]
    assert client.get("/api/me", headers=headers).status_code == 401
    assert client.post("/api/passkeys/registration/options", headers=headers).status_code == 401
    new_headers = {"Authorization": f"Bearer {new_session['access_token']}"}
    assert client.post("/api/passkeys/registration/options", headers=new_headers).status_code == 200
    assert client.post("/api/auth/google/reauth", headers=headers, json=payload).status_code == 401
    with connect_db() as db:
        row = db.execute(
            """SELECT authentication_method,provider_authenticated_at
               FROM auth_sessions WHERE access_token_hash=?""",
            (token_hash(new_session["access_token"]),),
        ).fetchone()
        assert row["authentication_method"] == "google"
        assert abs(row["provider_authenticated_at"] - int(time.time())) <= 5


def test_google_reauthentication_rolls_back_revocation_if_new_session_cannot_be_saved(
    client, monkeypatch
):
    user_id, token = make_user("rollback-reauth@example.com")
    with connect_db() as db, db:
        db.execute(
            """INSERT INTO oauth_identities(
                   user_id,provider,issuer,subject,email_at_link,created_at
               ) VALUES (?,'google','https://accounts.google.com','rollback-subject',?,?)""",
            (user_id, "rollback-reauth@example.com", int(time.time())),
        )
    headers = {"Authorization": f"Bearer {token}"}
    nonce = client.post("/api/auth/google/reauth/nonce", headers=headers).json()["nonce"]
    google_claims(
        monkeypatch,
        {
            "iss": "https://accounts.google.com",
            "sub": "rollback-subject",
            "email": "rollback-reauth@example.com",
            "email_verified": True,
            "aud": "ios.apps.googleusercontent.com",
            "nonce": nonce,
            "auth_time": int(time.time()),
        },
    )
    with connect_db() as db, db:
        db.execute(
            """CREATE TRIGGER fail_reauth_session BEFORE INSERT ON auth_sessions
               BEGIN SELECT RAISE(ABORT, 'forced session write failure'); END"""
        )
    payload = {"id_token": "signed-token-placeholder-long", "nonce": nonce}
    with pytest.raises(sqlite3.IntegrityError, match="forced session write failure"):
        client.post("/api/auth/google/reauth", headers=headers, json=payload)
    assert client.get("/api/me", headers=headers).status_code == 200
    with connect_db() as db, db:
        db.execute("DROP TRIGGER fail_reauth_session")
    assert client.post("/api/auth/google/reauth", headers=headers, json=payload).status_code == 200
