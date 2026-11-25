from uuid import UUID

from app.routes.google_auth import GoogleTokenRequest
from app.schemas import (
    AuthResponse,
    ExchangeRequest,
    LoginCredentials,
    MfaSetupResponse,
    RefreshTokenRequest,
    User,
)


def test_exchange_request_parses_uuid_but_serializes_as_api_string():
    value = "ad0c6189-0876-4103-b0eb-eed99091899a"
    request = ExchangeRequest.model_validate({"quote_id": value})

    assert request.quote_id == UUID(value)
    assert request.model_dump(mode="json") == {"quote_id": value}


def test_credential_values_are_hidden_from_model_representations():
    password = "unique-password-2026"
    token = "r" * 43
    login = LoginCredentials(email="user@example.com", password=password)
    refresh = RefreshTokenRequest(refresh_token=token)
    google = GoogleTokenRequest(id_token="signed-token-opaque-value", nonce="n" * 32)
    setup = MfaSetupResponse(secret="BASE32SECRET", provisioning_uri="otpauth://test", expires_at=1)
    response = AuthResponse(
        user=User(id=1, email="user@example.com", role="user"),
        access_token="a" * 43,
        refresh_token=token,
    )

    for model, secret in (
        (login, password),
        (refresh, token),
        (google, "signed-token-opaque-value"),
        (setup, "BASE32SECRET"),
        (response, token),
    ):
        assert secret not in repr(model)
