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
