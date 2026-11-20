"""Google OpenID Connect login and explicit account linking."""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    TypeAdapter,
    ValidationError,
)

from app.accounts import initialize_user_accounts
from app.authorization import current_session, token_hash
from app.database import connect_db
from app.schemas import AuthResponse, LoginResponse, User
from app.sessions import issue_token

router = APIRouter(prefix="/api/auth/google", tags=["authentication"])
CHALLENGE_TTL = 300
AuthenticatedSession = Annotated[tuple[str, User], Depends(current_session)]


class GoogleTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_token: str = Field(min_length=20, max_length=8192)
    nonce: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _new_challenge(db: sqlite3.Connection, kind: str, user_id: int | None = None) -> str:
    now = int(time.time())
    db.execute("DELETE FROM auth_challenges WHERE expires_at <= ?", (now,))
    value = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO auth_challenges(challenge_hash, kind, challenge_value, user_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
        (_digest(value), kind, value, user_id, now, now + CHALLENGE_TTL),
    )
    return value


@router.post("/nonce")
def google_nonce() -> dict[str, object]:
    with closing(connect_db()) as db, db:
        nonce = _new_challenge(db, "google_login")
    return {"nonce": nonce, "expires_in": CHALLENGE_TTL}


@router.post("/link/nonce")
def google_link_nonce(session: AuthenticatedSession) -> dict[str, object]:
    token, user = session
    now = int(time.time())
    with closing(connect_db()) as db, db:
        row = db.execute(
            "SELECT authenticated_at FROM sessions WHERE token_hash=? AND user_id=? AND expires_at>?",
            (token_hash(token), user.id, now),
        ).fetchone()
        if row is None or now - row["authenticated_at"] > 300:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Zaloguj się ponownie przed połączeniem Google.")
        nonce = _new_challenge(db, "google_link", user.id)
    return {"nonce": nonce, "expires_in": CHALLENGE_TTL}


def _verify_google_id_token(payload: GoogleTokenRequest, expected_user: int | None = None) -> dict[str, object]:
    audiences = {value.strip() for value in os.getenv("GOOGLE_OAUTH_CLIENT_IDS", "").split(",") if value.strip()}
    if not audiences:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Logowanie Google nie jest skonfigurowane.")
    try:
        from google.auth.exceptions import GoogleAuthError
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token
        from requests import RequestException

        claims = id_token.verify_oauth2_token(payload.id_token, google_requests.Request(), audience=None)
    except (GoogleAuthError, RequestException, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nie udało się zweryfikować logowania Google.") from None
    if not isinstance(claims, dict):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nie udało się zweryfikować logowania Google.")
    issuer = claims.get("iss")
    subject = claims.get("sub")
    email = claims.get("email")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy wystawca tokenu Google.")
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowa tożsamość Google.")
    aud = claims.get("aud")
    audiences_in_token = {aud} if isinstance(aud, str) else set(aud) if isinstance(aud, list) and all(isinstance(item, str) for item in aud) else set()
    if not audiences.intersection(audiences_in_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token Google jest przeznaczony dla innej aplikacji.")
    authorized_party = claims.get("azp")
    if isinstance(aud, list) and len(aud) > 1 and authorized_party is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token z wieloma odbiorcami nie zawiera azp.")
    if authorized_party is not None and (
        not isinstance(authorized_party, str) or authorized_party not in audiences
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowa aplikacja logująca Google.")
    if not isinstance(email, str) or len(email) > 320 or claims.get("email_verified") is not True:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google nie potwierdził adresu e-mail.")
    try:
        normalized_email = TypeAdapter(EmailStr).validate_python(email).lower()
    except ValidationError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google zwrócił nieprawidłowy adres e-mail.") from None
    if claims.get("nonce") != payload.nonce:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja logowania Google wygasła. Spróbuj ponownie.")
    # A Google identity may be linked only after authenticating the existing local account.
    # New accounts require an authoritative Google-managed mailbox; email equality alone never links accounts.
    authoritative = normalized_email.endswith("@gmail.com") or bool(claims.get("hd"))
    if expected_user is None and not authoritative:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Użyj konta Google zarządzanego przez Google lub najpierw połącz konto.")
    return {"issuer": "https://accounts.google.com", "subject": subject, "email": normalized_email}


def _consume_challenge(db: sqlite3.Connection, kind: str, nonce: str, user_id: int | None = None) -> None:
    row = db.execute(
        "SELECT user_id FROM auth_challenges WHERE challenge_hash = ? AND kind = ? AND challenge_value = ? AND expires_at > ?",
        (_digest(nonce), kind, nonce, int(time.time())),
    ).fetchone()
    if row is None or row["user_id"] != user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja logowania wygasła. Spróbuj ponownie.")
    db.execute("DELETE FROM auth_challenges WHERE challenge_hash = ?", (_digest(nonce),))


def _auth_result(db: sqlite3.Connection, user_id: int) -> LoginResponse:
    user_row = db.execute(
        "SELECT u.id, u.email, r.role_name FROM users u JOIN user_roles r ON r.user_id=u.id WHERE u.id=?",
        (user_id,),
    ).fetchone()
    mfa = db.execute("SELECT enabled_at FROM user_totp WHERE user_id=?", (user_id,)).fetchone()
    if mfa and mfa["enabled_at"] is not None:
        from app.routes.mfa import create_login_challenge

        return create_login_challenge(db, user_id)
    return AuthResponse(
        user=User(id=user_row["id"], email=user_row["email"], role=user_row["role_name"]),
        token=issue_token(db, user_id),
    )


@router.post("/login", response_model=LoginResponse)
def google_login(payload: GoogleTokenRequest) -> LoginResponse:
    with closing(connect_db()) as db:
        pending = db.execute(
            "SELECT 1 FROM auth_challenges WHERE challenge_hash=? AND kind='google_login' AND challenge_value=? AND expires_at>?",
            (_digest(payload.nonce), payload.nonce, int(time.time())),
        ).fetchone()
    if pending is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja logowania wygasła. Spróbuj ponownie.")
    identity = _verify_google_id_token(payload)
    # Argon2 is intentionally computed before acquiring SQLite's write lock.
    from app.main import password_hasher

    password_hash = password_hasher.hash(secrets.token_urlsafe(64))
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        _consume_challenge(db, "google_login", payload.nonce)
        existing = db.execute(
            "SELECT user_id FROM oauth_identities WHERE provider='google' AND issuer=? AND subject=?",
            (identity["issuer"], identity["subject"]),
        ).fetchone()
        if existing:
            return _auth_result(db, existing["user_id"])
        if db.execute("SELECT 1 FROM users WHERE email=?", (identity["email"],)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Konto z tym adresem już istnieje. Zaloguj się i połącz Google w profilu.")
        created = int(time.time())
        cursor = db.execute(
            "INSERT INTO users(email,password_hash,created_at) VALUES (?,?,?)",
            (identity["email"], password_hash, created),
        )
        user_id = int(cursor.lastrowid)
        db.execute("INSERT INTO user_roles(user_id,role_name) VALUES (?, 'user')", (user_id,))
        db.execute(
            "INSERT INTO oauth_identities(user_id,provider,issuer,subject,email_at_link,created_at) VALUES (?,'google',?,?,?,?)",
            (user_id, identity["issuer"], identity["subject"], identity["email"], created),
        )
        initialize_user_accounts(db, user_id, created)
        return _auth_result(db, user_id)


@router.post("/link", status_code=204)
def link_google(payload: GoogleTokenRequest, session: AuthenticatedSession) -> Response:
    _, user = session
    identity = _verify_google_id_token(payload, expected_user=user.id)
    now = int(time.time())
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        _consume_challenge(db, "google_link", payload.nonce, user.id)
        fresh = db.execute(
            "SELECT authenticated_at FROM sessions WHERE token_hash=? AND user_id=? AND expires_at>?",
            (token_hash(session[0]), user.id, now),
        ).fetchone()
        if fresh is None or now - fresh["authenticated_at"] > 300:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Zaloguj się ponownie przed połączeniem Google.")
        existing = db.execute(
            "SELECT user_id FROM oauth_identities WHERE provider='google' AND issuer=? AND subject=?",
            (identity["issuer"], identity["subject"]),
        ).fetchone()
        if existing is not None:
            if existing["user_id"] == user.id:
                return Response(status_code=204)
            raise HTTPException(status.HTTP_409_CONFLICT, "To konto Google jest już połączone z innym użytkownikiem.")
        try:
            db.execute(
                "INSERT INTO oauth_identities(user_id,provider,issuer,subject,email_at_link,created_at) VALUES (?,'google',?,?,?,?)",
                (user.id, identity["issuer"], identity["subject"], identity["email"], now),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status.HTTP_409_CONFLICT, "To konto Google jest już połączone z innym użytkownikiem.") from None
    return Response(status_code=204)
