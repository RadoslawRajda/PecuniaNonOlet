import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture(autouse=True)
def test_turnstile_and_registration_helper(monkeypatch):
    """Keep existing API tests offline while supplying the now-required CAPTCHA field."""
    monkeypatch.setattr(main, "verify_turnstile_token", lambda *_args, **_kwargs: None)
    original_post = TestClient.post

    def post_with_test_captcha(client, url, *args, **kwargs):
        body = kwargs.get("json")
        if url == "/api/register" and isinstance(body, dict):
            kwargs["json"] = {**body, "captcha_token": body.get("captcha_token", "test-token")}
        return original_post(client, url, *args, **kwargs)

    monkeypatch.setattr(TestClient, "post", post_with_test_captcha)
