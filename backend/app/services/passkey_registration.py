"""Verify and persist a new WebAuthn credential for an authenticated owner."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from app.audit import write_audit_event
from app.authorization import AuthenticatedSession
from app.database import connect_db
from app.services.authentication import assert_recent_authentication


@dataclass(frozen=True, slots=True)
class RegisteredPasskey:
    credential_id: str
    label: str
    created_at: int


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _require_pending_registration(
    db: sqlite3.Connection, challenge: str, user_id: int, session_id: str, now: int
) -> None:
    pending = db.execute(
        """SELECT session_hash FROM auth_challenges
           WHERE challenge_hash=? AND kind='passkey_register' AND challenge_value=?
             AND user_id=? AND expires_at>?""",
        (_digest(challenge), challenge, user_id, now),
    ).fetchone()
    if pending is None or pending["session_hash"] != session_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Wyzwanie passkey wygasło lub zostało już użyte."
        )


def _discard_failed_registration(challenge: str, user_id: int) -> None:
    with closing(connect_db()) as db, db:
        db.execute(
            """DELETE FROM auth_challenges
               WHERE challenge_hash=? AND kind='passkey_register' AND user_id=?""",
            (_digest(challenge), user_id),
        )


def _transports(credential: dict[str, Any]) -> list[str]:
    value = credential.get("response", {}).get("transports", [])
    if not isinstance(value, list) or any(
        not isinstance(item, str) or len(item) > 32 for item in value
    ):
        return []
    return value


def _commit_registration(
    db: sqlite3.Connection,
    session: AuthenticatedSession,
    challenge: str,
    credential_id: str,
    public_key: bytes,
    sign_count: int,
    label: str,
    transports: list[str],
    now: int,
) -> None:
    user = session.user
    assert_recent_authentication(db, session.session_id, user.id, now=now)
    _require_pending_registration(db, challenge, user.id, session.session_id, int(time.time()))
    db.execute("DELETE FROM auth_challenges WHERE challenge_hash=?", (_digest(challenge),))
    try:
        db.execute(
            """INSERT INTO passkeys(
                credential_id,user_id,public_key,sign_count,label,transports,created_at
            ) VALUES (?,?,?,?,?,?,?)""",
            (credential_id, user.id, public_key, sign_count, label, json.dumps(transports), now),
        )
        write_audit_event(
            db,
            actor_user_id=user.id,
            actor_role=user.role,
            action="auth.passkey_registered",
            entity_type="user",
            entity_id=str(user.id),
            details={"authenticator_key_hash": hashlib.sha256(credential_id.encode()).hexdigest()},
            created_at=now,
        )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ta passkey jest już zarejestrowana."
        ) from None


def register_passkey(
    session: AuthenticatedSession,
    credential: dict[str, Any],
    challenge: str,
    label: str,
    *,
    rp_id: str,
    origins: list[str],
) -> RegisteredPasskey:
    """Verify signature, RP, origin and UV, then consume the session-bound challenge.

    Cryptographic verification happens before the write lock. The transaction repeats
    the current-session and challenge checks before inserting the passkey and audit.
    """
    from webauthn import verify_registration_response
    from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
    from webauthn.helpers.exceptions import WebAuthnException

    now = int(time.time())
    with closing(connect_db()) as db:
        _require_pending_registration(db, challenge, session.user.id, session.session_id, now)
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=rp_id,
            expected_origin=origins,
            require_user_verification=True,
        )
    except (TypeError, ValueError, KeyError, WebAuthnException):
        _discard_failed_registration(challenge, session.user.id)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Rejestracja passkey nie powiodła się."
        ) from None
    credential_id = bytes_to_base64url(verified.credential_id)
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        _commit_registration(
            db,
            session,
            challenge,
            credential_id,
            verified.credential_public_key,
            verified.sign_count,
            label,
            _transports(credential),
            now,
        )
    return RegisteredPasskey(credential_id, label, now)
