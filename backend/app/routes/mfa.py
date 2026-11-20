"""User-managed TOTP enrollment and two-step login routes."""

from __future__ import annotations

import re
from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.audit import write_audit_event
from app.authorization import AuthenticatedSession, current_session
from app.database import connect_db
from app.rate_limits import client_ip, enforce_rate_limit, ip_bucket
from app.schemas import (
    AuthResponse,
    MfaDisableRequest,
    MfaDisableResponse,
    MfaEnableResponse,
    MfaLoginRequest,
    MfaSetupRequest,
    MfaSetupResponse,
    MfaStatusResponse,
    MfaTotpCodeRequest,
)
from app.services.authentication import (
    assert_password_or_recent_federated_identity,
)
from app.services.mfa import (
    _assert_live_session,
    _assert_not_locked,
    _record_failed_attempt,
    _reset_failed_attempts,
    _unavailable,
    _wrong_code,
    complete_mfa_login,
)
from app.sessions import revoke_user_sessions
from app.totp import (
    RECOVERY_CODE_COUNT,
    TOTP_SETUP_LIFETIME_SECONDS,
    MFAConfigurationError,
    create_recovery_codes,
    create_totp_secret,
    decrypt_secret,
    encrypt_secret,
    matching_totp_step,
    provisioning_uri,
    recovery_code_hash,
    unix_time,
)

router = APIRouter(prefix="/api")
Authenticated = Annotated[AuthenticatedSession, Depends(current_session)]


@router.get("/mfa", response_model=MfaStatusResponse)
def get_mfa_status(session: Authenticated) -> MfaStatusResponse:
    user = session.user
    with closing(connect_db()) as db:
        row = db.execute(
            "SELECT enabled_at FROM user_totp WHERE user_id = ?", (user.id,)
        ).fetchone()
    return MfaStatusResponse(totp_enabled=bool(row and row["enabled_at"] is not None))


@router.post("/mfa/totp/setup", response_model=MfaSetupResponse)
def setup_totp(payload: MfaSetupRequest, session: Authenticated) -> MfaSetupResponse:
    user = session.user
    with closing(connect_db()) as read_db:
        password_row = read_db.execute(
            "SELECT password_hash,has_local_password,password_origin FROM users WHERE id = ?",
            (user.id,),
        ).fetchone()
        if password_row is not None:
            assert_password_or_recent_federated_identity(
                read_db,
                password_row,
                payload.current_password,
                session_id=session.session_id,
                user_id=user.id,
                now=unix_time(),
            )
    if password_row is None:
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
        _assert_live_session(db, session.session_id, user.id, now)
        current = db.execute(
            "SELECT password_hash,has_local_password,password_origin FROM users WHERE id = ?",
            (user.id,),
        ).fetchone()
        if (
            current is None
            or current["password_hash"] != password_row["password_hash"]
            or current["has_local_password"] != password_row["has_local_password"]
            or current["password_origin"] != password_row["password_origin"]
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Hasło zostało zmienione. Zaloguj się ponownie."
            )
        if not payload.current_password:
            assert_password_or_recent_federated_identity(
                db,
                current,
                None,
                session_id=session.session_id,
                user_id=user.id,
                now=now,
            )
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
def confirm_totp(payload: MfaTotpCodeRequest, session: Authenticated) -> MfaEnableResponse:
    user = session.user
    now = unix_time()
    recovery_codes = create_recovery_codes()
    pending_error: HTTPException | None = None
    try:
        with closing(connect_db()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            _assert_live_session(db, session.session_id, user.id, now)
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
                pending_error = HTTPException(
                    status.HTTP_409_CONFLICT, "Konfiguracja wygasła. Rozpocznij ją ponownie."
                )
            else:
                _assert_not_locked(credential, now)
                secret = decrypt_secret(
                    user.id, credential["pending_secret_ciphertext"], purpose="pending"
                )
                matched_step = matching_totp_step(secret, payload.code, now=now)
                if matched_step is None:
                    pending_error = _wrong_code(locked=_record_failed_attempt(db, user.id, now))
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
                    revoke_user_sessions(db, user.id, now=now)
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
def finish_mfa_login(payload: MfaLoginRequest, request: Request) -> AuthResponse:
    enforce_rate_limit(
        [ip_bucket("totp_login", client_ip(request.client.host if request.client else None))]
    )
    return complete_mfa_login(payload.challenge_token, payload.code, now=unix_time())


@router.post("/mfa/totp/disable", response_model=MfaDisableResponse)
def disable_totp(payload: MfaDisableRequest, session: Authenticated) -> MfaDisableResponse:
    user = session.user
    with closing(connect_db()) as read_db:
        password_row = read_db.execute(
            "SELECT password_hash,has_local_password,password_origin FROM users WHERE id = ?",
            (user.id,),
        ).fetchone()
        if password_row is not None:
            assert_password_or_recent_federated_identity(
                read_db,
                password_row,
                payload.current_password,
                session_id=session.session_id,
                user_id=user.id,
                now=unix_time(),
            )
    if password_row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Obecne hasło jest nieprawidłowe.")

    now = unix_time()
    pending_error: HTTPException | None = None
    try:
        with closing(connect_db()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            _assert_live_session(db, session.session_id, user.id, now)
            current = db.execute(
                "SELECT password_hash,has_local_password,password_origin FROM users WHERE id = ?",
                (user.id,),
            ).fetchone()
            if (
                current is None
                or current["password_hash"] != password_row["password_hash"]
                or current["has_local_password"] != password_row["has_local_password"]
                or current["password_origin"] != password_row["password_origin"]
            ):
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "Hasło zostało zmienione. Zaloguj się ponownie."
                )
            if not payload.current_password:
                assert_password_or_recent_federated_identity(
                    db,
                    current,
                    None,
                    session_id=session.session_id,
                    user_id=user.id,
                    now=now,
                )
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
                valid_code = (
                    matched_step is not None and matched_step > credential["last_used_step"]
                )
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
                revoke_user_sessions(db, user.id, now=now)
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
