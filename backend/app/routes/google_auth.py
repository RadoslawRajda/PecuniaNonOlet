"""Google OpenID Connect login and explicit account linking."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import closing
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

from app.adapters.google_oidc import google_certificate_request
from app.authorization import AuthenticatedSession, current_session
from app.config import load_settings
from app.database import connect_db
from app.rate_limits import client_ip, enforce_rate_limit, ip_bucket
from app.schemas import AuthResponse, LoginResponse
from app.services.authentication import (
    assert_recent_authentication,
)
from app.services.google_accounts import (
    VerifiedGoogleIdentity,
    link_google_identity,
    login_with_google,
    reauthenticate_google_identity,
)

router = APIRouter(prefix="/api/auth/google", tags=["authentication"])
CHALLENGE_TTL = 300
Authenticated = Annotated[AuthenticatedSession, Depends(current_session)]


class GoogleTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_token: str = Field(min_length=20, max_length=8192, repr=False)
    nonce: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$", repr=False)


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


@router.get("/status")
def google_connection_status(session: Authenticated) -> dict[str, bool]:
    """Report this user's Google connection and local-password availability."""
    with closing(connect_db()) as db:
        linked = db.execute(
            "SELECT 1 FROM oauth_identities WHERE user_id=? AND provider='google' LIMIT 1",
            (session.user.id,),
        ).fetchone()
        local_password = db.execute(
            "SELECT has_local_password FROM users WHERE id=?",
            (session.user.id,),
        ).fetchone()
    return {
        "linked": linked is not None,
        "has_local_password": bool(local_password and local_password["has_local_password"]),
    }


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


@router.post("/reauth/nonce")
def google_reauth_nonce(session: Authenticated, request: Request) -> dict[str, object]:
    """Issue a one-use challenge bound to an existing session and Google identity."""
    enforce_rate_limit(
        [
            ip_bucket(
                "google_reauth_nonce", client_ip(request.client.host if request.client else None)
            )
        ]
    )
    with closing(connect_db()) as db, db:
        linked = db.execute(
            "SELECT 1 FROM oauth_identities WHERE user_id=? AND provider='google' LIMIT 1",
            (session.user.id,),
        ).fetchone()
        if linked is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Konto Google nie jest połączone.")
        nonce = _new_challenge(db, "google_reauth", session.user.id, session.session_id)
    return {"nonce": nonce, "expires_in": CHALLENGE_TTL}


@router.post(
    "/reauth",
    response_model=AuthResponse,
    summary="Ponownie potwierdź tożsamość przez Google",
    description=(
        "Wymaga aktywnej sesji, jednorazowego nonce i podpisanego ID tokenu z "
        "`auth_time` nie starszym niż pięć minut. Sukces unieważnia dotychczasową "
        "sesję i zwraca nową parę tokenów; klient musi ją zapisać."
    ),
)
def google_reauthenticate(
    payload: GoogleTokenRequest, session: Authenticated, request: Request
) -> AuthResponse:
    enforce_rate_limit(
        [ip_bucket("google_reauth", client_ip(request.client.host if request.client else None))]
    )
    return reauthenticate_google_identity(
        payload.nonce, session, lambda: _verify_google_id_token(payload)
    )


def _verify_google_id_token(payload: GoogleTokenRequest) -> VerifiedGoogleIdentity:
    settings = load_settings()
    audiences = {
        value.strip()
        for value in (settings.google_ios_client_id, settings.google_android_client_id)
        if value.strip()
    }
    if not audiences:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Logowanie Google nie jest skonfigurowane."
        )
    _require_google_rs256_header(payload.id_token)
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


def _require_google_rs256_header(token: str) -> None:
    """Reject non-Google JWT algorithms before asking the verifier to fetch keys.

    The untrusted header is used only as an allowlist gate; google-auth still
    verifies the signature and claims before any identity data is accepted.
    """
    parts = token.split(".")
    if len(parts) != 3 or not 1 <= len(parts[0]) <= 1024:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy token Google.")
    encoded = parts[0]
    try:
        header_bytes = base64.b64decode(
            encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
        )
        header = json.loads(header_bytes)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy token Google.") from None
    if not isinstance(header, dict) or header.get("alg") != "RS256" or "crit" in header:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy token Google.")


@router.post("/login", response_model=LoginResponse)
def google_login(payload: GoogleTokenRequest, request: Request) -> LoginResponse:
    enforce_rate_limit(
        [ip_bucket("google_login", client_ip(request.client.host if request.client else None))]
    )
    return login_with_google(payload.nonce, lambda: _verify_google_id_token(payload))


@router.post("/link", status_code=204)
def link_google(payload: GoogleTokenRequest, session: Authenticated, request: Request) -> Response:
    enforce_rate_limit(
        [ip_bucket("google_link", client_ip(request.client.host if request.client else None))]
    )
    identity = _verify_google_id_token(payload)
    link_google_identity(payload.nonce, session, identity)
    return Response(status_code=204)
