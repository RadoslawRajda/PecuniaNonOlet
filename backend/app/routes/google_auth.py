"""Google OpenID Connect login and explicit account linking."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    TypeAdapter,
    ValidationError,
)

from app.accounts import initialize_user_accounts
from app.adapters.google_oidc import google_certificate_request
from app.audit import write_audit_event
from app.authorization import AuthenticatedSession, current_session
from app.config import load_settings
from app.database import connect_db
from app.rate_limits import client_ip, enforce_rate_limit, ip_bucket
from app.schemas import AuthResponse, LoginResponse, User
from app.services.authentication import (
    assert_recent_authentication,
    claim_auth_challenge_attempt,
    create_login_challenge,
)
from app.sessions import issue_session

router = APIRouter(prefix="/api/auth/google", tags=["authentication"])
CHALLENGE_TTL = 300
Authenticated = Annotated[AuthenticatedSession, Depends(current_session)]


class GoogleTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_token: str = Field(min_length=20, max_length=8192)
    nonce: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True, slots=True)
class VerifiedGoogleIdentity:
    issuer: str
    subject: str
    email: str
    authoritative_mailbox: bool
    authenticated_at: int | None


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _new_challenge(
    db: sqlite3.Connection,
    kind: str,
    user_id: int | None = None,
    session_digest: str | None = None,
) -> str:
    now = int(time.time())
    db.execute("DELETE FROM auth_challenges WHERE expires_at <= ?", (now,))
    value = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO auth_challenges(challenge_hash, kind, challenge_value, user_id, created_at, expires_at, session_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (_digest(value), kind, value, user_id, now, now + CHALLENGE_TTL, session_digest),
    )
    return value


@router.post("/nonce")
def google_nonce(request: Request) -> dict[str, object]:
    enforce_rate_limit(
        [ip_bucket("google_nonce", client_ip(request.client.host if request.client else None))]
    )
    with closing(connect_db()) as db, db:
        nonce = _new_challenge(db, "google_login")
    return {"nonce": nonce, "expires_in": CHALLENGE_TTL}


@router.post("/link/nonce")
def google_link_nonce(session: Authenticated, request: Request) -> dict[str, object]:
    user = session.user
    enforce_rate_limit(
        [ip_bucket("google_link_nonce", client_ip(request.client.host if request.client else None))]
    )
    now = int(time.time())
    with closing(connect_db()) as db, db:
        assert_recent_authentication(db, session.session_id, user.id, now=now)
        nonce = _new_challenge(db, "google_link", user.id, session.session_id)
    return {"nonce": nonce, "expires_in": CHALLENGE_TTL}


def _verify_google_id_token(payload: GoogleTokenRequest) -> VerifiedGoogleIdentity:
    audiences = {
        value.strip()
        for value in load_settings().google_oauth_client_ids.split(",")
        if value.strip()
    }
    if not audiences:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Logowanie Google nie jest skonfigurowane."
        )
    try:
        from google.auth.exceptions import GoogleAuthError
        from google.oauth2 import id_token
        from requests import RequestException

        claims = id_token.verify_oauth2_token(
            payload.id_token, google_certificate_request, audience=None
        )
    except (GoogleAuthError, RequestException, ValueError):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Nie udało się zweryfikować logowania Google."
        ) from None
    if not isinstance(claims, dict):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Nie udało się zweryfikować logowania Google."
        )
    issuer = claims.get("iss")
    subject = claims.get("sub")
    email = claims.get("email")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy wystawca tokenu Google.")
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowa tożsamość Google.")
    aud = claims.get("aud")
    audiences_in_token = (
        {aud}
        if isinstance(aud, str)
        else set(aud)
        if isinstance(aud, list) and all(isinstance(item, str) for item in aud)
        else set()
    )
    if not audiences.intersection(audiences_in_token):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Token Google jest przeznaczony dla innej aplikacji."
        )
    authorized_party = claims.get("azp")
    if isinstance(aud, list) and len(aud) > 1 and authorized_party is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Token z wieloma odbiorcami nie zawiera azp."
        )
    if authorized_party is not None and (
        not isinstance(authorized_party, str) or authorized_party not in audiences
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Nieprawidłowa aplikacja logująca Google."
        )
    if not isinstance(email, str) or len(email) > 320 or claims.get("email_verified") is not True:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google nie potwierdził adresu e-mail.")
    try:
        normalized_email = TypeAdapter(EmailStr).validate_python(email).lower()
    except ValidationError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Google zwrócił nieprawidłowy adres e-mail."
        ) from None
    if claims.get("nonce") != payload.nonce:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Sesja logowania Google wygasła. Spróbuj ponownie."
        )
    authoritative = normalized_email.endswith("@gmail.com") or bool(claims.get("hd"))
    authenticated_at = claims.get("auth_time")
    if authenticated_at is not None and (
        isinstance(authenticated_at, bool) or not isinstance(authenticated_at, int)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy czas logowania Google.")
    if authenticated_at is not None and authenticated_at > int(time.time()) + 30:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy czas logowania Google.")
    return VerifiedGoogleIdentity(
        issuer="https://accounts.google.com",
        subject=subject,
        email=normalized_email,
        authoritative_mailbox=authoritative,
        authenticated_at=authenticated_at,
    )


def _consume_challenge(
    db: sqlite3.Connection,
    kind: str,
    nonce: str,
    user_id: int | None = None,
    session_digest: str | None = None,
) -> None:
    row = db.execute(
        "SELECT user_id, session_hash FROM auth_challenges WHERE challenge_hash = ? AND kind = ? AND challenge_value = ? AND expires_at > ?",
        (_digest(nonce), kind, nonce, int(time.time())),
    ).fetchone()
    if row is None or row["user_id"] != user_id or row["session_hash"] != session_digest:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Sesja logowania wygasła. Spróbuj ponownie."
        )
    db.execute("DELETE FROM auth_challenges WHERE challenge_hash = ?", (_digest(nonce),))


def _auth_result(
    db: sqlite3.Connection, user_id: int, provider_authenticated_at: int | None
) -> LoginResponse:
    user_row = db.execute(
        "SELECT u.id, u.email, r.role_name FROM users u JOIN user_roles r ON r.user_id=u.id WHERE u.id=?",
        (user_id,),
    ).fetchone()
    mfa = db.execute("SELECT enabled_at FROM user_totp WHERE user_id=?", (user_id,)).fetchone()
    if mfa and mfa["enabled_at"] is not None:
        return create_login_challenge(
            db,
            user_id,
            authentication_method="google",
            provider_authenticated_at=provider_authenticated_at,
        )
    tokens = issue_session(
        db,
        user_id,
        authentication_method="google",
        provider_authenticated_at=provider_authenticated_at,
    )
    return AuthResponse(
        user=User(id=user_row["id"], email=user_row["email"], role=user_row["role_name"]),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        refresh_expires_in=tokens.refresh_expires_in,
    )


@router.post("/login", response_model=LoginResponse)
def google_login(payload: GoogleTokenRequest, request: Request) -> LoginResponse:
    enforce_rate_limit(
        [ip_bucket("google_login", client_ip(request.client.host if request.client else None))]
    )
    now = int(time.time())
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        attempt_allowed = claim_auth_challenge_attempt(db, "google_login", payload.nonce, now=now)
    if not attempt_allowed:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Sesja logowania wygasła. Spróbuj ponownie."
        )
    identity = _verify_google_id_token(payload)
    with closing(connect_db()) as read_db:
        existing_identity = read_db.execute(
            "SELECT 1 FROM oauth_identities WHERE provider='google' AND issuer=? AND subject=?",
            (identity.issuer, identity.subject),
        ).fetchone()
        existing_email = read_db.execute(
            "SELECT 1 FROM users WHERE email=?", (identity.email,)
        ).fetchone()
    # Existing Google identities need no password hashing. New Google-only accounts
    # receive an undisclosed random credential to satisfy the current NOT NULL schema.
    random_password_hash = None
    if existing_identity is None and not identity.authoritative_mailbox:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Użyj konta Google zarządzanego przez Google lub najpierw połącz konto.",
        )
    if existing_identity is None and existing_email is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Konto z tym adresem już istnieje. Zaloguj się i połącz Google w profilu.",
        )
    if existing_identity is None:
        from app.passwords import password_hasher

        random_password_hash = password_hasher.hash(secrets.token_urlsafe(64))
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        _consume_challenge(db, "google_login", payload.nonce)
        existing = db.execute(
            "SELECT user_id FROM oauth_identities WHERE provider='google' AND issuer=? AND subject=?",
            (identity.issuer, identity.subject),
        ).fetchone()
        if existing:
            return _auth_result(db, existing["user_id"], identity.authenticated_at)
        if not identity.authoritative_mailbox:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Użyj konta Google zarządzanego przez Google lub najpierw połącz konto.",
            )
        if db.execute("SELECT 1 FROM users WHERE email=?", (identity.email,)).fetchone():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Konto z tym adresem już istnieje. Zaloguj się i połącz Google w profilu.",
            )
        created = int(time.time())
        cursor = db.execute(
            "INSERT INTO users(email,password_hash,webauthn_user_handle,has_local_password,created_at) VALUES (?,?,?,?,?)",
            (identity.email, random_password_hash, secrets.token_bytes(32), False, created),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("The inserted user did not receive a database id.")
        user_id = cursor.lastrowid
        db.execute("INSERT INTO user_roles(user_id,role_name) VALUES (?, 'user')", (user_id,))
        db.execute(
            "INSERT INTO oauth_identities(user_id,provider,issuer,subject,email_at_link,created_at) VALUES (?,'google',?,?,?,?)",
            (user_id, identity.issuer, identity.subject, identity.email, created),
        )
        initialize_user_accounts(db, user_id, created)
        return _auth_result(db, user_id, identity.authenticated_at)


@router.post("/link", status_code=204)
def link_google(payload: GoogleTokenRequest, session: Authenticated, request: Request) -> Response:
    enforce_rate_limit(
        [ip_bucket("google_link", client_ip(request.client.host if request.client else None))]
    )
    user = session.user
    identity = _verify_google_id_token(payload)
    now = int(time.time())
    if (
        identity.authenticated_at is None
        or identity.authenticated_at > now + 30
        or now - identity.authenticated_at > 300
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Uwierzytelnij się ponownie w Google przed połączeniem konta.",
        )
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        _consume_challenge(db, "google_link", payload.nonce, user.id, session.session_id)
        assert_recent_authentication(db, session.session_id, user.id, now=now)
        existing = db.execute(
            "SELECT user_id FROM oauth_identities WHERE provider='google' AND issuer=? AND subject=?",
            (identity.issuer, identity.subject),
        ).fetchone()
        if existing is not None:
            if existing["user_id"] == user.id:
                return Response(status_code=204)
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "To konto Google jest już połączone z innym użytkownikiem.",
            )
        try:
            db.execute(
                "INSERT INTO oauth_identities(user_id,provider,issuer,subject,email_at_link,created_at) VALUES (?,'google',?,?,?,?)",
                (user.id, identity.issuer, identity.subject, identity.email, now),
            )
            write_audit_event(
                db,
                actor_user_id=user.id,
                actor_role=user.role,
                action="auth.google_linked",
                entity_type="user",
                entity_id=str(user.id),
                details={"provider": "google"},
                created_at=now,
            )
        except sqlite3.IntegrityError:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "To konto Google jest już połączone z innym użytkownikiem.",
            ) from None
    return Response(status_code=204)
