"""Streaming ASGI request-body limits for endpoints that parse untrusted payloads."""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_PROFILE_PHOTO_REQUEST_BYTES = 2 * 1024 * 1024 + 64 * 1024
MAX_WEBAUTHN_REQUEST_BYTES = 32 * 1024
MAX_GOOGLE_AUTH_REQUEST_BYTES = 10 * 1024
MAX_AUTH_REQUEST_BYTES = 16 * 1024
MAX_GENERAL_REQUEST_BYTES = 1024 * 1024


class RequestBodyLimitMiddleware:
    """Reject oversized authentication/image bodies while streaming their ASGI messages."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    def _policy(scope: Scope) -> tuple[int, str] | None:
        if scope.get("type") != "http":
            return None
        method = scope.get("method")
        path = scope.get("path", "")
        if method == "PUT" and path == "/api/profile/photo":
            return MAX_PROFILE_PHOTO_REQUEST_BYTES, "Zdjęcie przekracza dozwolony rozmiar."
        if method == "POST" and path.startswith("/api/passkeys/"):
            return MAX_WEBAUTHN_REQUEST_BYTES, "Żądanie passkey przekracza dozwolony rozmiar."
        if method == "POST" and path.startswith("/api/auth/google/"):
            return MAX_GOOGLE_AUTH_REQUEST_BYTES, "Żądanie logowania Google jest zbyt duże."
        if path in {
            "/api/register",
            "/api/login",
            "/api/login/mfa",
            "/api/refresh",
            "/api/logout",
            "/api/change-password",
        } or path.startswith("/api/mfa/"):
            return MAX_AUTH_REQUEST_BYTES, "Żądanie uwierzytelnienia jest zbyt duże."
        return MAX_GENERAL_REQUEST_BYTES, "Żądanie przekracza dozwolony rozmiar."

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        policy = self._policy(scope)
        if policy is None:
            await self.app(scope, receive, send)
            return

        max_bytes, message = policy

        async def send_too_large() -> None:
            await JSONResponse({"detail": message}, status_code=413)(scope, receive, send)

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > max_bytes:
                    await send_too_large()
                    return
            except ValueError:
                pass

        body = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            if event["type"] != "http.request":
                continue
            chunk = event.get("body", b"")
            if len(chunk) > max_bytes - len(body):
                await send_too_large()
                return
            body.extend(chunk)
            if not event.get("more_body", False):
                break

        delivered = False

        async def buffered_receive() -> Message:
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, buffered_receive, send)
