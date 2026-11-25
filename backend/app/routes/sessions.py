"""User-visible session inventory and authenticated revocation operations."""

from __future__ import annotations

import re
import time
from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.authorization import AuthenticatedSession, current_session
from app.database import connect_db
from app.rate_limits import client_ip, enforce_rate_limit, ip_bucket
from app.schemas import RevokeSessionsResponse, SessionListResponse, SessionSummary
from app.services.authentication import assert_recent_authentication
from app.sessions import revoke_session

router = APIRouter(prefix="/api/sessions", tags=["authentication"])
Authenticated = Annotated[AuthenticatedSession, Depends(current_session)]
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


def _rate_limit(request: Request, action: str) -> None:
    address = client_ip(request.client.host if request.client else None)
    enforce_rate_limit([ip_bucket(action, address)], limits=[30])


@router.get("", response_model=SessionListResponse)
def list_sessions(session: Authenticated, request: Request) -> SessionListResponse:
    _rate_limit(request, "session_list")
    user = session.user
    now = int(time.time())
    with closing(connect_db()) as db:
        rows = db.execute(
            """SELECT session_id,authentication_method,created_at,authenticated_at
               FROM auth_sessions WHERE user_id=? AND revoked_at IS NULL
                 AND refresh_expires_at>? AND absolute_expires_at>?
               ORDER BY created_at DESC,session_id DESC""",
            (user.id, now, now),
        ).fetchall()
    return SessionListResponse(
        current_session_id=session.session_id,
        sessions=[
            SessionSummary(
                session_id=row["session_id"],
                authentication_method=row["authentication_method"],
                created_at=row["created_at"],
                authenticated_at=row["authenticated_at"],
                current=row["session_id"] == session.session_id,
            )
            for row in rows
        ],
    )


@router.delete("/{session_id}", status_code=204, response_class=Response)
def revoke_other_session(
    session_id: str,
    session: Authenticated,
    request: Request,
) -> Response:
    _rate_limit(request, "session_revoke")
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono sesji.")
    if session_id == session.session_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Aby zakończyć bieżącą sesję, użyj wylogowania.",
        )
    user = session.user
    now = int(time.time())
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        assert_recent_authentication(db, session.session_id, user.id, now=now)
        target = db.execute(
            "SELECT session_id FROM auth_sessions WHERE session_id=? AND user_id=? AND revoked_at IS NULL",
            (session_id, user.id),
        ).fetchone()
        if target is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono sesji.")
        revoke_session(db, session_id, now=now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/revoke-others", response_model=RevokeSessionsResponse)
def revoke_other_sessions(
    session: Authenticated,
    request: Request,
) -> RevokeSessionsResponse:
    _rate_limit(request, "session_revoke")
    user = session.user
    now = int(time.time())
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        assert_recent_authentication(db, session.session_id, user.id, now=now)
        cursor = db.execute(
            """UPDATE auth_sessions SET revoked_at=? WHERE user_id=? AND session_id!=?
               AND revoked_at IS NULL""",
            (now, user.id, session.session_id),
        )
    return RevokeSessionsResponse(revoked_count=cursor.rowcount)
