"""Authentication API for clients on the local network."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import Settings, bind_settings, load_settings, reset_settings
from app.database import migrate_database
from app.request_limits import RequestBodyLimitMiddleware
from app.routes.analytics import router as analytics_router
from app.routes.auth import router as auth_router
from app.routes.diagnostics import router as diagnostics_router
from app.routes.exchange import router as exchange_router
from app.routes.finance import router as finance_router
from app.routes.google_auth import router as google_auth_router
from app.routes.mfa import router as mfa_router
from app.routes.passkeys import router as passkeys_router
from app.routes.profile_photos import router as profile_photos_router
from app.routes.transfers import router as transfers_router

logger = logging.getLogger(__name__)


async def safe_validation_error(request: Request, exc: Exception):
    """Never echo request values (including passwords and bearer-like tokens) in errors."""
    if not isinstance(exc, RequestValidationError):
        raise exc
    errors = [
        {key: value for key, value in error.items() if key not in {"input", "ctx", "url"}}
        for error in exc.errors()
    ]
    logger.info("request_validation_failed path=%s error_count=%s", request.url.path, len(errors))
    return JSONResponse(status_code=422, content={"detail": errors})


async def handle_sqlite_operational_error(request: Request, exc: Exception):
    if not isinstance(exc, sqlite3.OperationalError):
        raise exc
    message = str(exc).lower()
    if "database" in message and ("locked" in message or "busy" in message):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Baza jest chwilowo zajęta. Ponów żądanie."},
            headers={"Retry-After": "1"},
        )
    raise exc


async def prevent_api_response_caching(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        if "no-store" not in response.headers.get("Cache-Control", "").lower():
            response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    return response


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API with explicit runtime configuration and migration lifecycle."""
    configured = settings
    startup_settings = configured or Settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        migrate_database(configured)
        yield

    is_production = startup_settings.app_env == "production"
    application = FastAPI(
        title="PecuniaNonOlet API",
        lifespan=lifespan,
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )
    application.state.settings = configured
    if is_production:
        application.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=[
                host.strip() for host in startup_settings.trusted_hosts.split(",") if host.strip()
            ],
        )
    for api_router in (
        auth_router,
        diagnostics_router,
        finance_router,
        transfers_router,
        exchange_router,
        profile_photos_router,
        analytics_router,
        mfa_router,
        google_auth_router,
        passkeys_router,
    ):
        application.include_router(api_router)
    application.add_middleware(RequestBodyLimitMiddleware)
    application.add_exception_handler(RequestValidationError, safe_validation_error)
    application.add_exception_handler(sqlite3.OperationalError, handle_sqlite_operational_error)

    @application.middleware("http")
    async def bind_application_settings(request: Request, call_next):
        effective_settings = request.app.state.settings or load_settings()
        token = bind_settings(effective_settings)
        try:
            return await call_next(request)
        finally:
            reset_settings(token)

    application.middleware("http")(prevent_api_response_caching)
    return application


app = create_app()
