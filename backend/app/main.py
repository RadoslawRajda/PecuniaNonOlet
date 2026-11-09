"""Authentication API for clients on the local network."""

from __future__ import annotations

import hashlib
import html
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, closing

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from pwdlib import PasswordHash

from app.database import connect_db, migrate_database


SESSION_LIFETIME_SECONDS = 7 * 24 * 60 * 60
password_hasher = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hasher.hash("invalid-account-password")
bearer = HTTPBearer(auto_error=False)


class LoginCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class RegisterCredentials(LoginCredentials):
    password: str = Field(min_length=8, max_length=128)


class User(BaseModel):
    id: int
    email: EmailStr


class AuthResponse(BaseModel):
    user: User
    token: str
    token_type: str = "bearer"
    expires_in: int = SESSION_LIFETIME_SECONDS


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token(db: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
    db.execute(
        "INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (token_hash(token), user_id, now + SESSION_LIFETIME_SECONDS),
    )
    return token


def current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> tuple[str, User]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Brak tokenu dostępu.")

    token = credentials.credentials
    with closing(connect_db()) as db:
        row = db.execute(
            """
            SELECT u.id, u.email FROM sessions AS s
            JOIN users AS u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_at > ?
            """,
            (token_hash(token), int(time.time())),
        ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")
    return token, User(id=row["id"], email=row["email"])


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate_database()
    yield


app = FastAPI(title="PecuniaNonOlet API", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def diagnostics(request: Request) -> HTMLResponse:
    ip = os.getenv("LAN_IP", "")
    address = f"http://{ip}:8000" if ip else "Nie ustawiono (uruchom przez skrypt)."
    mdns_state = "Ogłaszana przez skrypt" if ip else "Nie uruchomiono przez skrypt"
    with closing(connect_db()) as db:
        db.execute("SELECT 1").fetchone()
    rows = (
        ("API", "działa"),
        ("SQLite", "działa"),
        ("Adres LAN", address),
        ("Nazwa mDNS", "pecunianonolet.local"),
        ("Usługa mDNS", "_pecunianonolet._tcp.local."),
        ("Stan mDNS", mdns_state),
        ("Klient", request.client.host if request.client else "nieznany"),
    )
    details = "\n".join(
        f"<dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd>"
        for label, value in rows
    )
    return HTMLResponse(
        "<!doctype html><html lang=\"pl\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>PecuniaNonOlet — diagnostyka</title></head><body>"
        "<h1>PecuniaNonOlet - diagnostyka</h1><dl>"
        f"{details}</dl><p><a href=\"/docs\">Dokumentacja API</a> · "
        "<a href=\"/health\">Health check</a></p></body></html>"
    )


@app.get("/health")
def health() -> dict[str, str]:
    with closing(connect_db()) as db:
        db.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@app.post("/api/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterCredentials) -> AuthResponse:
    password_hash = password_hasher.hash(payload.password)
    with closing(connect_db()) as db:
        try:
            with db:
                cursor = db.execute(
                    "INSERT INTO users(email, password_hash, created_at) VALUES (?, ?, ?)",
                    (payload.email, password_hash, int(time.time())),
                )
                user_id = int(cursor.lastrowid)
                token = issue_token(db, user_id)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "Ten adres e-mail jest już zajęty.") from exc
    return AuthResponse(user=User(id=user_id, email=payload.email), token=token)


@app.post("/api/login", response_model=AuthResponse)
def login(payload: LoginCredentials) -> AuthResponse:
    with closing(connect_db()) as db:
        row = db.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?", (payload.email,)
        ).fetchone()
        stored_hash = row["password_hash"] if row is not None else DUMMY_PASSWORD_HASH
        valid_password = password_hasher.verify(payload.password, stored_hash)
        if row is None or not valid_password:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Błędny e-mail lub hasło.")
        with db:
            token = issue_token(db, row["id"])
    return AuthResponse(user=User(id=row["id"], email=row["email"]), token=token)


@app.get("/api/me", response_model=User)
def me(session: tuple[str, User] = Depends(current_session)) -> User:
    return session[1]


@app.post("/api/logout", status_code=204, response_class=Response)
def logout(session: tuple[str, User] = Depends(current_session)) -> Response:
    with closing(connect_db()) as db:
        with db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(session[0]),))
    return Response(status_code=204)
