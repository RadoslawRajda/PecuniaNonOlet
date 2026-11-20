"""Append-only, credential-free records for authentication and authorization events."""

from __future__ import annotations

import logging
import sqlite3
import time
from contextlib import closing
from typing import Literal

from fastapi import Request

from app.database import connect_db

logger = logging.getLogger(__name__)
EventType = Literal["authentication", "authorization", "session", "credential_change"]
AuthMethod = Literal["password", "totp", "google", "passkey", "refresh", "bearer"]


def _event_details(path: str, status_code: int) -> tuple[EventType, AuthMethod] | None:
    if path == "/api/register":
        return "authentication", "password"
    if path == "/api/login":
        return "authentication", "password"
    if path == "/api/login/mfa":
        return "authentication", "totp"
    if path == "/api/refresh" or path == "/api/logout":
        return "session", "refresh"
    if path.startswith("/api/sessions"):
        return "session", "bearer"
    if path.startswith("/api/auth/google/"):
        return "authentication", "google"
    if path.startswith("/api/passkeys/authentication/"):
        return "authentication", "passkey"
    if path.startswith("/api/passkeys/registration/") or path == "/api/passkeys":
        return "credential_change", "passkey"
    if path.startswith("/api/mfa/"):
        return "credential_change", "totp"
    if path == "/api/change-password":
        return "credential_change", "password"
    if status_code in {401, 403}:
        return "authorization", "bearer"
    return None


def _record_event(
    *,
    event_type: EventType,
    authentication_method: AuthMethod,
    outcome: Literal["success", "failure", "challenge"],
    endpoint: str,
    user_id: int | None,
) -> None:
    try:
        with closing(connect_db()) as db, db:
            db.execute(
                """INSERT INTO security_events(
                       event_type,outcome,authentication_method,endpoint,user_id,occurred_at
                   ) VALUES (?,?,?,?,?,?)""",
                (
                    event_type,
                    outcome,
                    authentication_method,
                    endpoint[:128],
                    user_id,
                    int(time.time()),
                ),
            )
    except (sqlite3.Error, OSError) as exc:
        logger.error("security_event_write_failed error_type=%s", type(exc).__name__)


async def log_security_event(request: Request, call_next):
    """Log auth flows and access denials without capturing request payloads or tokens."""
    path = request.url.path
    try:
        response = await call_next(request)
    except Exception:
        classification = _event_details(path, 500)
        if classification is not None:
            route = request.scope.get("route")
            _record_event(
                event_type=classification[0],
                authentication_method=classification[1],
                outcome="failure",
                endpoint=getattr(route, "path", "/unmatched"),
                user_id=getattr(request.state, "security_user_id", None),
            )
        raise

    classification = _event_details(path, response.status_code)
    if classification is None:
        return response

    route = request.scope.get("route")
    endpoint = getattr(route, "path", "/unmatched")
    outcome = "success" if response.status_code < 400 else "failure"
    _record_event(
        event_type=classification[0],
        authentication_method=classification[1],
        outcome=outcome,
        endpoint=endpoint,
        user_id=getattr(request.state, "security_user_id", None),
    )
    return response
