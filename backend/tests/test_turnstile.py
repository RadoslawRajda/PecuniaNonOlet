from __future__ import annotations

from typing import Any

import httpx
import pytest
from app.adapters.turnstile import TURNSTILE_VERIFY_URL, verify_turnstile_token
from app.config import Settings
from fastapi import HTTPException


class ProviderResponse:
    def __init__(self, body: object, *, error: Exception | None = None) -> None:
        self.body = body
        self.error = error

    def raise_for_status(self) -> None:
        if self.error:
            raise self.error

    def json(self) -> object:
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


def configured_settings(**overrides: Any) -> Settings:
    values = {
        "app_env": "test",
        "turnstile_secret_key": "private-key",
        "turnstile_expected_hostname": "app.example.test",
        **overrides,
    }
    return Settings(**values)


def test_turnstile_posts_to_fixed_provider_with_short_timeout_and_remote_ip():
    captured: dict[str, Any] = {}

    def post(url: str, **kwargs: Any) -> ProviderResponse:
        captured.update(url=url, **kwargs)
        return ProviderResponse(
            {"success": True, "hostname": "APP.EXAMPLE.TEST", "action": "register"}
        )

    verify_turnstile_token("captcha-token", "192.0.2.15", settings=configured_settings(), post=post)

    assert captured["url"] == TURNSTILE_VERIFY_URL
    assert captured["timeout"] == 5.0
    assert captured["data"] == {
        "secret": "private-key",
        "response": "captcha-token",
        "remoteip": "192.0.2.15",
    }


def test_turnstile_missing_secret_fails_closed_without_network_call():
    def unexpected_post(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("provider must not be called without configured secret")

    with pytest.raises(HTTPException) as exc_info:
        verify_turnstile_token(
            "token", settings=configured_settings(turnstile_secret_key=""), post=unexpected_post
        )

    assert exc_info.value.status_code == 503


@pytest.mark.parametrize(
    ("provider_body", "expected_status"),
    [
        ({"success": False}, 400),
        ({"success": True, "hostname": "attacker.example", "action": "register"}, 400),
        ({"success": True, "hostname": "app.example.test", "action": "login"}, 400),
        (["unexpected-json-shape"], 400),
        (ValueError("malformed JSON"), 503),
    ],
)
def test_turnstile_rejects_invalid_or_malformed_provider_responses(
    provider_body: object, expected_status: int
):
    with pytest.raises(HTTPException) as exc_info:
        verify_turnstile_token(
            "token",
            settings=configured_settings(),
            post=lambda *_args, **_kwargs: ProviderResponse(provider_body),
        )

    assert exc_info.value.status_code == expected_status


def test_turnstile_timeout_fails_closed():
    def timeout(*_args: Any, **_kwargs: Any) -> None:
        raise httpx.TimeoutException("timed out")

    with pytest.raises(HTTPException) as exc_info:
        verify_turnstile_token("token", settings=configured_settings(), post=timeout)

    assert exc_info.value.status_code == 503
