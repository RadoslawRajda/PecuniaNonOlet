"""Public finance contracts should expose their required retry and amount semantics."""

from app.main import app


def test_financial_openapi_describes_idempotency_and_quote_contract():
    paths = app.openapi()["paths"]
    for path in ("/api/transfers", "/api/exchange"):
        operation = paths[path]["post"]
        assert "Idempotency-Key" in operation["description"]
        assert any(
            parameter["name"] == "Idempotency-Key" and parameter["required"]
            for parameter in operation["parameters"]
        )

    quote = paths["/api/exchange/quote"]["post"]
    assert "jednorazowe" in quote["description"]
    assert "nie zmienia sald" in quote["description"]

    schemas = app.openapi()["components"]["schemas"]
    assert schemas["TransferRequest"]["examples"][0]["amount_minor"] == 1250
    assert schemas["ExchangeQuoteRequest"]["examples"][0]["source_amount_minor"] == 424
    assert schemas["ExchangeRequest"]["examples"][0]["quote_id"]


def test_session_openapi_describes_rotation_and_google_reauthentication():
    paths = app.openapi()["paths"]
    assert "Ponowne użycie" in paths["/api/refresh"]["post"]["description"]
    assert "refresh token w body" in paths["/api/logout"]["post"]["description"]
    reauth = paths["/api/auth/google/reauth"]["post"]
    assert "nową parę tokenów" in reauth["description"]
    assert "200" in reauth["responses"]
