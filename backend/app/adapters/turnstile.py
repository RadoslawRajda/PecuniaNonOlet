"""Cloudflare Turnstile verification with a fixed endpoint and bounded timeout."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import Settings, load_settings

logger = logging.getLogger(__name__)
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_TEST_SECRET = "1x0000000000000000000000000000000AA"


def verify_turnstile_token(
    token: str,
    remote_ip: str | None = None,
    *,
    settings: Settings | None = None,
    post: Callable[..., Any] | None = None,
) -> None:
    """Verify the registration token; network failures fail closed as 503."""
    configured = settings or load_settings()
    secret = configured.turnstile_secret_key.get_secret_value().strip()
    if not secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Weryfikacja CAPTCHA jest chwilowo niedostępna.",
        )

    send = httpx.post if post is None else post
    try:
        response = send(
            TURNSTILE_VERIFY_URL,
            data={
                "secret": secret,
                "response": token,
                **({"remoteip": remote_ip} if remote_ip else {}),
            },
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

    expected_hostname = configured.turnstile_expected_hostname.strip().lower()
    hostname = result.get("hostname")
    if expected_hostname and (
        not isinstance(hostname, str) or hostname.lower() != expected_hostname
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Weryfikacja CAPTCHA nie powiodła się.")

    if secret != TURNSTILE_TEST_SECRET and result.get("action") != "register":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Weryfikacja CAPTCHA nie powiodła się.")
