"""TOTP enrollment helpers and atomic MFA login finalization use case."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass

from fastapi import HTTPException, status

from app.audit import write_audit_event
from app.database import connect_db
from app.schemas import AuthResponse, User
from app.sessions import issue_session
from app.totp import (
    MFA_FAILURE_WINDOW_SECONDS,
    MFA_LOCKOUT_SECONDS,
    MFA_MAX_FAILED_ATTEMPTS,
    MFAConfigurationError,
    challenge_hash,
    decrypt_secret,
    matching_totp_step,
    recovery_code_hash,
    unix_time,
)


def _unavailable() -> HTTPException:
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Uwierzytelnianie MFA jest chwilowo niedostępne.",
    )


def _verify_password(password: str | None, password_hash: str | None) -> bool:
    from app.passwords import password_hasher

    return bool(password and password_hash and password_hasher.verify(password, password_hash))


def _assert_live_session(db: sqlite3.Connection, session_id: str, user_id: int, now: int) -> None:
    row = db.execute(
        """SELECT 1 FROM auth_sessions WHERE session_id = ? AND user_id = ?
           AND access_expires_at > ? AND refresh_expires_at > ?
           AND absolute_expires_at > ? AND revoked_at IS NULL""",
        (session_id, user_id, now, now, now),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")


def _assert_not_locked(row: sqlite3.Row, now: int) -> None:
    if row["locked_until"] > now:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Zbyt wiele błędnych kodów. Spróbuj ponownie później.",
            headers={"Retry-After": str(row["locked_until"] - now)},
        )


def _record_failed_attempt(
    db: sqlite3.Connection,
    user_id: int,
    now: int,
    *,
    challenge_digest: str | None = None,
) -> bool:
    row = db.execute(
        "SELECT failed_attempts, failure_window_started_at FROM user_totp WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return False
    window_started = row["failure_window_started_at"]
    if window_started is None or now - window_started >= MFA_FAILURE_WINDOW_SECONDS:
        attempts = 1
        window_started = now
    else:
        attempts = row["failed_attempts"] + 1
    locked_until = now + MFA_LOCKOUT_SECONDS if attempts >= MFA_MAX_FAILED_ATTEMPTS else 0
    db.execute(
        """UPDATE user_totp SET failed_attempts = ?, failure_window_started_at = ?,
                  locked_until = ? WHERE user_id = ?""",
        (attempts, window_started, locked_until, user_id),
    )
    if challenge_digest is not None:
        challenge = db.execute(
            "SELECT attempts FROM totp_login_challenges WHERE challenge_hash = ?",
            (challenge_digest,),
        ).fetchone()
        if challenge is not None:
            next_attempt = challenge["attempts"] + 1
            if next_attempt >= MFA_MAX_FAILED_ATTEMPTS:
                db.execute(
                    "DELETE FROM totp_login_challenges WHERE challenge_hash = ?",
                    (challenge_digest,),
                )
            else:
                db.execute(
                    "UPDATE totp_login_challenges SET attempts = ? WHERE challenge_hash = ?",
                    (next_attempt, challenge_digest),
                )
    return attempts >= MFA_MAX_FAILED_ATTEMPTS


def _reset_failed_attempts(db: sqlite3.Connection, user_id: int) -> None:
    db.execute(
        """UPDATE user_totp SET failed_attempts = 0, failure_window_started_at = NULL,
                  locked_until = 0 WHERE user_id = ?""",
        (user_id,),
    )


def _wrong_code(*, locked: bool) -> HTTPException:
    if locked:
        return HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Zbyt wiele błędnych kodów. Spróbuj ponownie później.",
            headers={"Retry-After": str(MFA_LOCKOUT_SECONDS)},
        )
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy lub wygasły kod.")


@dataclass(frozen=True, slots=True)
class MfaLoginOutcome:
    response: AuthResponse | None = None
    error: HTTPException | None = None


def _invalid_challenge() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy lub wygasły challenge.")


def _load_login_challenge(db: sqlite3.Connection, digest: str) -> sqlite3.Row:
    challenge = db.execute(
        """SELECT user_id, expires_at, attempts, authentication_method,
                  provider_authenticated_at
           FROM totp_login_challenges WHERE challenge_hash = ?""",
        (digest,),
    ).fetchone()
    if challenge is None:
        raise _invalid_challenge()
    return challenge


def _load_active_credential(db: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM user_totp WHERE user_id = ? AND enabled_at IS NOT NULL",
        (user_id,),
    ).fetchone()


def _verify_login_code(
    db: sqlite3.Connection, credential: sqlite3.Row, user_id: int, code: str, now: int
) -> tuple[bool, int | None, bool]:
    """Return validity, matched TOTP step and whether a recovery code was used."""
    if re.fullmatch(r"[0-9]{6}", code):
        secret = decrypt_secret(user_id, credential["secret_ciphertext"], purpose="active")
        step = matching_totp_step(secret, code, now=now)
        return step is not None and step > credential["last_used_step"], step, False
    found = db.execute(
        "SELECT 1 FROM totp_recovery_codes WHERE user_id = ? AND code_hash = ?",
        (user_id, recovery_code_hash(code)),
    ).fetchone()
    return found is not None, None, found is not None


def _consume_login_code(
    db: sqlite3.Connection,
    user_id: int,
    code: str,
    matched_step: int | None,
    used_recovery_code: bool,
    now: int,
) -> None:
    if used_recovery_code:
        db.execute(
            "DELETE FROM totp_recovery_codes WHERE user_id = ? AND code_hash = ?",
            (user_id, recovery_code_hash(code)),
        )
        role = db.execute(
            "SELECT role_name FROM user_roles WHERE user_id = ?", (user_id,)
        ).fetchone()["role_name"]
        write_audit_event(
            db,
            actor_user_id=user_id,
            actor_role=role,
            action="auth.mfa_recovery_code_used",
            entity_type="user",
            entity_id=str(user_id),
            details={},
            created_at=now,
        )
    else:
        db.execute(
            "UPDATE user_totp SET last_used_step = ? WHERE user_id = ?",
            (matched_step, user_id),
        )
    _reset_failed_attempts(db, user_id)


def _issue_authenticated_session(db: sqlite3.Connection, challenge: sqlite3.Row) -> AuthResponse:
    user_id = challenge["user_id"]
    identity = db.execute(
        """SELECT u.id, u.email, r.role_name FROM users AS u
           JOIN user_roles AS r ON r.user_id = u.id WHERE u.id = ?""",
        (user_id,),
    ).fetchone()
    if identity is None:
        raise _invalid_challenge()
    tokens = issue_session(
        db,
        user_id,
        authentication_method=challenge["authentication_method"],
        provider_authenticated_at=challenge["provider_authenticated_at"],
    )
    return AuthResponse(
        user=User(id=identity["id"], email=identity["email"], role=identity["role_name"]),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        refresh_expires_in=tokens.refresh_expires_in,
    )


def _finish_login_in_transaction(
    db: sqlite3.Connection, digest: str, code: str, now: int
) -> MfaLoginOutcome:
    """Return errors after committing challenge expiry or failed-attempt counters."""
    challenge = _load_login_challenge(db, digest)
    if challenge["expires_at"] <= now:
        db.execute("DELETE FROM totp_login_challenges WHERE challenge_hash = ?", (digest,))
        return MfaLoginOutcome(error=_invalid_challenge())
    user_id = challenge["user_id"]
    credential = _load_active_credential(db, user_id)
    if credential is None or credential["secret_ciphertext"] is None:
        db.execute("DELETE FROM totp_login_challenges WHERE user_id = ?", (user_id,))
        return MfaLoginOutcome(error=_invalid_challenge())
    _assert_not_locked(credential, now)
    valid, matched_step, used_recovery = _verify_login_code(db, credential, user_id, code, now)
    if not valid:
        locked = _record_failed_attempt(db, user_id, now, challenge_digest=digest)
        return MfaLoginOutcome(error=_wrong_code(locked=locked))
    _consume_login_code(db, user_id, code, matched_step, used_recovery, now)
    db.execute("DELETE FROM totp_login_challenges WHERE challenge_hash = ?", (digest,))
    return MfaLoginOutcome(response=_issue_authenticated_session(db, challenge))


def complete_mfa_login(challenge_token: str, code: str, *, now: int | None = None) -> AuthResponse:
    """Consume one TOTP challenge and issue a full session in one write transaction.

    The pending error is raised only after commit so expired challenges and failed
    attempts persist. A failed session issue rolls back code consumption and audit.
    """
    now = unix_time() if now is None else now
    digest = challenge_hash(challenge_token)
    try:
        with closing(connect_db()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            outcome = _finish_login_in_transaction(db, digest, code, now)
    except MFAConfigurationError as exc:
        raise _unavailable() from exc
    if outcome.error is not None:
        raise outcome.error
    if outcome.response is None:
        raise _invalid_challenge()
    return outcome.response
