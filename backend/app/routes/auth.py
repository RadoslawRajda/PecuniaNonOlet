"""Registration, password login and local session endpoints."""

from __future__ import annotations

import secrets
import sqlite3
import time
from contextlib import closing

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.accounts import initialize_user_accounts
from app.adapters.turnstile import verify_turnstile_token
from app.authorization import AuthenticatedSession, current_session, token_hash
from app.config import Settings, load_settings
from app.database import connect_db
from app.passwords import DUMMY_PASSWORD_HASH, password_hasher
from app.rate_limits import client_ip, enforce_rate_limit, identity_bucket, ip_bucket
from app.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginCredentials,
    LoginResponse,
    LogoutRequest,
    PublicRegisterRequest,
    RefreshTokenRequest,
    User,
)
from app.services.authentication import (
    assert_password_or_recent_federated_identity,
    create_login_challenge,
)
from app.sessions import issue_session, revoke_user_sessions, rotate_refresh_token

router = APIRouter(tags=["authentication"])


@router.post("/api/register", response_model=AuthResponse, status_code=201)
def register(payload: PublicRegisterRequest, request: Request) -> AuthResponse:
    settings: Settings = request.app.state.settings or load_settings()
    address = client_ip(request.client.host if request.client else None)
    enforce_rate_limit(
        [ip_bucket("register", address), identity_bucket("register", payload.email)],
        limits=[20, 5],
    )
    verify_turnstile_token(
        payload.captcha_token,
        request.client.host if request.client else None,
        settings=settings,
    )
    password_hash = password_hasher.hash(payload.password)
    with closing(connect_db()) as db:
        try:
            with db:
                cursor = db.execute(
                    "INSERT INTO users(email, password_hash, webauthn_user_handle, created_at) VALUES (?, ?, ?, ?)",
                    (payload.email, password_hash, secrets.token_bytes(32), int(time.time())),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("The inserted user did not receive a database id.")
                user_id = cursor.lastrowid
                db.execute(
                    "INSERT INTO user_roles(user_id, role_name) VALUES (?, 'user')", (user_id,)
                )
                initialize_user_accounts(db, user_id, int(time.time()))
                tokens = issue_session(db, user_id, now=int(time.time()))
        except sqlite3.IntegrityError as exc:
            if "users.email" in str(exc):
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "Ten adres e-mail jest już zajęty."
                ) from exc
            raise
    return AuthResponse(
        user=User(id=user_id, email=payload.email, role="user"),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        refresh_expires_in=tokens.refresh_expires_in,
    )


@router.post("/api/login", response_model=LoginResponse)
def login(payload: LoginCredentials, request: Request) -> LoginResponse:
    address = client_ip(request.client.host if request.client else None)
    enforce_rate_limit(
        [ip_bucket("password_login", address), identity_bucket("password_login", payload.email)],
        limits=[20, 10],
    )
    with closing(connect_db()) as read_db:
        row = read_db.execute(
            """
            SELECT u.id, u.email, u.password_hash, u.has_local_password, r.role_name
            FROM users AS u JOIN user_roles AS r ON r.user_id = u.id
            WHERE u.email = ?
            """,
            (payload.email,),
        ).fetchone()
        stored_hash = (
            row["password_hash"]
            if row is not None and row["has_local_password"]
            else DUMMY_PASSWORD_HASH
        )
        valid_password = password_hasher.verify(payload.password, stored_hash)
        if row is None or not valid_password:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Błędny e-mail lub hasło.")
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute(
            "SELECT id, email, password_hash FROM users WHERE id = ?", (row["id"],)
        ).fetchone()
        if current is None or current["password_hash"] != stored_hash:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Błędny e-mail lub hasło.")
        current_role = db.execute(
            "SELECT role_name FROM user_roles WHERE user_id = ?", (row["id"],)
        ).fetchone()
        if current_role is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Błędny e-mail lub hasło.")
        mfa = db.execute(
            "SELECT enabled_at FROM user_totp WHERE user_id = ?", (row["id"],)
        ).fetchone()
        if mfa is not None and mfa["enabled_at"] is not None:
            challenge = create_login_challenge(db, row["id"], authentication_method="password")
            return challenge
        tokens = issue_session(db, row["id"], now=int(time.time()))
    return AuthResponse(
        user=User(id=current["id"], email=current["email"], role=current_role["role_name"]),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        refresh_expires_in=tokens.refresh_expires_in,
    )


@router.post(
    "/api/refresh",
    response_model=AuthResponse,
    summary="Odśwież sesję",
    description=(
        "Wymienia ważny refresh token na nową parę access/refresh. Poprzednia para "
        "przestaje działać. Ponowne użycie zużytego refresh tokenu unieważnia całą "
        "rodzinę sesji. Klient powinien zapisać oba nowe tokeny atomowo."
    ),
)
def refresh_session(payload: RefreshTokenRequest, request: Request) -> AuthResponse:
    """Rotate a refresh credential; a reused credential revokes its session family."""
    address = client_ip(request.client.host if request.client else None)
    enforce_rate_limit([ip_bucket("session_refresh", address)], limits=[30])
    now = int(time.time())
    identity = None
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        tokens = rotate_refresh_token(db, payload.refresh_token, now=now)
        if tokens is not None:
            identity = db.execute(
                "SELECT u.id,u.email,r.role_name FROM auth_sessions s "
                "JOIN users u ON u.id=s.user_id "
                "JOIN user_roles r ON r.user_id=u.id WHERE s.session_id=?",
                (tokens.session_id,),
            ).fetchone()
    if tokens is None or identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")
    return AuthResponse(
        user=User(id=identity["id"], email=identity["email"], role=identity["role_name"]),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        refresh_expires_in=tokens.refresh_expires_in,
    )


@router.post("/api/change-password", response_model=ChangePasswordResponse)
def change_password(
    payload: ChangePasswordRequest,
    session: AuthenticatedSession = Depends(current_session),
) -> ChangePasswordResponse:
    user = session.user
    with closing(connect_db()) as read_db:
        row = read_db.execute(
            "SELECT password_hash,has_local_password,password_origin FROM users WHERE id = ?",
            (user.id,),
        ).fetchone()
        if row is not None:
            assert_password_or_recent_federated_identity(
                read_db,
                row,
                payload.current_password,
                session_id=session.session_id,
                user_id=user.id,
                now=int(time.time()),
            )
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Obecne hasło jest nieprawidłowe.")
    if row["has_local_password"] and password_hasher.verify(
        payload.new_password, row["password_hash"]
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nowe hasło musi różnić się od obecnego.")
    expected_hash = row["password_hash"]
    new_hash = password_hasher.hash(payload.new_password)
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        active_session = db.execute(
            """SELECT 1 FROM auth_sessions WHERE session_id = ? AND user_id = ?
               AND access_expires_at > ? AND refresh_expires_at > ?
               AND absolute_expires_at > ? AND revoked_at IS NULL""",
            (
                session.session_id,
                user.id,
                int(time.time()),
                int(time.time()),
                int(time.time()),
            ),
        ).fetchone()
        if active_session is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")
        current = db.execute(
            "SELECT password_hash,has_local_password,password_origin FROM users WHERE id = ?",
            (user.id,),
        ).fetchone()
        if (
            current is None
            or current["password_hash"] != expected_hash
            or current["has_local_password"] != row["has_local_password"]
            or current["password_origin"] != row["password_origin"]
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Hasło zostało już zmienione. Zaloguj się ponownie."
            )
        if not payload.current_password:
            assert_password_or_recent_federated_identity(
                db,
                current,
                None,
                session_id=session.session_id,
                user_id=user.id,
                now=int(time.time()),
            )
        revoke_user_sessions(db, user.id, now=int(time.time()))
        db.execute(
            "UPDATE users SET password_hash = ?,has_local_password=1,password_origin='local' WHERE id = ?",
            (new_hash, user.id),
        )
        db.execute("DELETE FROM totp_login_challenges WHERE user_id = ?", (user.id,))
        db.execute("DELETE FROM user_totp WHERE user_id = ? AND enabled_at IS NULL", (user.id,))
    return ChangePasswordResponse(
        message="Hasło zostało zmienione. Zaloguj się ponownie.",
        reauthentication_required=True,
    )


@router.get("/api/me", response_model=User)
def me(session: AuthenticatedSession = Depends(current_session)) -> User:
    return session.user


@router.post(
    "/api/logout",
    status_code=204,
    response_class=Response,
    summary="Wyloguj bieżącą rodzinę sesji",
    description=(
        "Przyjmuje refresh token w body, także gdy access token już wygasł. "
        "Odpowiedź 204 nie ujawnia, czy przekazany token istniał."
    ),
)
def logout(payload: LogoutRequest, request: Request) -> Response:
    """Revoke the token family without revealing whether the supplied token exists."""
    address = client_ip(request.client.host if request.client else None)
    enforce_rate_limit([ip_bucket("logout", address)], limits=[60])
    if payload.refresh_token is not None:
        presented_hash = token_hash(payload.refresh_token)
        now = int(time.time())
        with closing(connect_db()) as db, db:
            db.execute(
                "UPDATE auth_sessions SET revoked_at=? WHERE refresh_token_hash=? AND revoked_at IS NULL",
                (now, presented_hash),
            )
            previous = db.execute(
                "SELECT session_id FROM consumed_refresh_tokens WHERE token_hash=?",
                (presented_hash,),
            ).fetchone()
            if previous is not None:
                db.execute(
                    "UPDATE auth_sessions SET revoked_at=? WHERE session_id=? AND revoked_at IS NULL",
                    (now, previous["session_id"]),
                )
    return Response(status_code=204)
