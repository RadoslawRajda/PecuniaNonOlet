"""Bounded and cached transport for Google's signing-certificate endpoint."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any

import requests
from google.auth.exceptions import TransportError
from google.auth.transport import Response

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"
GOOGLE_CERTS_TIMEOUT_SECONDS = 5
MAX_CERTIFICATE_CACHE_SECONDS = 6 * 60 * 60
_MAX_AGE_PATTERN = re.compile(r"(?:^|,)\s*max-age=(\d+)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class CachedResponse(Response):
    status: int
    headers: dict[str, str]
    data: bytes


class GoogleCertificateRequest:
    """Fetch only Google's fixed cert URL with a deadline and HTTP cache semantics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cached: tuple[float, CachedResponse] | None = None
        self._session = requests.Session()

    def __call__(self, url: str, method: str = "GET", **kwargs: Any) -> Response:
        if url != GOOGLE_CERTS_URL or method != "GET":
            raise TransportError("Unexpected Google verification request")
        now = time.monotonic()
        with self._lock:
            if self._cached is not None and now < self._cached[0]:
                return self._cached[1]
            self._cached = None
            try:
                response = self._session.request(
                    "GET",
                    GOOGLE_CERTS_URL,
                    timeout=GOOGLE_CERTS_TIMEOUT_SECONDS,
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                raise TransportError("Google certificate service is unavailable") from exc
            result = CachedResponse(
                status=response.status_code,
                headers=dict(response.headers),
                data=response.content,
            )
            if result.status == 200:
                lifetime = _cache_lifetime(result.headers)
                if lifetime:
                    self._cached = (time.monotonic() + lifetime, result)
            return result


def _cache_lifetime(headers: dict[str, str]) -> int:
    """Honor Google's max-age, while bounding stale-key use if the header is absent."""
    cache_control = next(
        (value for key, value in headers.items() if key.lower() == "cache-control"), ""
    )
    if "no-store" in cache_control.lower() or "no-cache" in cache_control.lower():
        return 0
    match = _MAX_AGE_PATTERN.search(cache_control)
    if match is None:
        return 300
    return min(int(match.group(1)), MAX_CERTIFICATE_CACHE_SECONDS)


google_certificate_request = GoogleCertificateRequest()
