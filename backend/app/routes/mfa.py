"""User-managed TOTP enrollment and two-step login routes."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.audit import write_audit_event
from app.authorization import current_session, token_hash
from app.database import connect_db
from app.schemas import (
    AuthResponse,
    MfaDisableRequest,
    MfaDisableResponse,
    MfaEnableResponse,
    MfaLoginChallengeResponse,
    MfaLoginRequest,
    MfaSetupRequest,
    MfaSetupResponse,
    MfaStatusResponse,
    MfaTotpCodeRequest,
    User,
)
from app.sessions import issue_token
from app.totp import (
    LOGIN_CHALLENGE_LIFETIME_SECONDS,
    MFAConfigurationError,
    MFA_FAILURE_WINDOW_SECONDS,
    MFA_LOCKOUT_SECONDS,
    MFA_MAX_FAILED_ATTEMPTS,
    RECOVERY_CODE_COUNT,
    TOTP_SETUP_LIFETIME_SECONDS,
    challenge_hash,
    create_recovery_codes,
    create_totp_secret,
    decrypt_secret,
    encrypt_secret,
    matching_totp_step,
    new_challenge,
    provisioning_uri,
    recovery_code_hash,
    unix_time,
)

router = APIRouter(prefix="/api")
AuthenticatedSession = Annotated[tuple[str, User], Depends(current_session)]
_RECOVERY_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16}$")


def _unavailable() -> HTTPException:
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Uwierzytelnianie MFA jest chwilowo niedostępne.",
    )


def _verify_password(password: str, password_hash: str) -> bool:
    # Import lazily to avoid making the app/router import each other.
    from app.main import password_hasher

    return password_hasher.verify(password, password_hash)


def _assert_live_session(db: sqlite3.Connection, session_token: str, user_id: int, now: int) -> None:
    row = db.execute(
        "SELECT 1 FROM sessions WHERE token_hash = ? AND user_id = ? AND expires_at > ?",
        (token_hash(session_token), user_id, now),
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


def create_login_challenge(
    db: sqlite3.Connection, user_id: int
) -> MfaLoginChallengeResponse:
    """Called only inside login's write transaction after password revalidation."""
    credential = db.execute(
        "SELECT enabled_at, locked_until FROM user_totp WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if credential is None or credential["enabled_at"] is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Błędny e-mail lub hasło.")
    now = unix_time()
    _assert_not_locked(credential, now)
    raw_challenge = new_challenge()
    digest = challenge_hash(raw_challenge)
    db.execute("DELETE FROM totp_login_challenges WHERE expires_at <= ?", (now,))
    db.execute(
        "INSERT INTO totp_login_challenges(challenge_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (digest, user_id, now, now + LOGIN_CHALLENGE_LIFETIME_SECONDS),
    )
    return MfaLoginChallengeResponse(
        challenge_token=raw_challenge,
        expires_in=LOGIN_CHALLENGE_LIFETIME_SECONDS,
    )


@router.get("/mfa", response_model=MfaStatusResponse)
def get_mfa_status(session: AuthenticatedSession) -> MfaStatusResponse:
    _, user = session
    with closing(connect_db()) as db:
        row = db.execute(
            "SELECT enabled_at FROM user_totp WHERE user_id = ?", (user.id,)
        ).fetchone()
    return MfaStatusResponse(totp_enabled=bool(row and row["enabled_at"] is not None))


@router.post("/mfa/totp/setup", response_model=MfaSetupResponse)
def setup_totp(payload: MfaSetupRequest, session: AuthenticatedSession) -> MfaSetupResponse:
    session_token, user = session
    with closing(connect_db()) as read_db:
        password_row = read_db.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user.id,)
        ).fetchone()
    if password_row is None or not _verify_password(payload.current_password, password_row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Obecne hasło jest nieprawidłowe.")

    secret = create_totp_secret()
    try:
        pending_ciphertext = encrypt_secret(user.id, secret, purpose="pending")
    except MFAConfigurationError as exc:
        raise _unavailable() from exc
    now = unix_time()
    expires_at = now + TOTP_SETUP_LIFETIME_SECONDS
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        _assert_live_session(db, session_token, user.id, now)
        current = db.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user.id,)
        ).fetchone()
        if current is None or current["password_hash"] != password_row["password_hash"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Hasło zostało zmienione. Zaloguj się ponownie.")
        credential = db.execute(
            "SELECT enabled_at FROM user_totp WHERE user_id = ?", (user.id,)
        ).fetchone()
        if credential is not None and credential["enabled_at"] is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "MFA jest już włączone.")
        db.execute(
            """INSERT INTO user_totp(user_id, pending_secret_ciphertext, pending_expires_at)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   pending_secret_ciphertext = excluded.pending_secret_ciphertext,
                   pending_expires_at = excluded.pending_expires_at""",
            (user.id, pending_ciphertext, expires_at),
        )
    return MfaSetupResponse(
        secret=secret,
        provisioning_uri=provisioning_uri(secret, user.email),
        expires_at=expires_at,
    )


@router.post("/mfa/totp/confirm", response_model=MfaEnableResponse)
def confirm_totp(payload: MfaTotpCodeRequest, session: AuthenticatedSession) -> MfaEnableResponse:
    session_token, user = session
    now = unix_time()
    recovery_codes = create_recovery_codes()
    pending_error: HTTPException | None = None
    try:
        with closing(connect_db()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            _assert_live_session(db, session_token, user.id, now)
            credential = db.execute(
                "SELECT * FROM user_totp WHERE user_id = ?", (user.id,)
            ).fetchone()
            if credential is None or credential["pending_secret_ciphertext"] is None:
                raise HTTPException(status.HTTP_409_CONFLICT, "Nie rozpoczęto konfiguracji TOTP.")
            if credential["pending_expires_at"] <= now:
                db.execute(
                    "UPDATE user_totp SET pending_secret_ciphertext = NULL, pending_expires_at = NULL WHERE user_id = ?",
                    (user.id,),
                )
                pending_error = HTTPException(status.HTTP_409_CONFLICT, "Konfiguracja wygasła. Rozpocznij ją ponownie.")
            else:
                _assert_not_locked(credential, now)
                secret = decrypt_secret(
                    user.id, credential["pending_secret_ciphertext"], purpose="pending"
                )
                matched_step = matching_totp_step(secret, payload.code, now=now)
                if matched_step is None:
                    pending_error = _wrong_code(
                        locked=_record_failed_attempt(db, user.id, now)
                    )
                else:
                    active_ciphertext = encrypt_secret(user.id, secret, purpose="active")
                    db.execute(
                        """UPDATE user_totp SET secret_ciphertext = ?, pending_secret_ciphertext = NULL,
                                  pending_expires_at = NULL, enabled_at = ?, last_used_step = ?
                           WHERE user_id = ?""",
                        (active_ciphertext, now, matched_step, user.id),
                    )
                    db.execute("DELETE FROM totp_recovery_codes WHERE user_id = ?", (user.id,))
                    db.executemany(
                        "INSERT INTO totp_recovery_codes(code_hash, user_id, created_at) VALUES (?, ?, ?)",
                        [(recovery_code_hash(code), user.id, now) for code in recovery_codes],
                    )
                    db.execute("DELETE FROM sessions WHERE user_id = ?", (user.id,))
                    db.execute("DELETE FROM totp_login_challenges WHERE user_id = ?", (user.id,))
                    _reset_failed_attempts(db, user.id)
                    write_audit_event(
                        db,
                        actor_user_id=user.id,
                        actor_role=user.role,
                        action="auth.mfa_totp_enabled",
                        entity_type="user",
                        entity_id=str(user.id),
                        details={"recovery_codes_issued": RECOVERY_CODE_COUNT},
                        created_at=now,
                    )
    except MFAConfigurationError as exc:
        raise _unavailable() from exc
    if pending_error is not None:
        raise pending_error
    return MfaEnableResponse(recovery_codes=recovery_codes)


@router.post("/login/mfa", response_model=AuthResponse)
def complete_mfa_login(payload: MfaLoginRequest) -> AuthResponse:
    now = unix_time()
    challenge_digest = challenge_hash(payload.challenge_token)
    pending_error: HTTPException | None = None
    result: AuthResponse | None = None
    try:
        with closing(connect_db()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            challenge = db.execute(
                "SELECT user_id, expires_at, attempts FROM totp_login_challenges WHERE challenge_hash = ?",
                (challenge_digest,),
            ).fetchone()
            if challenge is None:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy lub wygasły challenge.")
            if challenge["expires_at"] <= now:
                db.execute(
                    "DELETE FROM totp_login_challenges WHERE challenge_hash = ?", (challenge_digest,)
                )
                pending_error = HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy lub wygasły challenge.")
            else:
                user_id = challenge["user_id"]
                credential = db.execute(
                    "SELECT * FROM user_totp WHERE user_id = ? AND enabled_at IS NOT NULL",
                    (user_id,),
                ).fetchone()
                if credential is None or credential["secret_ciphertext"] is None:
                    db.execute("DELETE FROM totp_login_challenges WHERE user_id = ?", (user_id,))
                    pending_error = HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy lub wygasły challenge.")
                else:
                    _assert_not_locked(credential, now)
                    used_recovery_code = False
                    matched_step: int | None = None
                    if re.fullmatch(r"[0-9]{6}", payload.code):
                        secret = decrypt_secret(
                            user_id, credential["secret_ciphertext"], purpose="active"
                        )
                        matched_step = matching_totp_step(secret, payload.code, now=now)
                        valid_code = matched_step is not None and matched_step > credential["last_used_step"]
                    else:
                        row = db.execute(
                            "SELECT code_hash FROM totp_recovery_codes WHERE user_id = ? AND code_hash = ?",
                            (user_id, recovery_code_hash(payload.code)),
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
                                (user_id, recovery_code_hash(payload.code)),
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
                            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy lub wygasły challenge.")
                        token = issue_token(db, user_id)
                        result = AuthResponse(
                            user=User(id=identity["id"], email=identity["email"], role=identity["role_name"]),
                            token=token,
                        )
    except MFAConfigurationError as exc:
        raise _unavailable() from exc
    if pending_error is not None:
        raise pending_error
    if result is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy lub wygasły challenge.")
    return result


@router.post("/mfa/totp/disable", response_model=MfaDisableResponse)
def disable_totp(payload: MfaDisableRequest, session: AuthenticatedSession) -> MfaDisableResponse:
    session_token, user = session
    with closing(connect_db()) as read_db:
        password_row = read_db.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user.id,)
        ).fetchone()
    if password_row is None or not _verify_password(payload.current_password, password_row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Obecne hasło jest nieprawidłowe.")

    now = unix_time()
    pending_error: HTTPException | None = None
    try:
        with closing(connect_db()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            _assert_live_session(db, session_token, user.id, now)
            current = db.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user.id,)
            ).fetchone()
            if current is None or current["password_hash"] != password_row["password_hash"]:
                raise HTTPException(status.HTTP_409_CONFLICT, "Hasło zostało zmienione. Zaloguj się ponownie.")
            credential = db.execute(
                "SELECT * FROM user_totp WHERE user_id = ? AND enabled_at IS NOT NULL",
                (user.id,),
            ).fetchone()
            if credential is None or credential["secret_ciphertext"] is None:
                raise HTTPException(status.HTTP_409_CONFLICT, "MFA nie jest włączone.")
            _assert_not_locked(credential, now)
            used_recovery_code = False
            matched_step: int | None = None
            if re.fullmatch(r"[0-9]{6}", payload.code):
                secret = decrypt_secret(user.id, credential["secret_ciphertext"], purpose="active")
                matched_step = matching_totp_step(secret, payload.code, now=now)
                valid_code = matched_step is not None and matched_step > credential["last_used_step"]
            else:
                recovery = db.execute(
                    "SELECT code_hash FROM totp_recovery_codes WHERE user_id = ? AND code_hash = ?",
                    (user.id, recovery_code_hash(payload.code)),
                ).fetchone()
                valid_code = recovery is not None
                used_recovery_code = valid_code

            if not valid_code:
                pending_error = _wrong_code(locked=_record_failed_attempt(db, user.id, now))
            else:
                if used_recovery_code:
                    db.execute(
                        "DELETE FROM totp_recovery_codes WHERE user_id = ? AND code_hash = ?",
                        (user.id, recovery_code_hash(payload.code)),
                    )
                db.execute("DELETE FROM user_totp WHERE user_id = ?", (user.id,))
                db.execute("DELETE FROM sessions WHERE user_id = ?", (user.id,))
                db.execute("DELETE FROM totp_login_challenges WHERE user_id = ?", (user.id,))
                write_audit_event(
                    db,
                    actor_user_id=user.id,
                    actor_role=user.role,
                    action="auth.mfa_totp_disabled",
                    entity_type="user",
                    entity_id=str(user.id),
                    details={"used_recovery_code": used_recovery_code},
                    created_at=now,
                )
    except MFAConfigurationError as exc:
        raise _unavailable() from exc
    if pending_error is not None:
        raise pending_error
    return MfaDisableResponse()
