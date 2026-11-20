"""Shared authentication workflows used by password, Google and passkey routes."""

from __future__ import annotations

import sqlite3
import time
from hashlib import sha256

from fastapi import HTTPException, status

from app.schemas import MfaLoginChallengeResponse
from app.totp import (
    LOGIN_CHALLENGE_LIFETIME_SECONDS,
    challenge_hash,
    new_challenge,
)

MAX_AUTH_CHALLENGE_ATTEMPTS = 5


def current_timestamp() -> int:
    """Return epoch seconds; kept as a seam for deterministic auth-flow tests."""
    return int(time.time())


def assert_recent_authentication(
    db: sqlite3.Connection, session_id: str, user_id: int, *, now: int
) -> None:
    """Require recent evidence from the method that actually authenticated the session."""
    row = db.execute(
        """SELECT authenticated_at,authentication_method,provider_authenticated_at
           FROM auth_sessions WHERE user_id=? AND session_id=? AND access_expires_at>?
             AND refresh_expires_at>? AND absolute_expires_at>? AND revoked_at IS NULL""",
        (user_id, session_id, now, now, now),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")

    method = row["authentication_method"]
    evidence_time = (
        row["provider_authenticated_at"] if method == "google" else row["authenticated_at"]
    )
    if method not in {"password", "google", "passkey"} or evidence_time is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Zaloguj się ponownie przed zmianą metod uwierzytelniania.",
        )
    if evidence_time > now + 30 or now - evidence_time > 300:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Zaloguj się ponownie przed zmianą metod uwierzytelniania.",
        )


def assert_password_or_recent_federated_identity(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    current_password: str | None,
    *,
    session_id: str,
    user_id: int,
    now: int,
) -> None:
    """Authorize a credential change without guessing a historical password's origin.

    Known local passwords require the current password. A legacy Google-linked
    password of unknown origin can be recovered only with a fresh Google login,
    and only when the caller deliberately omits the current password.
    """
    from app.passwords import password_hasher

    if row["has_local_password"] and current_password:
        if password_hasher.verify(current_password, row["password_hash"]):
            return
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Obecne hasło jest nieprawidłowe.")
    if row["has_local_password"] and row["password_origin"] != "legacy_unknown":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Obecne hasło jest nieprawidłowe.")
    if row["has_local_password"]:
        method = db.execute(
            "SELECT authentication_method FROM auth_sessions WHERE session_id=? AND user_id=?",
            (session_id, user_id),
        ).fetchone()
        if method is None or method["authentication_method"] != "google":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Obecne hasło jest nieprawidłowe.")
    assert_recent_authentication(db, session_id, user_id, now=now)


def claim_auth_challenge_attempt(
    db: sqlite3.Connection,
    kind: str,
    value: str,
    *,
    now: int,
    user_id: int | None = None,
    session_id: str | None = None,
) -> bool:
    """Atomically count one verifier attempt inside the caller's write transaction.

    The challenge is still consumed by the successful ceremony. Invalid or repeated
    attempts are capped at five; expired, mismatched, or exhausted challenges fail
    without running expensive cryptographic verification.
    """
    try:
        digest = sha256(value.encode("ascii")).hexdigest()
    except UnicodeEncodeError:
        return False
    row = db.execute(
        """SELECT user_id,session_hash,expires_at,attempts FROM auth_challenges
           WHERE challenge_hash=? AND kind=? AND challenge_value=?""",
        (digest, kind, value),
    ).fetchone()
    if (
        row is None
        or row["expires_at"] <= now
        or row["user_id"] != user_id
        or row["session_hash"] != session_id
        or row["attempts"] >= MAX_AUTH_CHALLENGE_ATTEMPTS
    ):
        return False
    db.execute(
        "UPDATE auth_challenges SET attempts=attempts+1 WHERE challenge_hash=? AND attempts < ?",
        (digest, MAX_AUTH_CHALLENGE_ATTEMPTS),
    )
    return db.execute("SELECT changes()").fetchone()[0] == 1


def create_login_challenge(
    db: sqlite3.Connection,
    user_id: int,
    *,
    authentication_method: str,
    provider_authenticated_at: int | None = None,
    now: int | None = None,
) -> MfaLoginChallengeResponse:
    """Create the second-factor challenge inside the caller's login transaction."""
    credential = db.execute(
        "SELECT enabled_at, locked_until FROM user_totp WHERE user_id = ?", (user_id,)
    ).fetchone()
    if credential is None or credential["enabled_at"] is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Błędny e-mail lub hasło.")
    now = current_timestamp() if now is None else now
    if credential["locked_until"] > now:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Zbyt wiele błędnych kodów. Spróbuj ponownie później.",
            headers={"Retry-After": str(credential["locked_until"] - now)},
        )
    raw_challenge = new_challenge()
    db.execute("DELETE FROM totp_login_challenges WHERE expires_at <= ?", (now,))
    db.execute(
        "INSERT INTO totp_login_challenges(challenge_hash,user_id,created_at,expires_at,authenticated_at,authentication_method,provider_authenticated_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            challenge_hash(raw_challenge),
            user_id,
            now,
            now + LOGIN_CHALLENGE_LIFETIME_SECONDS,
            now,
            authentication_method,
            provider_authenticated_at,
        ),
    )
    return MfaLoginChallengeResponse(
        challenge_token=raw_challenge,
        expires_in=LOGIN_CHALLENGE_LIFETIME_SECONDS,
    )
