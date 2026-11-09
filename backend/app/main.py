"""Authentication API for clients on the local network."""

from __future__ import annotations

import html
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, closing

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from pwdlib import PasswordHash

from app.authorization import current_session, token_hash
from app.database import connect_db, migrate_database
from app.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginCredentials,
    RegisterCredentials,
    User,
)

SESSION_LIFETIME_SECONDS = 7 * 24 * 60 * 60
password_hasher = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hasher.hash("invalid-account-password")
def issue_token(db: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
    db.execute(
        "INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (token_hash(token), user_id, now + SESSION_LIFETIME_SECONDS),
    )
    return token


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
                db.execute("INSERT INTO user_roles(user_id, role_name) VALUES (?, 'user')", (user_id,))
                token = issue_token(db, user_id)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "Ten adres e-mail jest już zajęty.") from exc
    return AuthResponse(user=User(id=user_id, email=payload.email, role="user"), token=token)


@app.post("/api/login", response_model=AuthResponse)
def login(payload: LoginCredentials) -> AuthResponse:
    with closing(connect_db()) as db:
        row = db.execute(
            """
            SELECT u.id, u.email, u.password_hash, r.role_name
            FROM users AS u JOIN user_roles AS r ON r.user_id = u.id
            WHERE u.email = ?
            """,
            (payload.email,),
        ).fetchone()
        stored_hash = row["password_hash"] if row is not None else DUMMY_PASSWORD_HASH
        valid_password = password_hasher.verify(payload.password, stored_hash)
        if row is None or not valid_password:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Błędny e-mail lub hasło.")
        with db:
            token = issue_token(db, row["id"])
    return AuthResponse(
        user=User(id=row["id"], email=row["email"], role=row["role_name"]), token=token
    )


@app.post("/api/change-password", response_model=ChangePasswordResponse)
def change_password(
    payload: ChangePasswordRequest,
    session: tuple[str, User] = Depends(current_session),
) -> ChangePasswordResponse:
    session_token, user = session
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        active_session = db.execute(
            "SELECT 1 FROM sessions WHERE token_hash = ? AND user_id = ? AND expires_at > ?",
            (token_hash(session_token), user.id, int(time.time())),
        ).fetchone()
        if active_session is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")
        row = db.execute("SELECT password_hash FROM users WHERE id = ?", (user.id,)).fetchone()
        if row is None or not password_hasher.verify(payload.current_password, row["password_hash"]):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Obecne hasło jest nieprawidłowe.")
        if password_hasher.verify(payload.new_password, row["password_hash"]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nowe hasło musi różnić się od obecnego.")
        new_hash = password_hasher.hash(payload.new_password)
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user.id,))
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user.id))
    return ChangePasswordResponse(
        message="Hasło zostało zmienione. Zaloguj się ponownie.",
        reauthentication_required=True,
    )


@app.get("/api/me", response_model=User)
def me(session: tuple[str, User] = Depends(current_session)) -> User:
    return session[1]


@app.post("/api/logout", status_code=204, response_class=Response)
def logout(session: tuple[str, User] = Depends(current_session)) -> Response:
    with closing(connect_db()) as db, db:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(session[0]),))
    return Response(status_code=204)
