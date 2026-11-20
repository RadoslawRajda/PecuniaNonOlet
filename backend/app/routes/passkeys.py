"""WebAuthn passkey registration and authentication using the py_webauthn verifier."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import closing
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.authorization import current_session, token_hash
from app.database import connect_db
from app.schemas import AuthResponse, LoginResponse, User
from app.sessions import issue_token

router = APIRouter(prefix="/api/passkeys", tags=["passkeys"])
CHALLENGE_TTL = 300
RECENT_AUTH_SECONDS = 300
AuthenticatedSession = Annotated[tuple[str, User], Depends(current_session)]


class CredentialBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential: dict[str, Any]
    label: str = Field(default="Passkey", min_length=1, max_length=80)

    @field_validator("credential")
    @classmethod
    def bound_credential(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, separators=(",", ":"), ensure_ascii=True)) > 24_000:
            raise ValueError("Credential payload is too large")
        return value

    @field_validator("label")
    @classmethod
    def nonblank_label(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Label cannot be empty")
        return value.strip()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _rp_id() -> str:
    value = os.getenv("WEBAUTHN_RP_ID", "pecunianonolet.local").strip().lower()
    if not value or ":" in value or "/" in value or value.startswith("."):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Passkeys nie są skonfigurowane.")
    return value


def _origins() -> list[str]:
    default_origins = (
        "https://pecunianonolet.local,https://pecunianonolet.local:8000,"
        "android:apk-key-hash:-sYXRdwJA3hvue3mKpYrOZ9zSPC7b4mbgzJmdZEDO5w"
    )
    values = [item.strip() for item in os.getenv("WEBAUTHN_ALLOWED_ORIGINS", default_origins).split(",") if item.strip()]
    if not values:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Passkeys nie są skonfigurowane.")
    return values


def _fresh_session(db: sqlite3.Connection, session_token: str, user_id: int, now: int) -> None:
    row = db.execute(
        "SELECT authenticated_at FROM sessions WHERE token_hash=? AND user_id=? AND expires_at>?",
        (token_hash(session_token), user_id, now),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")
    if now - row["authenticated_at"] > RECENT_AUTH_SECONDS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Zaloguj się ponownie przed zarządzaniem passkeys.")


def _new_challenge(db: sqlite3.Connection, kind: str, user_id: int | None, value: str) -> None:
    now = int(time.time())
    db.execute("DELETE FROM auth_challenges WHERE expires_at<=?", (now,))
    db.execute(
        "INSERT INTO auth_challenges(challenge_hash,kind,challenge_value,user_id,created_at,expires_at) VALUES (?,?,?,?,?,?)",
        (_digest(value), kind, value, user_id, now, now + CHALLENGE_TTL),
    )


def _consume_challenge(db: sqlite3.Connection, kind: str, value: str, user_id: int | None = None) -> None:
    row = db.execute(
        "SELECT user_id FROM auth_challenges WHERE challenge_hash=? AND kind=? AND challenge_value=? AND expires_at>?",
        (_digest(value), kind, value, int(time.time())),
    ).fetchone()
    if row is None or row["user_id"] != user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Wyzwanie passkey wygasło lub zostało już użyte.")
    db.execute("DELETE FROM auth_challenges WHERE challenge_hash=?", (_digest(value),))


def _challenge_from_client(credential: dict[str, Any]) -> str:
    try:
        from webauthn.helpers import base64url_to_bytes
        client_data = json.loads(base64url_to_bytes(credential["response"]["clientDataJSON"]))
        value = client_data["challenge"]
        if not isinstance(value, str) or len(value) > 128:
            raise ValueError
        return value
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nieprawidłowe poświadczenie passkey.") from None


@router.get("")
def list_passkeys(session: AuthenticatedSession) -> list[dict[str, object]]:
    _, user = session
    with closing(connect_db()) as db:
        rows = db.execute(
            "SELECT credential_id,label,created_at,last_used_at,transports FROM passkeys WHERE user_id=? ORDER BY created_at DESC",
            (user.id,),
        ).fetchall()
    return [
        {"id": row["credential_id"], "label": row["label"], "created_at": row["created_at"],
         "last_used_at": row["last_used_at"], "transports": json.loads(row["transports"])}
        for row in rows
    ]


@router.post("/registration/options")
def registration_options(session: AuthenticatedSession) -> dict[str, object]:
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers import base64url_to_bytes
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    session_token, user = session
    now = int(time.time())
    rp_id = _rp_id()
    with closing(connect_db()) as db, db:
        _fresh_session(db, session_token, user.id, now)
        existing = db.execute("SELECT credential_id,transports FROM passkeys WHERE user_id=?", (user.id,)).fetchall()
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name="Pecunia non olet",
            user_id=user.id.to_bytes(8, "big"),
            user_name=user.email,
            user_display_name=user.email,
            exclude_credentials=[
                PublicKeyCredentialDescriptor(
                    id=base64url_to_bytes(item["credential_id"]),
                    transports=json.loads(item["transports"]),
                ) for item in existing
            ],
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        serialized = json.loads(options_to_json(options))
        _new_challenge(db, "passkey_register", user.id, serialized["challenge"])
    return serialized


@router.post("/registration/verify", status_code=201)
def registration_verify(payload: CredentialBody, session: AuthenticatedSession) -> dict[str, object]:
    from webauthn import verify_registration_response
    from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
    from webauthn.helpers.exceptions import WebAuthnException

    session_token, user = session
    credential = payload.credential
    challenge = _challenge_from_client(credential)
    now = int(time.time())
    with closing(connect_db()) as db:
        pending = db.execute(
            "SELECT 1 FROM auth_challenges WHERE challenge_hash=? AND kind='passkey_register' AND challenge_value=? AND user_id=? AND expires_at>?",
            (_digest(challenge), challenge, user.id, now),
        ).fetchone()
    if pending is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Wyzwanie passkey wygasło lub zostało już użyte.")
    try:
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=_rp_id(),
            expected_origin=_origins(),
            require_user_verification=True,
        )
    except (TypeError, ValueError, KeyError, WebAuthnException):
        _discard_challenge("passkey_register", challenge, user.id)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rejestracja passkey nie powiodła się.") from None
    credential_id = bytes_to_base64url(verification.credential_id)
    transports = credential.get("response", {}).get("transports", [])
    if not isinstance(transports, list) or any(not isinstance(item, str) or len(item) > 32 for item in transports):
        transports = []
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        _fresh_session(db, session_token, user.id, now)
        _consume_challenge(db, "passkey_register", challenge, user.id)
        try:
            db.execute(
                "INSERT INTO passkeys(credential_id,user_id,public_key,sign_count,label,transports,created_at) VALUES (?,?,?,?,?,?,?)",
                (credential_id, user.id, verification.credential_public_key, verification.sign_count,
                 payload.label.strip(), json.dumps(transports), now),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status.HTTP_409_CONFLICT, "Ta passkey jest już zarejestrowana.") from None
    return {"id": credential_id, "label": payload.label.strip(), "created_at": now}


def _discard_challenge(kind: str, value: str, user_id: int) -> None:
    with closing(connect_db()) as db, db:
        db.execute("DELETE FROM auth_challenges WHERE challenge_hash=? AND kind=? AND user_id=?", (_digest(value), kind, user_id))


@router.post("/authentication/options")
def authentication_options() -> dict[str, object]:
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import UserVerificationRequirement

    options = generate_authentication_options(
        rp_id=_rp_id(),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    serialized = json.loads(options_to_json(options))
    with closing(connect_db()) as db, db:
        _new_challenge(db, "passkey_login", None, serialized["challenge"])
    return serialized


@router.post("/authentication/verify", response_model=LoginResponse)
def authentication_verify(payload: CredentialBody) -> LoginResponse:
    from webauthn import verify_authentication_response
    from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
    from webauthn.helpers.exceptions import WebAuthnException

    credential = payload.credential
    challenge = _challenge_from_client(credential)
    credential_id = credential.get("id")
    raw_id = credential.get("rawId")
    try:
        from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

        if not isinstance(raw_id, str) or len(raw_id) > 1024:
            raise ValueError
        normalized_raw_id = bytes_to_base64url(base64url_to_bytes(raw_id))
    except (TypeError, ValueError):
        normalized_raw_id = ""
    if not isinstance(credential_id, str) or len(credential_id) > 1024 or credential_id != normalized_raw_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nie udało się uwierzytelnić passkey.")
    now = int(time.time())
    with closing(connect_db()) as read_db:
        challenge_row = read_db.execute(
            "SELECT 1 FROM auth_challenges WHERE challenge_hash=? AND kind='passkey_login' AND challenge_value=? AND user_id IS NULL AND expires_at>?",
            (_digest(challenge), challenge, now),
        ).fetchone()
        row = read_db.execute("SELECT * FROM passkeys WHERE credential_id=?", (credential_id,)).fetchone()
    if challenge_row is None or row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nie udało się uwierzytelnić passkey.")
    user_handle = credential.get("response", {}).get("userHandle")
    if user_handle is not None:
        try:
            if base64url_to_bytes(user_handle) != row["user_id"].to_bytes(8, "big"):
                raise ValueError
        except (TypeError, ValueError):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nie udało się uwierzytelnić passkey.") from None
    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=_rp_id(),
            expected_origin=_origins(),
            credential_public_key=row["public_key"],
            credential_current_sign_count=row["sign_count"],
            require_user_verification=True,
        )
    except (TypeError, ValueError, KeyError, WebAuthnException):
        _discard_login_challenge(challenge)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nie udało się uwierzytelnić passkey.") from None
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("SELECT sign_count,user_id FROM passkeys WHERE credential_id=?", (credential_id,)).fetchone()
        live = db.execute(
            "SELECT 1 FROM auth_challenges WHERE challenge_hash=? AND kind='passkey_login' AND expires_at>?",
            (_digest(challenge), int(time.time())),
        ).fetchone()
        if current is None or current["user_id"] != row["user_id"] or current["sign_count"] != row["sign_count"] or live is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nie udało się uwierzytelnić passkey.")
        db.execute("DELETE FROM auth_challenges WHERE challenge_hash=?", (_digest(challenge),))
        db.execute(
            "UPDATE passkeys SET sign_count=?,last_used_at=? WHERE credential_id=?",
            (verification.new_sign_count, int(time.time()), credential_id),
        )
        mfa = db.execute("SELECT enabled_at FROM user_totp WHERE user_id=?", (row["user_id"],)).fetchone()
        if mfa and mfa["enabled_at"] is not None:
            from app.routes.mfa import create_login_challenge

            return create_login_challenge(db, row["user_id"])
        user_row = db.execute(
            "SELECT u.id,u.email,r.role_name FROM users u JOIN user_roles r ON r.user_id=u.id WHERE u.id=?",
            (row["user_id"],),
        ).fetchone()
        return AuthResponse(
            user=User(id=user_row["id"], email=user_row["email"], role=user_row["role_name"]),
            token=issue_token(db, row["user_id"]),
        )


def _discard_login_challenge(value: str) -> None:
    with closing(connect_db()) as db, db:
        db.execute("DELETE FROM auth_challenges WHERE challenge_hash=? AND kind='passkey_login'", (_digest(value),))


@router.delete("/{credential_id}", status_code=204)
def delete_passkey(credential_id: str, session: AuthenticatedSession) -> Response:
    session_token, user = session
    now = int(time.time())
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        _fresh_session(db, session_token, user.id, now)
        deleted = db.execute("DELETE FROM passkeys WHERE credential_id=? AND user_id=?", (credential_id, user.id))
        if deleted.rowcount == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono passkey.")
    return Response(status_code=204)
