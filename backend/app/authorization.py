"""Opaque access-token authentication and role authorization dependencies."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr

from app.database import connect_db
from app.schemas import User

bearer = HTTPBearer(auto_error=False)


def token_hash(token: str) -> str:
    """Hash a high-entropy opaque credential before database lookup or storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    """Request identity with the raw access token hidden from repr and logs."""

    session_id: str
    user: User
    access_token: SecretStr


def current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),  # noqa: B008
) -> AuthenticatedSession:
    """Resolve an active, unexpired opaque access token to its session family."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Brak tokenu dostępu.")

    token = credentials.credentials
    now = int(time.time())
    with closing(connect_db()) as db:
        row = db.execute(
            """SELECT s.session_id, u.id, u.email, r.role_name
               FROM auth_sessions AS s
               JOIN users AS u ON u.id = s.user_id
               JOIN user_roles AS r ON r.user_id = u.id
               WHERE s.access_token_hash = ? AND s.access_expires_at > ?
                 AND s.refresh_expires_at > ? AND s.absolute_expires_at > ?
                 AND s.revoked_at IS NULL""",
            (token_hash(token), now, now, now),
        ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")
    return AuthenticatedSession(
        session_id=row["session_id"],
        user=User(id=row["id"], email=row["email"], role=row["role_name"]),
        access_token=SecretStr(token),
    )


def require_roles(*allowed_roles: str) -> Callable[..., User]:
    allowed = frozenset(allowed_roles)
    if not allowed or not allowed <= {"user", "analyst"}:
        raise ValueError("Należy podać co najmniej jedną poprawną rolę.")

    def dependency(session: AuthenticatedSession = Depends(current_session)) -> User:
        user = session.user
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Brak wymaganych uprawnień.")
        return user

    return dependency
