"""Session issuance shared by password and multi-factor login flows."""

from __future__ import annotations

import secrets
import sqlite3
import time

from app.authorization import token_hash

SESSION_LIFETIME_SECONDS = 7 * 24 * 60 * 60


def issue_token(db: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
    db.execute(
        "INSERT INTO sessions(token_hash, user_id, expires_at, authenticated_at) VALUES (?, ?, ?, ?)",
        (token_hash(token), user_id, now + SESSION_LIFETIME_SECONDS, now),
    )
    return token
