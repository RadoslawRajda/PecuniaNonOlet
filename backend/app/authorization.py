"""Session authentication and role authorization dependencies."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from contextlib import closing

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database import connect_db
from app.schemas import User

bearer = HTTPBearer(auto_error=False)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),  # noqa: B008
) -> tuple[str, User]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Brak tokenu dostępu.")

    token = credentials.credentials
    with closing(connect_db()) as db:
        row = db.execute(
            """
            SELECT u.id, u.email, r.role_name
            FROM sessions AS s
            JOIN users AS u ON u.id = s.user_id
            JOIN user_roles AS r ON r.user_id = u.id
            WHERE s.token_hash = ? AND s.expires_at > ?
            """,
            (token_hash(token), int(time.time())),
        ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")
    return token, User(id=row["id"], email=row["email"], role=row["role_name"])


def require_roles(*allowed_roles: str) -> Callable[..., User]:
    allowed = frozenset(allowed_roles)
    if not allowed or not allowed <= {"user", "analyst"}:
        raise ValueError("Należy podać co najmniej jedną poprawną rolę.")

    def dependency(session: tuple[str, User] = Depends(current_session)) -> User:
        user = session[1]
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Brak wymaganych uprawnień.")
        return user

    return dependency
