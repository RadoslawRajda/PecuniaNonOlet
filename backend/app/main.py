"""Authentication API for clients on the local network."""

from __future__ import annotations

import html
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager, closing
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pwdlib import PasswordHash

from app.accounts import initialize_user_accounts
from app.authorization import current_session, token_hash
from app.database import connect_db, migrate_database
from app.routes.analytics import router as analytics_router
from app.routes.exchange import router as exchange_router
from app.routes.finance import router as finance_router
from app.routes.google_auth import router as google_auth_router
from app.routes.mfa import router as mfa_router
from app.routes.passkeys import router as passkeys_router
from app.routes.profile_photos import (
    ProfilePhotoBodyLimitMiddleware,
)
from app.routes.profile_photos import (
    router as profile_photos_router,
)
from app.routes.transfers import router as transfers_router
from app.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginCredentials,
    LoginResponse,
    PublicRegisterRequest,
    User,
)
from app.sessions import issue_token

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

password_hasher = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hasher.hash("invalid-account-password")
logger = logging.getLogger(__name__)


def verify_turnstile_token(token: str, remote_ip: str | None = None) -> None:
    secret = os.getenv("TURNSTILE_SECRET_KEY", "").strip()
    if not secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Weryfikacja CAPTCHA jest chwilowo niedostępna.",
        )

    try:
        import httpx

        response = httpx.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": secret, "response": token, **({"remoteip": remote_ip} if remote_ip else {})},
            timeout=5.0,
        )
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("Turnstile verification service unavailable")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Weryfikacja CAPTCHA jest chwilowo niedostępna.",
        ) from None

    if not isinstance(result, dict) or result.get("success") is not True:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Weryfikacja CAPTCHA nie powiodła się.")

    expected_hostname = os.getenv("TURNSTILE_EXPECTED_HOSTNAME", "").strip().lower()
    hostname = result.get("hostname")
    if expected_hostname and (
        not isinstance(hostname, str) or hostname.lower() != expected_hostname
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Weryfikacja CAPTCHA nie powiodła się.")

    # Cloudflare's published test secret intentionally omits action and hostname claims.
    is_test_secret = secret == "1x0000000000000000000000000000000AA"
    if not is_test_secret and result.get("action") != "register":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Weryfikacja CAPTCHA nie powiodła się.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate_database()
    yield


app = FastAPI(title="PecuniaNonOlet API", lifespan=lifespan)
app.include_router(finance_router)
app.include_router(transfers_router)
app.include_router(exchange_router)
app.include_router(profile_photos_router)
app.include_router(analytics_router)
app.include_router(mfa_router)
app.include_router(google_auth_router)
app.include_router(passkeys_router)
app.add_middleware(ProfilePhotoBodyLimitMiddleware)


@app.exception_handler(sqlite3.OperationalError)
async def handle_sqlite_operational_error(request: Request, exc: sqlite3.OperationalError):
    message = str(exc).lower()
    if "database" in message and ("locked" in message or "busy" in message):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Baza jest chwilowo zajęta. Ponów żądanie."},
            headers={"Retry-After": "1"},
        )
    raise exc


@app.middleware("http")
async def prevent_api_response_caching(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        if "no-store" not in response.headers.get("Cache-Control", "").lower():
            response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def diagnostics(request: Request) -> HTMLResponse:
    ip = os.getenv("LAN_IP", "")
    from app.local_tls import ensure_local_tls

    tls_files = ensure_local_tls(Path(__file__).resolve().parents[1] / "data" / "tls", ip or "127.0.0.1")
    fingerprint = html.escape(tls_files.ca_fingerprint_sha256)
    return HTMLResponse(
        "<!doctype html><html lang=\"pl\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>PecuniaNonOlet — konfiguracja HTTPS</title></head><body>"
        "<h1>Konfiguracja bezpiecznego połączenia</h1>"
        "<p>Ta strona służy tylko do zainstalowania lokalnego certyfikatu zaufania. "
        "Nie loguj się ani nie wysyłaj tutaj danych konta.</p>"
        "<ol><li>Pobierz publiczny certyfikat CA: "
        "<a href=\"/local-root-ca.cer\" download>Pobierz certyfikat</a>.</li>"
        "<li><strong>iPhone:</strong> po pobraniu profilu otwórz "
        "Ustawienia &gt; Ogólne &gt; VPN i urządzenia zarządzane, wybierz pobrany profil "
        "i zainstaluj go. Następnie otwórz Ustawienia &gt; Ogólne &gt; To urządzenie... "
        "&gt; Ustawienia zaufania certyfikatów i włącz pełne zaufanie dla tego CA. "
        "<strong>Android:</strong> "
        "zainstaluj plik jako certyfikat CA w ustawieniach zabezpieczeń telefonu "
        "(nazwy opcji zależą od producenta).</li>"
        "<li>Przed zaufaniem porównaj odcisk SHA-256 poniżej z wartością "
        "wypisaną w terminalu komputera uruchamiającego backend.</li></ol>"
        f"<p><strong>Odcisk SHA-256 CA:</strong><br><code>{fingerprint}</code></p>"
        "<h2>Połączenie backendu</h2>"
        "<p><strong>HTTPS — bezpieczne połączenie aplikacji:</strong><br>"
        "<a href=\"https://pecunianonolet.local:8000/\">"
        "https://pecunianonolet.local:8000/</a></p>"
        "<p>Domena mDNS: <code>pecunianonolet.local</code><br>"
        "Swagger UI: <a href=\"https://pecunianonolet.local:8000/docs\">"
        "https://pecunianonolet.local:8000/docs</a></p>"
        "<p>API i pozostałe strony są dostępne tylko przez HTTPS.</p>"
        "<p>Nie instaluj certyfikatu, jeśli odcisk nie zgadza się z wartością "
        "pokazaną na komputerze. Lokalny certyfikat jest przeznaczony do "
        "developmentu w zaufanej sieci.</p></body></html>",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/health")
def health() -> dict[str, str]:
    with closing(connect_db()) as db:
        db.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@app.get("/local-root-ca.cer", include_in_schema=False)
def download_local_ca() -> FileResponse:
    """Serve only the public local CA certificate to simplify phone setup."""
    certificate_path = Path(__file__).resolve().parents[1] / "data" / "tls" / "local-root-ca.cer"
    if not certificate_path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lokalny certyfikat CA nie jest dostępny.")
    return FileResponse(
        certificate_path,
        media_type="application/pkix-cert",
        filename="pecunianonolet-local-root-ca.cer",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/.well-known/apple-app-site-association", include_in_schema=False)
def apple_app_site_association() -> JSONResponse:
    team_id = os.getenv("APPLE_TEAM_ID", "96UM85TJJ7").strip()
    bundle_id = os.getenv("IOS_BUNDLE_ID", "com.rajda.pecunianonolet").strip()
    if not team_id or not bundle_id or "." in team_id or " " in bundle_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Brakuje APPLE_TEAM_ID lub IOS_BUNDLE_ID.")
    return JSONResponse(
        {"webcredentials": {"apps": [f"{team_id}.{bundle_id}"]}},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/.well-known/assetlinks.json", include_in_schema=False)
def android_asset_links() -> JSONResponse:
    fingerprints = [
        value.strip().upper()
        for value in os.getenv("ANDROID_SHA256_CERT_FINGERPRINTS", "FA:C6:17:45:DC:09:03:78:6F:B9:ED:E6:2A:96:2B:39:9F:73:48:F0:BB:6F:89:9B:83:32:66:75:91:03:3B:9C").split(",")
        if value.strip()
    ]
    if not fingerprints or any(len(value) != 95 or any(c not in "0123456789ABCDEF:" for c in value) for value in fingerprints):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Brakuje poprawnego ANDROID_SHA256_CERT_FINGERPRINTS.")
    return JSONResponse(
        [{
            "relation": ["delegate_permission/common.get_login_creds"],
            "target": {
                "namespace": "android_app",
                "package_name": os.getenv("ANDROID_PACKAGE_NAME", "com.pecunianonolet"),
                "sha256_cert_fingerprints": fingerprints,
            },
        }],
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/register", response_model=AuthResponse, status_code=201)
def register(payload: PublicRegisterRequest, request: Request) -> AuthResponse:
    verify_turnstile_token(
        payload.captcha_token,
        request.client.host if request.client else None,
    )
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
                initialize_user_accounts(db, user_id, int(time.time()))
                token = issue_token(db, user_id)
        except sqlite3.IntegrityError as exc:
            if "users.email" in str(exc):
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "Ten adres e-mail jest już zajęty."
                ) from exc
            raise
    return AuthResponse(user=User(id=user_id, email=payload.email, role="user"), token=token)


@app.post("/api/login", response_model=LoginResponse)
def login(payload: LoginCredentials) -> LoginResponse:
    with closing(connect_db()) as read_db:
        row = read_db.execute(
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
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute(
            "SELECT id, email, password_hash FROM users WHERE id = ?", (row["id"],)
        ).fetchone()
        if current is None or current["password_hash"] != stored_hash:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Błędny e-mail lub hasło.")
        current_role = db.execute(
            "SELECT role_name FROM user_roles WHERE user_id = ?", (row["id"],)
        ).fetchone()
        if current_role is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Błędny e-mail lub hasło.")
        mfa = db.execute(
            "SELECT enabled_at FROM user_totp WHERE user_id = ?", (row["id"],)
        ).fetchone()
        if mfa is not None and mfa["enabled_at"] is not None:
            from app.routes.mfa import create_login_challenge

            challenge = create_login_challenge(db, row["id"])
            return challenge
        token = issue_token(db, row["id"])
    return AuthResponse(
        user=User(id=current["id"], email=current["email"], role=current_role["role_name"]), token=token
    )


@app.post("/api/change-password", response_model=ChangePasswordResponse)
def change_password(
    payload: ChangePasswordRequest,
    session: tuple[str, User] = Depends(current_session),
) -> ChangePasswordResponse:
    session_token, user = session
    with closing(connect_db()) as read_db:
        row = read_db.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user.id,)
        ).fetchone()
    if row is None or not password_hasher.verify(payload.current_password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Obecne hasło jest nieprawidłowe.")
    if password_hasher.verify(payload.new_password, row["password_hash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nowe hasło musi różnić się od obecnego.")
    expected_hash = row["password_hash"]
    new_hash = password_hasher.hash(payload.new_password)
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        active_session = db.execute(
            "SELECT 1 FROM sessions WHERE token_hash = ? AND user_id = ? AND expires_at > ?",
            (token_hash(session_token), user.id, int(time.time())),
        ).fetchone()
        if active_session is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")
        current = db.execute("SELECT password_hash FROM users WHERE id = ?", (user.id,)).fetchone()
        if current is None or current["password_hash"] != expected_hash:
            raise HTTPException(status.HTTP_409_CONFLICT, "Hasło zostało już zmienione. Zaloguj się ponownie.")
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user.id,))
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user.id))
        db.execute("DELETE FROM totp_login_challenges WHERE user_id = ?", (user.id,))
        db.execute("DELETE FROM user_totp WHERE user_id = ? AND enabled_at IS NULL", (user.id,))
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
