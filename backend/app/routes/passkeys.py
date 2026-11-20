"""WebAuthn passkey registration and authentication using the py_webauthn verifier."""

from __future__ import annotations

import binascii
import hashlib
import json
import re
import sqlite3
import time
from contextlib import closing
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.audit import write_audit_event
from app.authorization import AuthenticatedSession, current_session
from app.config import load_settings
from app.database import connect_db
from app.rate_limits import client_ip, enforce_rate_limit, ip_bucket
from app.schemas import LoginResponse
from app.services.authentication import (
    assert_recent_authentication,
)
from app.services.passkey_authentication import authenticate_passkey
from app.services.passkey_registration import register_passkey

router = APIRouter(prefix="/api/passkeys", tags=["passkeys"])
CHALLENGE_TTL = 300
RECENT_AUTH_SECONDS = 300
WEBAUTHN_CHALLENGE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{22,86}$")
Authenticated = Annotated[AuthenticatedSession, Depends(current_session)]


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


class PasskeyAssertionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential: dict[str, Any]

    @field_validator("credential")
    @classmethod
    def bound_credential(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, separators=(",", ":"), ensure_ascii=True)) > 24_000:
            raise ValueError("Credential payload is too large")
        return value


class PasskeySummary(BaseModel):
    id: str
    label: str
    created_at: int
    last_used_at: int | None
    transports: list[str]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _rp_id() -> str:
    value = load_settings().webauthn_rp_id.strip().lower()
    if not value or ":" in value or "/" in value or value.startswith("."):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Passkeys nie są skonfigurowane.")
    return value


def _origins() -> list[str]:
    default_origins = (
        "https://pecunianonolet.local,https://pecunianonolet.local:8000,"
        "android:apk-key-hash:-sYXRdwJA3hvue3mKpYrOZ9zSPC7b4mbgzJmdZEDO5w"
    )
    values = [
        item.strip()
        for item in (load_settings().webauthn_allowed_origins or default_origins).split(",")
        if item.strip()
    ]
    if not values:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Passkeys nie są skonfigurowane.")
    return values


def _fresh_session(db: sqlite3.Connection, session_id: str, user_id: int, now: int) -> None:
    assert_recent_authentication(db, session_id, user_id, now=now)


def _new_challenge(
    db: sqlite3.Connection,
    kind: str,
    user_id: int | None,
    value: str,
    session_digest: str | None = None,
) -> None:
    now = int(time.time())
    db.execute("DELETE FROM auth_challenges WHERE expires_at<=?", (now,))
    db.execute(
        "INSERT INTO auth_challenges(challenge_hash,kind,challenge_value,user_id,created_at,expires_at,session_hash) VALUES (?,?,?,?,?,?,?)",
        (_digest(value), kind, value, user_id, now, now + CHALLENGE_TTL, session_digest),
    )


def _consume_challenge(
    db: sqlite3.Connection, kind: str, value: str, user_id: int | None = None
) -> None:
    row = db.execute(
        "SELECT user_id FROM auth_challenges WHERE challenge_hash=? AND kind=? AND challenge_value=? AND expires_at>?",
        (_digest(value), kind, value, int(time.time())),
    ).fetchone()
    if row is None or row["user_id"] != user_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Wyzwanie passkey wygasło lub zostało już użyte."
        )
    db.execute("DELETE FROM auth_challenges WHERE challenge_hash=?", (_digest(value),))


def _user_handle(db: sqlite3.Connection, user_id: int) -> bytes:
    row = db.execute("SELECT webauthn_user_handle FROM users WHERE id=?", (user_id,)).fetchone()
    if row is None or not isinstance(row["webauthn_user_handle"], bytes):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Passkeys nie są skonfigurowane.")
    return row["webauthn_user_handle"]


def _challenge_from_client(credential: dict[str, Any], expected_type: str) -> str:
    """Parse only first-party client data before using challenge bytes in persistence."""
    try:
        from webauthn.helpers import base64url_to_bytes

        encoded_data = credential["response"]["clientDataJSON"]
        client_data = json.loads(base64url_to_bytes(encoded_data))
        if not isinstance(client_data, dict) or client_data.get("type") != expected_type:
            raise ValueError
        value = client_data["challenge"]
        if not isinstance(value, str) or not WEBAUTHN_CHALLENGE_PATTERN.fullmatch(value):
            raise ValueError
        decoded_challenge = base64url_to_bytes(value)
        if not 16 <= len(decoded_challenge) <= 64:
            raise ValueError
        if client_data.get("crossOrigin", False) is not False or "topOrigin" in client_data:
            raise ValueError
        return value
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, binascii.Error):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Nieprawidłowe poświadczenie passkey."
        ) from None


@router.get("")
def list_passkeys(session: Authenticated) -> list[PasskeySummary]:
    user = session.user
    with closing(connect_db()) as db:
        rows = db.execute(
            "SELECT credential_id,label,created_at,last_used_at,transports FROM passkeys WHERE user_id=? ORDER BY created_at DESC",
            (user.id,),
        ).fetchall()
    return [
        PasskeySummary(
            id=row["credential_id"],
            label=row["label"],
            created_at=row["created_at"],
            last_used_at=row["last_used_at"],
            transports=json.loads(row["transports"]),
        )
        for row in rows
    ]


@router.post("/registration/options")
def registration_options(session: Authenticated, request: Request) -> dict[str, object]:
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers import base64url_to_bytes
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    user = session.user
    enforce_rate_limit(
        [
            ip_bucket(
                "passkey_registration", client_ip(request.client.host if request.client else None)
            )
        ]
    )
    now = int(time.time())
    rp_id = _rp_id()
    with closing(connect_db()) as db, db:
        _fresh_session(db, session.session_id, user.id, now)
        existing = db.execute(
            "SELECT credential_id,transports FROM passkeys WHERE user_id=?", (user.id,)
        ).fetchall()
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name="Pecunia non olet",
            user_id=_user_handle(db, user.id),
            user_name=user.email,
            user_display_name=user.email,
            exclude_credentials=[
                PublicKeyCredentialDescriptor(
                    id=base64url_to_bytes(item["credential_id"]),
                    transports=json.loads(item["transports"]),
                )
                for item in existing
            ],
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        serialized = json.loads(options_to_json(options))
        _new_challenge(db, "passkey_register", user.id, serialized["challenge"], session.session_id)
    return serialized


@router.post("/registration/verify", status_code=201)
def registration_verify(
    payload: CredentialBody, session: Authenticated, request: Request
) -> dict[str, object]:
    enforce_rate_limit(
        [
            ip_bucket(
                "passkey_registration_verify",
                client_ip(request.client.host if request.client else None),
            )
        ]
    )
    challenge = _challenge_from_client(payload.credential, "webauthn.create")
    result = register_passkey(
        session,
        payload.credential,
        challenge,
        payload.label,
        rp_id=_rp_id(),
        origins=_origins(),
    )
    return {"id": result.credential_id, "label": result.label, "created_at": result.created_at}


@router.post("/authentication/options")
def authentication_options(request: Request) -> dict[str, object]:
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import UserVerificationRequirement

    enforce_rate_limit(
        [ip_bucket("passkey_options", client_ip(request.client.host if request.client else None))]
    )
    options = generate_authentication_options(
        rp_id=_rp_id(),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    serialized = json.loads(options_to_json(options))
    with closing(connect_db()) as db, db:
        _new_challenge(db, "passkey_login", None, serialized["challenge"])
    return serialized


@router.post("/authentication/verify", response_model=LoginResponse)
def authentication_verify(payload: PasskeyAssertionBody, request: Request) -> LoginResponse:
    enforce_rate_limit(
        [ip_bucket("passkey_verify", client_ip(request.client.host if request.client else None))]
    )
    challenge = _challenge_from_client(payload.credential, "webauthn.get")
    return authenticate_passkey(payload.credential, challenge, rp_id=_rp_id(), origins=_origins())


@router.delete("/{credential_id}", status_code=204)
def delete_passkey(credential_id: str, session: Authenticated) -> Response:
    user = session.user
    now = int(time.time())
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        _fresh_session(db, session.session_id, user.id, now)
        methods = db.execute(
            """SELECT u.has_local_password,
                      EXISTS(SELECT 1 FROM oauth_identities WHERE user_id=u.id) AS has_google,
                      (SELECT count(*) FROM passkeys WHERE user_id=u.id AND credential_id<>?)
                          AS other_passkeys
               FROM users u WHERE u.id=?""",
            (credential_id, user.id),
        ).fetchone()
        if (
            methods is not None
            and not methods["has_local_password"]
            and not methods["has_google"]
            and methods["other_passkeys"] == 0
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Dodaj inną metodę logowania przed usunięciem ostatniej passkey.",
            )
        deleted = db.execute(
            "DELETE FROM passkeys WHERE credential_id=? AND user_id=?", (credential_id, user.id)
        )
        if deleted.rowcount == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono passkey.")
        write_audit_event(
            db,
            actor_user_id=user.id,
            actor_role=user.role,
            action="auth.passkey_deleted",
            entity_type="user",
            entity_id=str(user.id),
            details={"authenticator_key_hash": hashlib.sha256(credential_id.encode()).hexdigest()},
            created_at=now,
        )
    return Response(status_code=204)
