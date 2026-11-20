"""Streaming ASGI request-body limits for endpoints that parse untrusted payloads."""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_PROFILE_PHOTO_REQUEST_BYTES = 2 * 1024 * 1024 + 64 * 1024
MAX_WEBAUTHN_REQUEST_BYTES = 32 * 1024
MAX_GOOGLE_AUTH_REQUEST_BYTES = 10 * 1024


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
        return None

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

        total_bytes = 0
        too_large = False

        async def limited_receive() -> Message:
            nonlocal total_bytes, too_large
            if too_large:
                return {"type": "http.disconnect"}
            event = await receive()
            if event["type"] == "http.request":
                total_bytes += len(event.get("body", b""))
                too_large = total_bytes > max_bytes
            return event

        async def tracked_send(event: Message) -> None:
            if not too_large:
                await send(event)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except Exception:
            if not too_large:
                raise
        if too_large:
            await send_too_large()
