"""Google identity login and explicit linking use cases."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass

from fastapi import HTTPException, status

from app.accounts import initialize_user_accounts
from app.audit import write_audit_event
from app.authorization import AuthenticatedSession, token_hash
from app.database import connect_db
from app.schemas import AuthResponse, LoginResponse, User
from app.services.authentication import (
    assert_recent_authentication,
    claim_auth_challenge_attempt,
    create_login_challenge,
)
from app.sessions import issue_session, revoke_session


@dataclass(frozen=True, slots=True)
class VerifiedGoogleIdentity:
    issuer: str
    subject: str
    email: str
    authoritative_mailbox: bool
    authenticated_at: int | None
    issued_at: int
    android_native_token: bool


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def consume_google_challenge(
    db: sqlite3.Connection,
    kind: str,
    nonce: str,
    user_id: int | None = None,
    session_id: str | None = None,
) -> None:
    """Consume only a live challenge bound to the expected user and session."""
    row = db.execute(
        """SELECT user_id, session_hash FROM auth_challenges
           WHERE challenge_hash = ? AND kind = ? AND challenge_value = ? AND expires_at > ?""",
        (_digest(nonce), kind, nonce, int(time.time())),
    ).fetchone()
    if row is None or row["user_id"] != user_id or row["session_hash"] != session_id:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Sesja logowania wygasła. Spróbuj ponownie."
        )
    db.execute("DELETE FROM auth_challenges WHERE challenge_hash = ?", (_digest(nonce),))


def _google_user_id(db: sqlite3.Connection, identity: VerifiedGoogleIdentity) -> int | None:
    row = db.execute(
        """SELECT user_id FROM oauth_identities
           WHERE provider='google' AND issuer=? AND subject=?""",
        (identity.issuer, identity.subject),
    ).fetchone()
    return row["user_id"] if row is not None else None


def _email_taken(db: sqlite3.Connection, email: str) -> bool:
    return db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone() is not None


def _require_new_google_identity_allowed(
    db: sqlite3.Connection, identity: VerifiedGoogleIdentity
) -> None:
    if not identity.authoritative_mailbox:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Użyj konta Google zarządzanego przez Google lub najpierw połącz konto.",
        )
    if _email_taken(db, identity.email):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Konto z tym adresem już istnieje. Zaloguj się i połącz Google w profilu.",
        )


def _create_google_user(
    db: sqlite3.Connection, identity: VerifiedGoogleIdentity, random_password_hash: str
) -> int:
    created = int(time.time())
    cursor = db.execute(
        """INSERT INTO users(
            email,password_hash,webauthn_user_handle,has_local_password,password_origin,created_at
        ) VALUES (?,?,?,?,?,?)""",
        (
            identity.email,
            random_password_hash,
            secrets.token_bytes(32),
            False,
            "google_generated",
            created,
        ),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("The inserted user did not receive a database id.")
    user_id = cursor.lastrowid
    db.execute("INSERT INTO user_roles(user_id,role_name) VALUES (?, 'user')", (user_id,))
    db.execute(
        """INSERT INTO oauth_identities(
            user_id,provider,issuer,subject,email_at_link,created_at
        ) VALUES (?,'google',?,?,?,?)""",
        (user_id, identity.issuer, identity.subject, identity.email, created),
    )
    initialize_user_accounts(db, user_id, created)
    return user_id


def _login_result(
    db: sqlite3.Connection, user_id: int, provider_authenticated_at: int | None
) -> LoginResponse:
    mfa = db.execute("SELECT enabled_at FROM user_totp WHERE user_id=?", (user_id,)).fetchone()
    if mfa and mfa["enabled_at"] is not None:
        return create_login_challenge(
            db,
            user_id,
            authentication_method="google",
            provider_authenticated_at=provider_authenticated_at,
        )
    identity = db.execute(
        """SELECT u.id, u.email, r.role_name FROM users u
           JOIN user_roles r ON r.user_id=u.id WHERE u.id=?""",
        (user_id,),
    ).fetchone()
    if identity is None:
        raise RuntimeError("Google identity points to a missing user")
    tokens = issue_session(
        db,
        user_id,
        authentication_method="google",
        provider_authenticated_at=provider_authenticated_at,
    )
    return AuthResponse(
        user=User(id=identity["id"], email=identity["email"], role=identity["role_name"]),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        refresh_expires_in=tokens.refresh_expires_in,
    )


def login_with_google(
    nonce: str, verify_identity: Callable[[], VerifiedGoogleIdentity]
) -> LoginResponse:
    """Count an OIDC challenge attempt, verify the token, then log in atomically.

    The callback verifies a signed ID token outside the SQLite write lock. A new
    Google user is created only when the mailbox is authoritative and no local
    user already owns the email. Existing identities match provider/issuer/subject.
    """
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        allowed = claim_auth_challenge_attempt(db, "google_login", nonce, now=int(time.time()))
    if not allowed:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Sesja logowania wygasła. Spróbuj ponownie."
        )
    identity = verify_identity()
    with closing(connect_db()) as db:
        existing_user_id = _google_user_id(db, identity)
        if existing_user_id is None:
            _require_new_google_identity_allowed(db, identity)
    random_password_hash: str | None = None
    if existing_user_id is None:
        # The schema still requires a password hash for Google-only users.
        from app.passwords import password_hasher

        random_password_hash = password_hasher.hash(secrets.token_urlsafe(64))
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        consume_google_challenge(db, "google_login", nonce)
        user_id = _google_user_id(db, identity)
        if user_id is None:
            _require_new_google_identity_allowed(db, identity)
            if random_password_hash is None:
                raise RuntimeError("Missing generated credential for new Google user")
            user_id = _create_google_user(db, identity, random_password_hash)
        return _login_result(db, user_id, identity.authenticated_at)


def link_google_identity(
    nonce: str, session: AuthenticatedSession, identity: VerifiedGoogleIdentity
) -> None:
    """Link a fresh Google identity to the current user, never by email alone.

    The nonce, recent local authentication, ownership check, insert and audit share
    one BEGIN IMMEDIATE transaction. Repeating a link for the same user is harmless.
    """
    now = int(time.time())
    # Some native Google sign-in APIs (including Android Credential Manager)
    # do not return auth_time. In that case, a newly issued, nonce-bound ID
    # token is the provider proof; the app session is separately required to
    # have been recently authenticated below.
    if identity.authenticated_at is None and not identity.android_native_token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Uwierzytelnij się ponownie w Google przed połączeniem konta.",
        )
    provider_proof_at = (
        identity.authenticated_at
        if identity.authenticated_at is not None
        else identity.issued_at
    )
    allowed_future_skew = 30 if identity.authenticated_at is not None else 60
    if provider_proof_at > now + allowed_future_skew or now - provider_proof_at > 300:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Wygeneruj nowe potwierdzenie logowania Google przed połączeniem konta.",
        )
    user = session.user
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        consume_google_challenge(db, "google_link", nonce, user.id, session.session_id)
        assert_recent_authentication(db, session.session_id, user.id, now=now)
        existing_user_id = _google_user_id(db, identity)
        if existing_user_id is not None:
            if existing_user_id == user.id:
                return
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "To konto Google jest już połączone z innym użytkownikiem.",
            )
        try:
            db.execute(
                """INSERT INTO oauth_identities(
                    user_id,provider,issuer,subject,email_at_link,created_at
                ) VALUES (?,'google',?,?,?,?)""",
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


def reauthenticate_google_identity(
    nonce: str,
    session: AuthenticatedSession,
    verify_identity: Callable[[], VerifiedGoogleIdentity],
) -> AuthResponse:
    """Replace one session after a fresh Google ceremony.

    Count the bound challenge attempt before token verification; consume it only
    after matching the verified issuer and subject to this user and live access
    token. Revocation and issuance share the challenge-consumption transaction.
    The caller must persist the returned token pair before using sensitive APIs.
    """
    now = int(time.time())
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        allowed = claim_auth_challenge_attempt(
            db,
            "google_reauth",
            nonce,
            now=now,
            user_id=session.user.id,
            session_id=session.session_id,
        )
    if not allowed:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wyzwanie Google wygasło.")
    identity = verify_identity()
    if identity.authenticated_at is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Google nie zwrócił wymaganego potwierdzenia wieku sesji. "
            "Skonfiguruj Session age claims dla aplikacji Google.",
        )
    if identity.authenticated_at > now + 30 or now - identity.authenticated_at > 300:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Google nie potwierdził świeżego logowania."
        )
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        consume_google_challenge(db, "google_reauth", nonce, session.user.id, session.session_id)
        if _google_user_id(db, identity) != session.user.id:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "To konto Google nie należy do użytkownika."
            )
        live_session = db.execute(
            """SELECT 1 FROM auth_sessions
               WHERE session_id=? AND user_id=? AND access_token_hash=?
                 AND access_expires_at>? AND refresh_expires_at>?
                 AND absolute_expires_at>? AND revoked_at IS NULL""",
            (
                session.session_id,
                session.user.id,
                token_hash(session.access_token.get_secret_value()),
                now,
                now,
                now,
            ),
        ).fetchone()
        if live_session is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")
        revoke_session(db, session.session_id, now=now)
        tokens = issue_session(
            db,
            session.user.id,
            authentication_method="google",
            provider_authenticated_at=identity.authenticated_at,
            now=now,
        )
    return AuthResponse(
        user=session.user,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        refresh_expires_in=tokens.refresh_expires_in,
    )
