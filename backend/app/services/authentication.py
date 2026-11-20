"""Shared authentication workflows used by password, Google and passkey routes."""

from __future__ import annotations

import sqlite3
import time

from fastapi import HTTPException, status

from app.schemas import MfaLoginChallengeResponse
from app.totp import (
    LOGIN_CHALLENGE_LIFETIME_SECONDS,
    challenge_hash,
    new_challenge,
)


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
