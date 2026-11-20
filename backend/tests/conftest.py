import pytest
from app.routes import auth as auth_routes


@pytest.fixture(autouse=True)
def test_turnstile_verification(monkeypatch):
    """Stub only the external Turnstile verification call; requests provide tokens explicitly."""
    monkeypatch.setattr(auth_routes, "verify_turnstile_token", lambda *_args, **_kwargs: None)
