"""TOTP enrollment helpers and atomic MFA login finalization use case."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing

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


def _assert_live_session(
    db: sqlite3.Connection, session_id: str, user_id: int, now: int
) -> None:
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


def complete_mfa_login(challenge_token: str, code: str, *, now: int | None = None) -> AuthResponse:
    """Consume one TOTP challenge and issue a full session in one write transaction."""
    now = unix_time() if now is None else now
    challenge_digest = challenge_hash(challenge_token)
    pending_error: HTTPException | None = None
    result: AuthResponse | None = None
    try:
        with closing(connect_db()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            challenge = db.execute(
                "SELECT user_id,expires_at,attempts,authentication_method,provider_authenticated_at "
                "FROM totp_login_challenges WHERE challenge_hash = ?",
                (challenge_digest,),
            ).fetchone()
            if challenge is None:
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy lub wygasły challenge."
                )
            if challenge["expires_at"] <= now:
                db.execute(
                    "DELETE FROM totp_login_challenges WHERE challenge_hash = ?",
                    (challenge_digest,),
                )
                pending_error = HTTPException(
                    status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy lub wygasły challenge."
                )
            else:
                user_id = challenge["user_id"]
                credential = db.execute(
                    "SELECT * FROM user_totp WHERE user_id = ? AND enabled_at IS NOT NULL",
                    (user_id,),
                ).fetchone()
                if credential is None or credential["secret_ciphertext"] is None:
                    db.execute("DELETE FROM totp_login_challenges WHERE user_id = ?", (user_id,))
                    pending_error = HTTPException(
                        status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy lub wygasły challenge."
                    )
                else:
                    _assert_not_locked(credential, now)
                    used_recovery_code = False
                    matched_step: int | None = None
                    if re.fullmatch(r"[0-9]{6}", code):
                        secret = decrypt_secret(
                            user_id, credential["secret_ciphertext"], purpose="active"
                        )
                        matched_step = matching_totp_step(secret, code, now=now)
                        valid_code = (
                            matched_step is not None and matched_step > credential["last_used_step"]
                        )
                    else:
                        row = db.execute(
                            "SELECT code_hash FROM totp_recovery_codes WHERE user_id = ? AND code_hash = ?",
                            (user_id, recovery_code_hash(code)),
                        ).fetchone()
                        valid_code = row is not None
                        used_recovery_code = valid_code

                    if not valid_code:
                        pending_error = _wrong_code(
                            locked=_record_failed_attempt(
                                db, user_id, now, challenge_digest=challenge_digest
                            )
                        )
                    else:
                        if used_recovery_code:
                            db.execute(
                                "DELETE FROM totp_recovery_codes WHERE user_id = ? AND code_hash = ?",
                                (user_id, recovery_code_hash(code)),
                            )
                            write_audit_event(
                                db,
                                actor_user_id=user_id,
                                actor_role=db.execute(
                                    "SELECT role_name FROM user_roles WHERE user_id = ?", (user_id,)
                                ).fetchone()["role_name"],
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
                        db.execute(
                            "DELETE FROM totp_login_challenges WHERE challenge_hash = ?",
                            (challenge_digest,),
                        )
                        identity = db.execute(
                            """SELECT u.id, u.email, r.role_name FROM users AS u
                               JOIN user_roles AS r ON r.user_id = u.id WHERE u.id = ?""",
                            (user_id,),
                        ).fetchone()
                        if identity is None:
                            raise HTTPException(
                                status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy lub wygasły challenge."
                            )
                        tokens = issue_session(
                            db,
                            user_id,
                            authentication_method=challenge["authentication_method"],
                            provider_authenticated_at=challenge["provider_authenticated_at"],
                        )
                        result = AuthResponse(
                            user=User(
                                id=identity["id"],
                                email=identity["email"],
                                role=identity["role_name"],
                            ),
                            access_token=tokens.access_token,
                            refresh_token=tokens.refresh_token,
                            expires_in=tokens.expires_in,
                            refresh_expires_in=tokens.refresh_expires_in,
                        )
    except MFAConfigurationError as exc:
        raise _unavailable() from exc
    if pending_error is not None:
        raise pending_error
    if result is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy lub wygasły challenge.")
    return result
