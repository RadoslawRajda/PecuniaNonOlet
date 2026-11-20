"""Health, local TLS setup and mobile association endpoints."""

from __future__ import annotations

import html
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.config import Settings, load_settings
from app.database import connect_db

router = APIRouter(tags=["diagnostics"])


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def diagnostics(request: Request) -> HTMLResponse:
    settings: Settings = request.app.state.settings or load_settings()
    if settings.app_env == "production":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono strony.")
    ip = settings.lan_ip
    from app.local_tls import ensure_local_tls

    tls_files = ensure_local_tls(
        Path(__file__).resolve().parents[1] / "data" / "tls", ip or "127.0.0.1"
    )
    fingerprint = html.escape(tls_files.ca_fingerprint_sha256)
    return HTMLResponse(
        '<!doctype html><html lang="pl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>PecuniaNonOlet — konfiguracja HTTPS</title></head><body>"
        "<h1>Konfiguracja bezpiecznego połączenia</h1>"
        "<p>Ta strona służy tylko do zainstalowania lokalnego certyfikatu zaufania. "
        "Nie loguj się ani nie wysyłaj tutaj danych konta.</p>"
        "<ol><li>Pobierz publiczny certyfikat CA: "
        '<a href="/local-root-ca.cer" download>Pobierz certyfikat</a>.</li>'
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
        '<a href="https://pecunianonolet.local:8000/">'
        "https://pecunianonolet.local:8000/</a></p>"
        "<p>Domena mDNS: <code>pecunianonolet.local</code><br>"
        'Swagger UI: <a href="https://pecunianonolet.local:8000/docs">'
        "https://pecunianonolet.local:8000/docs</a></p>"
        "<p>API i pozostałe strony są dostępne tylko przez HTTPS.</p>"
        "<p>Nie instaluj certyfikatu, jeśli odcisk nie zgadza się z wartością "
        "pokazaną na komputerze. Lokalny certyfikat jest przeznaczony do "
        "developmentu w zaufanej sieci.</p></body></html>",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/health")
def health() -> dict[str, str]:
    with closing(connect_db()) as db:
        db.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@router.get("/local-root-ca.cer", include_in_schema=False)
def download_local_ca() -> FileResponse:
    """Serve only the public local CA certificate to simplify phone setup."""
    if load_settings().app_env == "production":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono certyfikatu.")
    certificate_path = Path(__file__).resolve().parents[1] / "data" / "tls" / "local-root-ca.cer"
    if not certificate_path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lokalny certyfikat CA nie jest dostępny.")
    return FileResponse(
        certificate_path,
        media_type="application/pkix-cert",
        filename="pecunianonolet-local-root-ca.cer",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/.well-known/apple-app-site-association", include_in_schema=False)
def apple_app_site_association(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings or load_settings()
    team_id = settings.apple_team_id.strip()
    bundle_id = settings.ios_bundle_id.strip()
    if not team_id or not bundle_id or "." in team_id or " " in bundle_id:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Brakuje APPLE_TEAM_ID lub IOS_BUNDLE_ID."
        )
    return JSONResponse(
        {"webcredentials": {"apps": [f"{team_id}.{bundle_id}"]}},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/.well-known/assetlinks.json", include_in_schema=False)
def android_asset_links(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings or load_settings()
    fingerprints = [
        value.strip().upper()
        for value in settings.android_sha256_cert_fingerprints.split(",")
        if value.strip()
    ]
    if not fingerprints or any(
        len(value) != 95 or any(c not in "0123456789ABCDEF:" for c in value)
        for value in fingerprints
    ):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Brakuje poprawnego ANDROID_SHA256_CERT_FINGERPRINTS.",
        )
    return JSONResponse(
        [
            {
                "relation": ["delegate_permission/common.get_login_creds"],
                "target": {
                    "namespace": "android_app",
                    "package_name": settings.android_package_name,
                    "sha256_cert_fingerprints": fingerprints,
                },
            }
        ],
        headers={"Cache-Control": "no-store"},
    )
