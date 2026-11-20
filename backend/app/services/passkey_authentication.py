"""Verify a WebAuthn assertion and complete or continue the user's login."""

from __future__ import annotations

import binascii
import hashlib
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from app.database import connect_db
from app.schemas import AuthResponse, LoginResponse, User
from app.services.authentication import claim_auth_challenge_attempt, create_login_challenge
from app.sessions import issue_session


@dataclass(frozen=True, slots=True)
class StoredPasskey:
    credential_id: str
    user_id: int
    public_key: bytes
    sign_count: int


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _authentication_failed() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Nie udało się uwierzytelnić passkey.")


def _discard_login_challenge(value: str) -> None:
    with closing(connect_db()) as db, db:
        db.execute(
            "DELETE FROM auth_challenges WHERE challenge_hash=? AND kind='passkey_login'",
            (_digest(value),),
        )


def _credential_id(credential: dict[str, Any], challenge: str) -> str:
    from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

    credential_id = credential.get("id")
    raw_id = credential.get("rawId")
    try:
        if not isinstance(raw_id, str) or len(raw_id) > 1024:
            raise ValueError
        normalized = bytes_to_base64url(base64url_to_bytes(raw_id))
    except (TypeError, ValueError, binascii.Error):
        normalized = ""
    if (
        not isinstance(credential_id, str)
        or len(credential_id) > 1024
        or credential_id != normalized
    ):
        _discard_login_challenge(challenge)
        raise _authentication_failed()
    return credential_id


def _claim_attempt_and_load_passkey(challenge: str, credential_id: str) -> StoredPasskey:
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        now = int(time.time())
        allowed = claim_auth_challenge_attempt(db, "passkey_login", challenge, now=now)
        live = (
            db.execute(
                """SELECT 1 FROM auth_challenges
                   WHERE challenge_hash=? AND kind='passkey_login'
                     AND challenge_value=? AND user_id IS NULL AND expires_at>?""",
                (_digest(challenge), challenge, now),
            ).fetchone()
            if allowed
            else None
        )
        row = (
            db.execute("SELECT * FROM passkeys WHERE credential_id=?", (credential_id,)).fetchone()
            if live is not None
            else None
        )
    if live is None or row is None:
        raise _authentication_failed()
    return StoredPasskey(
        credential_id=credential_id,
        user_id=row["user_id"],
        public_key=row["public_key"],
        sign_count=row["sign_count"],
    )


def _require_matching_user_handle(
    credential: dict[str, Any], passkey: StoredPasskey, challenge: str
) -> None:
    from webauthn.helpers import base64url_to_bytes

    handle = credential.get("response", {}).get("userHandle")
    try:
        if not isinstance(handle, str) or not handle:
            raise ValueError
        with closing(connect_db()) as db:
            row = db.execute(
                "SELECT webauthn_user_handle FROM users WHERE id=?", (passkey.user_id,)
            ).fetchone()
        if row is None or not isinstance(row["webauthn_user_handle"], bytes):
            raise ValueError
        if base64url_to_bytes(handle) != row["webauthn_user_handle"]:
            raise ValueError
    except (TypeError, ValueError, binascii.Error):
        _discard_login_challenge(challenge)
        raise _authentication_failed() from None


def _verify_assertion(
    credential: dict[str, Any],
    challenge: str,
    passkey: StoredPasskey,
    rp_id: str,
    origins: list[str],
) -> int:
    from webauthn import verify_authentication_response
    from webauthn.helpers import base64url_to_bytes
    from webauthn.helpers.exceptions import WebAuthnException

    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=rp_id,
            expected_origin=origins,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except (TypeError, ValueError, KeyError, WebAuthnException):
        _discard_login_challenge(challenge)
        raise _authentication_failed() from None
    return verification.new_sign_count


def _finish_authentication(
    db: sqlite3.Connection, challenge: str, passkey: StoredPasskey, new_sign_count: int
) -> LoginResponse:
    current = db.execute(
        "SELECT sign_count,user_id FROM passkeys WHERE credential_id=?", (passkey.credential_id,)
    ).fetchone()
    live = db.execute(
        """SELECT 1 FROM auth_challenges
           WHERE challenge_hash=? AND kind='passkey_login' AND expires_at>?""",
        (_digest(challenge), int(time.time())),
    ).fetchone()
    if (
        current is None
        or current["user_id"] != passkey.user_id
        or current["sign_count"] != passkey.sign_count
        or live is None
    ):
        raise _authentication_failed()
    db.execute("DELETE FROM auth_challenges WHERE challenge_hash=?", (_digest(challenge),))
    db.execute(
        "UPDATE passkeys SET sign_count=?,last_used_at=? WHERE credential_id=?",
        (new_sign_count, int(time.time()), passkey.credential_id),
    )
    mfa = db.execute(
        "SELECT enabled_at FROM user_totp WHERE user_id=?", (passkey.user_id,)
    ).fetchone()
    if mfa and mfa["enabled_at"] is not None:
        return create_login_challenge(db, passkey.user_id, authentication_method="passkey")
    identity = db.execute(
        """SELECT u.id,u.email,r.role_name FROM users u
           JOIN user_roles r ON r.user_id=u.id WHERE u.id=?""",
        (passkey.user_id,),
    ).fetchone()
    if identity is None:
        raise _authentication_failed()
    tokens = issue_session(db, passkey.user_id, authentication_method="passkey")
    return AuthResponse(
        user=User(id=identity["id"], email=identity["email"], role=identity["role_name"]),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        refresh_expires_in=tokens.refresh_expires_in,
    )


def authenticate_passkey(
    credential: dict[str, Any], challenge: str, *, rp_id: str, origins: list[str]
) -> LoginResponse:
    """Verify assertion and issue a session or MFA challenge, consuming one login challenge.

    The first transaction counts attempts; signature verification runs outside the
    write lock. The second transaction checks sign count and challenge again before
    the passkey update and session/MFA challenge commit together.
    """
    credential_id = _credential_id(credential, challenge)
    passkey = _claim_attempt_and_load_passkey(challenge, credential_id)
    _require_matching_user_handle(credential, passkey, challenge)
    new_sign_count = _verify_assertion(credential, challenge, passkey, rp_id, origins)
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        return _finish_authentication(db, challenge, passkey, new_sign_count)
