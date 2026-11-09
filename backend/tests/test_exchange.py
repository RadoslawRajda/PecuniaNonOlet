import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import exchange
from app.routes.exchange import RateProviderUnavailable, RateTable


class FixedRateProvider:
    def current_rates(self):
        return RateTable(
            "Test NBP Table A",
            date.today().isoformat(),
            {
                "PLN": Decimal(1),
                "EUR": Decimal(4),
                "USD": Decimal(2),
                "GBP": Decimal(5),
                "CZK": Decimal("0.2"),
            },
        )


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "exchange.db"))
    app.dependency_overrides[exchange.get_rate_provider] = FixedRateProvider
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def create_user(client, email):
    return client.post(
        "/api/register", json={"email": email, "password": "test-password"}
    ).json()


def account_ids(client, token):
    return {
        row["currency_code"]: row["id"]
        for row in client.get("/api/accounts", headers=auth(token)).json()["accounts"]
    }


def test_nbp_provider_uses_https_and_parses_decimal_rates(monkeypatch):
    calls = []

    class FakeResponse:
        text = (
            '[{"table":"A","effectiveDate":"2026-11-09","rates":['
            '{"code":"EUR","mid":4.1234},{"code":"USD","mid":3.5},'
            '{"code":"GBP","mid":4.8},{"code":"CZK","mid":0.17}]}]'
        )

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["timeout"].read == 5.0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def get(self, url, headers):
            calls.append((url, headers))
            return FakeResponse()

    monkeypatch.setattr(exchange.httpx, "Client", FakeClient)
    table = exchange.NBPRateProvider().current_rates()
    assert calls[0][0].startswith("https://")
    assert table.pln_per_unit["EUR"] == Decimal("4.1234")
    assert table.pln_per_unit["PLN"] == Decimal(1)


@pytest.mark.parametrize("bad_payload", [
    "[]",
    '[{"table":"B","effectiveDate":"2026-11-09","rates":[]}]',
    '[{"table":"A","effectiveDate":"2026-11-09","rates":[]}]',
    '[{"table":"A","effectiveDate":"2026-11-09","rates":[{"code":"EUR","mid":0}]}]',
])
def test_nbp_provider_rejects_invalid_or_incomplete_table(monkeypatch, bad_payload):
    class FakeResponse:
        text = bad_payload

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(exchange.httpx, "Client", FakeClient)
    with pytest.raises(RateProviderUnavailable):
        exchange.NBPRateProvider().current_rates()


def test_nbp_provider_surfaces_network_timeout_as_unavailable(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["timeout"].read == 5.0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def get(self, *args, **kwargs):
            raise httpx.ReadTimeout("upstream timed out")

    monkeypatch.setattr(exchange.httpx, "Client", FakeClient)
    with pytest.raises(RateProviderUnavailable):
        exchange.NBPRateProvider().current_rates()


def test_rate_endpoint_returns_all_supported_currencies_and_requires_user(client):
    assert client.get("/api/exchange-rates").status_code == 401
    user = create_user(client, "rates@example.com")
    response = client.get("/api/exchange-rates", headers=auth(user["token"]))
    assert response.status_code == 200
    assert response.json() == {
        "provider": "Test NBP Table A",
        "effective_date": date.today().isoformat(),
        "base_currency_code": "PLN",
        "rates": [
            {"currency_code": "PLN", "pln_per_unit": "1"},
            {"currency_code": "EUR", "pln_per_unit": "4"},
            {"currency_code": "USD", "pln_per_unit": "2"},
            {"currency_code": "GBP", "pln_per_unit": "5"},
            {"currency_code": "CZK", "pln_per_unit": "0.2"},
        ],
    }


def test_rate_provider_unavailable_returns_service_unavailable(client):
    class Unavailable:
        def current_rates(self):
            raise RateProviderUnavailable

    app.dependency_overrides[exchange.get_rate_provider] = Unavailable
    user = create_user(client, "unavailable@example.com")
    response = client.get("/api/exchange-rates", headers=auth(user["token"]))
    assert response.status_code == 503
    assert "Kursy walut" in response.json()["detail"]


def test_quote_cross_rates_cover_every_directed_supported_pair(client):
    user = create_user(client, "pairs@example.com")
    ids = account_ids(client, user["token"])
    pln_per_unit = {
        "PLN": Decimal(1), "EUR": Decimal(4), "USD": Decimal(2),
        "GBP": Decimal(5), "CZK": Decimal("0.2"),
    }
    for source in ids:
        for destination in ids:
            if source == destination:
                continue
            response = client.post(
                "/api/exchange/quote",
                headers=auth(user["token"]),
                json={
                    "source_account_id": ids[source],
                    "destination_account_id": ids[destination],
                    "source_amount_minor": 10_000,
                },
            )
            assert response.status_code == 201, response.text
            body = response.json()
            expected_rate = pln_per_unit[source] / pln_per_unit[destination]
            expected_minor = int((Decimal(100) * expected_rate).quantize(Decimal("0.01")) * 100)
            assert body["exchange_rate"] == format(expected_rate, "f")
            assert body["destination_amount_minor"] == expected_minor
            assert body["source_currency_code"] == source
            assert body["destination_currency_code"] == destination


def test_quote_rejects_foreign_accounts_same_currency_and_bad_amount(client):
    first = create_user(client, "quote-first@example.com")
    second = create_user(client, "quote-second@example.com")
    first_ids = account_ids(client, first["token"])
    second_ids = account_ids(client, second["token"])
    headers = auth(first["token"])
    assert client.post(
        "/api/exchange/quote", headers=headers,
        json={"source_account_id": second_ids["PLN"], "destination_account_id": first_ids["EUR"], "source_amount_minor": 100},
    ).status_code == 404
    assert client.post(
        "/api/exchange/quote", headers=headers,
        json={"source_account_id": first_ids["PLN"], "destination_account_id": first_ids["PLN"], "source_amount_minor": 100},
    ).status_code == 422
    for amount in (0, -1, 9_000_000_000_000_001, 1.5):
        assert client.post(
            "/api/exchange/quote", headers=headers,
            json={"source_account_id": first_ids["PLN"], "destination_account_id": first_ids["EUR"], "source_amount_minor": amount},
        ).status_code == 422


def test_quote_and_exchange_are_scoped_to_the_owning_user(client):
    owner = create_user(client, "quote-owner@example.com")
    other = create_user(client, "quote-other@example.com")
    owner_ids = account_ids(client, owner["token"])
    quote = client.post(
        "/api/exchange/quote", headers=auth(owner["token"]),
        json={"source_account_id": owner_ids["PLN"], "destination_account_id": owner_ids["EUR"], "source_amount_minor": 100},
    ).json()
    response = client.post(
        "/api/exchange", headers={**auth(other["token"]), "Idempotency-Key": "steal-quote"},
        json={"quote_id": quote["quote_id"]},
    )
    assert response.status_code == 404
    balances = client.get("/api/accounts", headers=auth(owner["token"])).json()["accounts"]
    assert next(a["balance_minor"] for a in balances if a["currency_code"] == "PLN") == 100_000


def test_exchange_is_atomic_records_rate_and_replays_idempotently(client, tmp_path):
    user = create_user(client, "exchange@example.com")
    ids = account_ids(client, user["token"])
    quote = client.post(
        "/api/exchange/quote", headers=auth(user["token"]),
        json={"source_account_id": ids["PLN"], "destination_account_id": ids["EUR"], "source_amount_minor": 10_000},
    ).json()
    headers = {**auth(user["token"]), "Idempotency-Key": "fx-001"}
    payload = {"quote_id": quote["quote_id"]}
    response = client.post("/api/exchange", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source_amount_minor"] == 10_000
    assert body["destination_amount_minor"] == 2_500
    assert body["exchange_rate"] == "0.25"
    balances = client.get("/api/accounts", headers=auth(user["token"])).json()["accounts"]
    assert next(a["balance_minor"] for a in balances if a["currency_code"] == "PLN") == 90_000
    assert next(a["balance_minor"] for a in balances if a["currency_code"] == "EUR") == 2_500

    replay = client.post("/api/exchange", headers=headers, json=payload)
    assert replay.status_code == 201
    assert replay.json()["transaction_id"] == body["transaction_id"]
    assert replay.json()["idempotent_replay"] is True
    assert client.post(
        "/api/exchange", headers={**auth(user["token"]), "Idempotency-Key": "client-rate"},
        json={"quote_id": quote["quote_id"], "exchange_rate": "999"},
    ).status_code == 422
    assert client.post(
        "/api/exchange", headers=headers, json={"quote_id": "00000000-0000-0000-0000-000000000000"}
    ).status_code == 409
    assert client.post(
        "/api/exchange", headers={**auth(user["token"]), "Idempotency-Key": "fx-002"}, json=payload
    ).status_code == 409

    history = client.get("/api/transactions", headers=auth(user["token"])).json()["transactions"]
    transaction = next(item for item in history if item["id"] == body["transaction_id"])
    assert transaction["type"] == "exchange"
    assert transaction["source_amount_minor"] == 10_000
    assert transaction["destination_amount_minor"] == 2_500
    assert transaction["exchange_rate"] == "0.25"
    with sqlite3.connect(tmp_path / "exchange.db") as db:
        entries = db.execute(
            "SELECT amount_minor FROM ledger_entries WHERE transaction_id = ? ORDER BY amount_minor",
            (body["transaction_id"],),
        ).fetchall()
        assert entries == [(-10_000,), (2_500,)]
        assert db.execute("SELECT id FROM exchange_quotes WHERE consumed_transaction_id = ?", (body["transaction_id"],)).fetchone() == (quote["quote_id"],)
        assert db.execute("SELECT consumed_at FROM exchange_quotes WHERE id = ?", (quote["quote_id"],)).fetchone()[0] is not None
        assert db.execute(
            "SELECT base_currency_code, quote_currency_code, rate, provider FROM exchange_rate_snapshots"
        ).fetchone() == ("PLN", "EUR", "0.25", "Test NBP Table A")


def test_exchange_rounding_floors_positive_payouts(client):
    assert exchange.amount_in_minor_units(3, Decimal("0.5"), Decimal(1)) == 1
    user = create_user(client, "rounding@example.com")
    ids = account_ids(client, user["token"])
    quote = client.post(
        "/api/exchange/quote", headers=auth(user["token"]),
        json={"source_account_id": ids["CZK"], "destination_account_id": ids["PLN"], "source_amount_minor": 25},
    )
    assert quote.status_code == 201
    assert quote.json()["destination_amount_minor"] == 5


@pytest.mark.parametrize(("eur_rate", "pln_source_minor"), [("4.24", 424), ("3.00", 300)])
def test_exact_cross_rate_conversion_preserves_whole_eurocents(client, eur_rate, pln_source_minor):
    class ExactRateProvider:
        def current_rates(self):
            return RateTable(
                "Exact arithmetic test rates",
                date.today().isoformat(),
                {
                    "PLN": Decimal(1),
                    "EUR": Decimal(eur_rate),
                    "USD": Decimal("3.70"),
                    "GBP": Decimal("5.10"),
                    "CZK": Decimal("0.16"),
                },
            )

    app.dependency_overrides[exchange.get_rate_provider] = ExactRateProvider
    user = create_user(client, f"exact-{eur_rate.replace('.', '-')}@example.com")
    ids = account_ids(client, user["token"])
    quote = client.post(
        "/api/exchange/quote",
        headers=auth(user["token"]),
        json={
            "source_account_id": ids["PLN"],
            "destination_account_id": ids["EUR"],
            "source_amount_minor": pln_source_minor,
        },
    )
    assert quote.status_code == 201, quote.text
    assert quote.json()["destination_amount_minor"] == 100

    exchange_response = client.post(
        "/api/exchange",
        headers={**auth(user["token"]), "Idempotency-Key": f"exact-{eur_rate}"},
        json={"quote_id": quote.json()["quote_id"]},
    )
    assert exchange_response.status_code == 201
    assert exchange_response.json()["destination_amount_minor"] == 100
    balances = client.get("/api/accounts", headers=auth(user["token"])).json()["accounts"]
    assert next(item["balance_minor"] for item in balances if item["currency_code"] == "EUR") == 100


def test_exchange_quotes_match_exact_fraction_results_for_supported_currency_pairs(client):
    rates = {
        "PLN": Decimal(1),
        "EUR": Decimal("4.24"),
        "USD": Decimal("3.70"),
        "GBP": Decimal("5.10"),
        "CZK": Decimal("0.16"),
    }

    class ExactRateProvider:
        def current_rates(self):
            return RateTable("Exact arithmetic test rates", date.today().isoformat(), rates)

    app.dependency_overrides[exchange.get_rate_provider] = ExactRateProvider
    user = create_user(client, "fraction-pairs@example.com")
    ids = account_ids(client, user["token"])
    for source_code, source_id in ids.items():
        for destination_code, destination_id in ids.items():
            if source_code == destination_code:
                continue
            for source_minor in (1, 3, 25, 100, 300, 424, 10_001):
                exact_minor = (
                    Fraction(source_minor)
                    * Fraction(rates[source_code])
                    / Fraction(rates[destination_code])
                )
                expected = exact_minor.numerator // exact_minor.denominator
                response = client.post(
                    "/api/exchange/quote",
                    headers=auth(user["token"]),
                    json={
                        "source_account_id": source_id,
                        "destination_account_id": destination_id,
                        "source_amount_minor": source_minor,
                    },
                )
                if expected < 1:
                    assert response.status_code == 422
                else:
                    assert response.status_code == 201, response.text
                    assert response.json()["destination_amount_minor"] == expected


@pytest.mark.parametrize(
    ("effective_date", "expected_status"),
    [
        (date.today().isoformat(), 200),
        ((date.today() - timedelta(days=7)).isoformat(), 200),
        ((date.today() - timedelta(days=8)).isoformat(), 503),
        ((date.today() + timedelta(days=1)).isoformat(), 503),
        ("2000-01-01", 503),
        ("not-a-date", 503),
    ],
)
def test_rate_table_freshness_policy(client, effective_date, expected_status):
    class DatedRateProvider:
        def current_rates(self):
            return RateTable(
                "Dated test rates",
                effective_date,
                {
                    "PLN": Decimal(1),
                    "EUR": Decimal(4),
                    "USD": Decimal(2),
                    "GBP": Decimal(5),
                    "CZK": Decimal("0.2"),
                },
            )

    app.dependency_overrides[exchange.get_rate_provider] = DatedRateProvider
    user = create_user(client, f"freshness-{expected_status}-{effective_date}@example.com")
    response = client.get("/api/exchange-rates", headers=auth(user["token"]))
    assert response.status_code == expected_status


def test_two_way_exchange_cycles_never_increase_source_balance(client, tmp_path):
    user = create_user(client, "round-trip@example.com")
    ids = account_ids(client, user["token"])
    amounts = (1, 2, 3, 4, 5, 9, 10, 25, 100, 101, 1_000)

    for source_code, source_id in ids.items():
        for destination_code, destination_id in ids.items():
            if source_code == destination_code:
                continue
            for amount in amounts:
                with sqlite3.connect(tmp_path / "exchange.db") as db:
                    db.execute("UPDATE accounts SET balance_minor = 0")
                    db.execute(
                        "UPDATE accounts SET balance_minor = ? WHERE id = ?",
                        (amount, source_id),
                    )

                forward = client.post(
                    "/api/exchange/quote",
                    headers=auth(user["token"]),
                    json={
                        "source_account_id": source_id,
                        "destination_account_id": destination_id,
                        "source_amount_minor": amount,
                    },
                )
                if forward.status_code == 422:
                    continue  # A payout below one minor unit is rejected.
                assert forward.status_code == 201, forward.text
                key = f"cycle-{source_code}-{destination_code}-{amount}"
                executed = client.post(
                    "/api/exchange",
                    headers={**auth(user["token"]), "Idempotency-Key": key + "-out"},
                    json={"quote_id": forward.json()["quote_id"]},
                )
                assert executed.status_code == 201, executed.text

                backward = client.post(
                    "/api/exchange/quote",
                    headers=auth(user["token"]),
                    json={
                        "source_account_id": destination_id,
                        "destination_account_id": source_id,
                        "source_amount_minor": executed.json()["destination_amount_minor"],
                    },
                )
                if backward.status_code == 422:
                    continue
                assert backward.status_code == 201, backward.text
                returned = client.post(
                    "/api/exchange",
                    headers={**auth(user["token"]), "Idempotency-Key": key + "-back"},
                    json={"quote_id": backward.json()["quote_id"]},
                )
                assert returned.status_code == 201, returned.text
                with sqlite3.connect(tmp_path / "exchange.db") as db:
                    final_source_balance = db.execute(
                        "SELECT balance_minor FROM accounts WHERE id = ?", (source_id,)
                    ).fetchone()[0]
                assert final_source_balance <= amount, (source_code, destination_code, amount)


def test_opening_balance_idempotency_key_conflicts_cleanly(client):
    user = create_user(client, "opening-replay@example.com")
    response = client.post(
        "/api/exchange",
        headers={**auth(user["token"]), "Idempotency-Key": "opening-balance-pln-v1"},
        json={"quote_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 409


def test_sqlite_overflowing_ids_and_offsets_are_rejected_at_api_boundary(client):
    user = create_user(client, "numeric-boundary@example.com")
    headers = auth(user["token"])
    too_large = 9_223_372_036_854_775_808
    assert client.get(f"/api/transactions?offset={too_large}", headers=headers).status_code == 422
    assert client.post(
        "/api/transfers",
        headers={**headers, "Idempotency-Key": "bad-account-id"},
        json={
            "recipient_email": "someone@example.com",
            "source_account_id": too_large,
            "currency_code": "PLN",
            "amount_minor": 1,
        },
    ).status_code == 422
    assert client.post(
        "/api/exchange/quote",
        headers=headers,
        json={
            "source_account_id": too_large,
            "destination_account_id": 1,
            "source_amount_minor": 1,
        },
    ).status_code == 422


def test_one_quote_cannot_be_executed_concurrently_twice(client):
    user = create_user(client, "concurrent-fx@example.com")
    ids = account_ids(client, user["token"])
    quote = client.post(
        "/api/exchange/quote", headers=auth(user["token"]),
        json={"source_account_id": ids["PLN"], "destination_account_id": ids["EUR"], "source_amount_minor": 1_000},
    ).json()

    def submit(key):
        return client.post(
            "/api/exchange", headers={**auth(user["token"]), "Idempotency-Key": key},
            json={"quote_id": quote["quote_id"]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, ("parallel-a", "parallel-b")))
    assert sorted(response.status_code for response in responses) == [201, 409]
    balances = client.get("/api/accounts", headers=auth(user["token"])).json()["accounts"]
    assert next(a["balance_minor"] for a in balances if a["currency_code"] == "PLN") == 99_000
    assert next(a["balance_minor"] for a in balances if a["currency_code"] == "EUR") == 250


def test_expired_quote_and_insufficient_funds_do_not_change_balances(client, tmp_path):
    user = create_user(client, "expiry@example.com")
    ids = account_ids(client, user["token"])
    token = user["token"]
    quote = client.post(
        "/api/exchange/quote", headers=auth(token),
        json={"source_account_id": ids["PLN"], "destination_account_id": ids["EUR"], "source_amount_minor": 100},
    ).json()
    with sqlite3.connect(tmp_path / "exchange.db") as db:
        db.execute("UPDATE exchange_quotes SET created_at = 0, expires_at = 1 WHERE id = ?", (quote["quote_id"],))
    expired = client.post(
        "/api/exchange", headers={**auth(token), "Idempotency-Key": "expired"},
        json={"quote_id": quote["quote_id"]},
    )
    assert expired.status_code == 409

    no_funds = client.post(
        "/api/exchange/quote", headers=auth(token),
        json={"source_account_id": ids["EUR"], "destination_account_id": ids["PLN"], "source_amount_minor": 100},
    ).json()
    insufficient = client.post(
        "/api/exchange", headers={**auth(token), "Idempotency-Key": "no-funds"},
        json={"quote_id": no_funds["quote_id"]},
    )
    assert insufficient.status_code == 409
    balances = client.get("/api/accounts", headers=auth(token)).json()["accounts"]
    assert next(a["balance_minor"] for a in balances if a["currency_code"] == "PLN") == 100_000
    assert next(a["balance_minor"] for a in balances if a["currency_code"] == "EUR") == 0


def test_exchange_rejects_destination_balance_overflow(client, tmp_path):
    user = create_user(client, "overflow-fx@example.com")
    ids = account_ids(client, user["token"])
    quote = client.post(
        "/api/exchange/quote", headers=auth(user["token"]),
        json={"source_account_id": ids["PLN"], "destination_account_id": ids["EUR"], "source_amount_minor": 1_000},
    ).json()
    with sqlite3.connect(tmp_path / "exchange.db") as db:
        db.execute("UPDATE accounts SET balance_minor = 9000000000000000 WHERE id = ?", (ids["EUR"],))
    response = client.post(
        "/api/exchange", headers={**auth(user["token"]), "Idempotency-Key": "overflow"},
        json={"quote_id": quote["quote_id"]},
    )
    assert response.status_code == 409
    balances = client.get("/api/accounts", headers=auth(user["token"])).json()["accounts"]
    assert next(a["balance_minor"] for a in balances if a["currency_code"] == "PLN") == 100_000
    assert next(a["balance_minor"] for a in balances if a["currency_code"] == "EUR") == 9_000_000_000_000_000


def test_exchange_rolls_back_both_balances_when_ledger_insert_fails(client, tmp_path):
    user = create_user(client, "rollback-fx@example.com")
    ids = account_ids(client, user["token"])
    quote = client.post(
        "/api/exchange/quote", headers=auth(user["token"]),
        json={"source_account_id": ids["PLN"], "destination_account_id": ids["EUR"], "source_amount_minor": 5_000},
    ).json()
    with sqlite3.connect(tmp_path / "exchange.db") as db:
        db.execute(
            "CREATE TRIGGER reject_fx_entry BEFORE INSERT ON ledger_entries "
            "WHEN NEW.amount_minor > 0 BEGIN SELECT RAISE(ABORT, 'reject'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        client.post(
            "/api/exchange", headers={**auth(user["token"]), "Idempotency-Key": "rollback"},
            json={"quote_id": quote["quote_id"]},
        )
    balances = client.get("/api/accounts", headers=auth(user["token"])).json()["accounts"]
    assert next(a["balance_minor"] for a in balances if a["currency_code"] == "PLN") == 100_000
    assert next(a["balance_minor"] for a in balances if a["currency_code"] == "EUR") == 0
    with sqlite3.connect(tmp_path / "exchange.db") as db:
        assert db.execute("SELECT consumed_at FROM exchange_quotes WHERE id = ?", (quote["quote_id"],)).fetchone() == (None,)
        assert db.execute("SELECT count(*) FROM transactions WHERE kind = 'exchange'").fetchone() == (0,)


def test_analyst_cannot_quote_or_exchange(client):
    from app.admin import create_analyst

    analyst_id = create_analyst("analyst-fx@example.com", "analyst-password")
    assert analyst_id > 0
    login = client.post(
        "/api/login", json={"email": "analyst-fx@example.com", "password": "analyst-password"}
    ).json()
    assert client.get("/api/exchange-rates", headers=auth(login["token"])).status_code == 403
    assert client.post(
        "/api/exchange/quote", headers=auth(login["token"]),
        json={"source_account_id": 1, "destination_account_id": 2, "source_amount_minor": 100},
    ).status_code == 403
