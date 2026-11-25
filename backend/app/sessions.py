"""Opaque access/refresh token lifecycle and session-family revocation."""

from __future__ import annotations

import secrets
import sqlite3
import time
from dataclasses import dataclass

from app.authorization import token_hash

ACCESS_TOKEN_LIFETIME_SECONDS = 15 * 60
REFRESH_IDLE_LIFETIME_SECONDS = 30 * 24 * 60 * 60
SESSION_ABSOLUTE_LIFETIME_SECONDS = 90 * 24 * 60 * 60
MAX_CONCURRENT_SESSIONS = 5
CONSUMED_TOKEN_RETENTION_SECONDS = 2 * SESSION_ABSOLUTE_LIFETIME_SECONDS


@dataclass(frozen=True, slots=True)
class SessionTokens:
    """Raw credentials returned exactly once to the authenticated client."""

    session_id: str
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_expires_in: int


def issue_session(
    db: sqlite3.Connection,
    user_id: int,
    *,
    authentication_method: str = "password",
    provider_authenticated_at: int | None = None,
    now: int | None = None,
) -> SessionTokens:
    """Create one token family; caller owns the surrounding SQLite transaction.

    The oldest active session is revoked when the account reaches the five-session
    limit. Raw tokens are returned to the caller but only SHA-256 hashes are stored.
    """
    if authentication_method not in {"password", "google", "passkey"}:
        raise ValueError("Unsupported authentication method")
    if authentication_method != "google" and provider_authenticated_at is not None:
        raise ValueError("Only Google sessions can carry provider authentication time")

    created_at = int(time.time()) if now is None else now
    session_id = secrets.token_urlsafe(32)
    access_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32)
    access_expires_at = created_at + ACCESS_TOKEN_LIFETIME_SECONDS
    absolute_expires_at = created_at + SESSION_ABSOLUTE_LIFETIME_SECONDS
    refresh_expires_at = min(created_at + REFRESH_IDLE_LIFETIME_SECONDS, absolute_expires_at)

    db.execute(
        """UPDATE auth_sessions SET revoked_at = ?
           WHERE session_id IN (
               SELECT session_id FROM auth_sessions
               WHERE user_id = ? AND revoked_at IS NULL AND refresh_expires_at > ?
               ORDER BY created_at DESC, session_id DESC
               LIMIT -1 OFFSET ?
           )""",
        (created_at, user_id, created_at, MAX_CONCURRENT_SESSIONS - 1),
    )
    db.execute(
        "DELETE FROM auth_sessions WHERE absolute_expires_at <= ?",
        (created_at - CONSUMED_TOKEN_RETENTION_SECONDS,),
    )
    db.execute(
        "DELETE FROM consumed_refresh_tokens WHERE consumed_at < ?",
        (created_at - CONSUMED_TOKEN_RETENTION_SECONDS,),
    )
    db.execute(
        """INSERT INTO auth_sessions(
               session_id, user_id, access_token_hash, access_expires_at,
               refresh_token_hash, refresh_expires_at, absolute_expires_at,
               created_at, authenticated_at, authentication_method,
               provider_authenticated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            user_id,
            token_hash(access_token),
            access_expires_at,
            token_hash(refresh_token),
            refresh_expires_at,
            absolute_expires_at,
            created_at,
            created_at,
            authentication_method,
            provider_authenticated_at,
        ),
    )
    return SessionTokens(
        session_id=session_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_LIFETIME_SECONDS,
        refresh_expires_in=refresh_expires_at - created_at,
    )


def rotate_refresh_token(
    db: sqlite3.Connection, refresh_token: str, *, now: int
) -> SessionTokens | None:
    """Rotate a refresh token atomically and revoke its family on reuse.

    The caller owns a ``BEGIN IMMEDIATE`` transaction. A token seen in the consumed
    table proves reuse; its entire session family is revoked before returning None.
    """
    presented_hash = token_hash(refresh_token)
    row = db.execute(
        """SELECT session_id, absolute_expires_at, refresh_expires_at
           FROM auth_sessions WHERE refresh_token_hash = ? AND revoked_at IS NULL""",
        (presented_hash,),
    ).fetchone()
    if row is None:
        consumed = db.execute(
            "SELECT session_id FROM consumed_refresh_tokens WHERE token_hash = ?",
            (presented_hash,),
        ).fetchone()
        if consumed is not None:
            db.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE session_id = ? AND revoked_at IS NULL",
                (now, consumed["session_id"]),
            )
        return None

    if row["refresh_expires_at"] <= now or row["absolute_expires_at"] <= now:
        db.execute(
            "UPDATE auth_sessions SET revoked_at = ? WHERE session_id = ?",
            (now, row["session_id"]),
        )
        return None

    access_token = secrets.token_urlsafe(32)
    next_refresh_token = secrets.token_urlsafe(32)
    access_expires_at = min(now + ACCESS_TOKEN_LIFETIME_SECONDS, row["absolute_expires_at"])
    refresh_expires_at = min(now + REFRESH_IDLE_LIFETIME_SECONDS, row["absolute_expires_at"])
    db.execute(
        "INSERT INTO consumed_refresh_tokens(token_hash, session_id, consumed_at) VALUES (?, ?, ?)",
        (presented_hash, row["session_id"], now),
    )
    db.execute(
        """UPDATE auth_sessions SET access_token_hash = ?, access_expires_at = ?,
                  refresh_token_hash = ?, refresh_expires_at = ?
           WHERE session_id = ? AND revoked_at IS NULL""",
        (
            token_hash(access_token),
            access_expires_at,
            token_hash(next_refresh_token),
            refresh_expires_at,
            row["session_id"],
        ),
    )
    return SessionTokens(
        session_id=row["session_id"],
        access_token=access_token,
        refresh_token=next_refresh_token,
        expires_in=access_expires_at - now,
        refresh_expires_in=refresh_expires_at - now,
    )


def revoke_session(db: sqlite3.Connection, session_id: str, *, now: int) -> None:
    """Revoke a session family and all access tokens issued by it."""
    db.execute(
        "UPDATE auth_sessions SET revoked_at = ? WHERE session_id = ? AND revoked_at IS NULL",
        (now, session_id),
    )


def revoke_user_sessions(db: sqlite3.Connection, user_id: int, *, now: int) -> None:
    """Revoke every active session after a credential or MFA change."""
    db.execute(
        "UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
        (now, user_id),
    )
