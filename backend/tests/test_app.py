import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.accounts import initialize_user_accounts
from app.admin import create_analyst
from app.authorization import require_roles
from app.main import app
from app.schemas import User


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LAN_IP", "192.168.1.45")
    with TestClient(app) as test_client:
        yield test_client


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_diagnostics_and_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    page = client.get("/")
    assert page.status_code == 200
    assert "192.168.1.45" in page.text
    assert "_pecunianonolet._tcp.local." in page.text
    assert "SQLite" in page.text
    assert "<style" not in page.text


def test_register_login_logout_and_persistence(client, tmp_path):
    payload = {"email": "TEST@example.com", "password": "test12345"}
    registered = client.post("/api/register", json=payload)
    assert registered.status_code == 201
    body = registered.json()
    assert body["user"]["email"] == "test@example.com"
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 7 * 24 * 60 * 60
    token = body["token"]
    assert client.get("/api/me", headers=auth(token)).json() == body["user"]

    with sqlite3.connect(tmp_path / "test.db") as db:
        user = db.execute("SELECT password_hash FROM users").fetchone()[0]
        saved_token = db.execute("SELECT token_hash FROM sessions").fetchone()[0]
    assert user != payload["password"]
    assert saved_token != token

    assert client.post("/api/register", json=payload).status_code == 409
    assert client.post("/api/login", json={**payload, "password": "wrongpass"}).status_code == 401
    logged_in = client.post("/api/login", json=payload)
    assert logged_in.status_code == 200
    other_token = logged_in.json()["token"]
    assert other_token != token

    assert client.post("/api/logout", headers=auth(token)).status_code == 204
    assert client.get("/api/me", headers=auth(token)).status_code == 401
    assert client.get("/api/me", headers=auth(other_token)).status_code == 200


def test_missing_expired_and_invalid_token(client, tmp_path):
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/logout").status_code == 401
    assert client.get("/api/me", headers=auth("invalid")).status_code == 401

    token = client.post(
        "/api/register", json={"email": "user@example.com", "password": "test12345"}
    ).json()["token"]
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.execute("UPDATE sessions SET expires_at = 1")
    assert client.get("/api/me", headers=auth(token)).status_code == 401


def test_registration_validation(client):
    for payload in (
        {"email": "not-an-email", "password": "test12345"},
        {"email": "ok@example.com", "password": "short"},
    ):
        assert client.post("/api/register", json=payload).status_code == 422


def test_user_role_is_default_and_cannot_be_selected_by_registration(client, tmp_path):
    registered = client.post(
        "/api/register",
        json={"email": "role@example.com", "password": "test12345", "role": "analyst"},
    )
    assert registered.status_code == 422
    registered = client.post(
        "/api/register", json={"email": "role@example.com", "password": "test12345"}
    )
    assert registered.status_code == 201
    assert registered.json()["user"]["role"] == "user"
    token = registered.json()["token"]
    assert client.get("/api/me", headers=auth(token)).json() == {
        "id": registered.json()["user"]["id"],
        "email": "role@example.com",
        "role": "user",
    }
    with sqlite3.connect(tmp_path / "test.db") as db:
        assert db.execute(
            "SELECT role_name FROM user_roles WHERE user_id = ?",
            (registered.json()["user"]["id"],),
        ).fetchone() == ("user",)


def test_analyst_accounts_are_created_by_trusted_local_process(client, tmp_path):
    analyst_id = create_analyst("analyst@example.com", "analyst-password")
    with sqlite3.connect(tmp_path / "test.db") as db:
        assert db.execute("SELECT role_name FROM user_roles WHERE user_id = ?", (analyst_id,)).fetchone() == ("analyst",)
    logged_in = client.post(
        "/api/login", json={"email": "analyst@example.com", "password": "analyst-password"}
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["role"] == "analyst"
    assert client.get("/api/me", headers=auth(logged_in.json()["token"])).json()["role"] == "analyst"


def test_role_dependency_denies_users_from_analyst_operations():
    user = User(id=1, email="user@example.com", role="user")
    analyst = User(id=2, email="analyst@example.com", role="analyst")
    assert require_roles("user")(("token", user)) == user
    with pytest.raises(HTTPException) as error:
        require_roles("analyst")(("token", user))
    assert getattr(error.value, "status_code", None) == 403
    assert require_roles("analyst")(("token", analyst)) == analyst


def test_analyst_creation_rejects_invalid_password_and_duplicate_email(client):
    with pytest.raises(ValueError):
        create_analyst("weak@example.com", "short")
    create_analyst("existing@example.com", "password-123")
    with pytest.raises(ValueError, match="już istnieje"):
        create_analyst("existing@example.com", "password-123")


def test_change_password_revokes_all_sessions_and_requires_reauthentication(client):
    payload = {"email": "password@example.com", "password": "old-password"}
    first = client.post("/api/register", json=payload).json()
    second = client.post("/api/login", json=payload).json()
    other = client.post(
        "/api/register", json={"email": "other@example.com", "password": "other-password"}
    ).json()

    response = client.post(
        "/api/change-password",
        headers=auth(first["token"]),
        json={"current_password": "old-password", "new_password": "new-password"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "message": "Hasło zostało zmienione. Zaloguj się ponownie.",
        "reauthentication_required": True,
    }
    assert client.get("/api/me", headers=auth(first["token"])).status_code == 401
    assert client.get("/api/me", headers=auth(second["token"])).status_code == 401
    assert client.get("/api/me", headers=auth(other["token"])).status_code == 200
    assert client.post("/api/login", json=payload).status_code == 401
    new_login = client.post(
        "/api/login", json={"email": "password@example.com", "password": "new-password"}
    )
    assert new_login.status_code == 200


def test_change_password_requires_session_and_current_password(client):
    assert client.post(
        "/api/change-password",
        json={"current_password": "old-password", "new_password": "new-password"},
    ).status_code == 401
    credentials = {"email": "wrong-current@example.com", "password": "old-password"}
    token = client.post("/api/register", json=credentials).json()["token"]
    response = client.post(
        "/api/change-password",
        headers=auth(token),
        json={"current_password": "wrong-password", "new_password": "new-password"},
    )
    assert response.status_code == 401
    assert client.get("/api/me", headers=auth(token)).status_code == 200
    assert client.post("/api/login", json=credentials).status_code == 200


def test_change_password_validates_new_password_and_rejects_reuse(client):
    credentials = {"email": "validation@example.com", "password": "old-password"}
    token = client.post("/api/register", json=credentials).json()["token"]
    headers = auth(token)
    for password in ("short", "x" * 129):
        response = client.post(
            "/api/change-password",
            headers=headers,
            json={"current_password": "old-password", "new_password": password},
        )
        assert response.status_code == 422
    same_password = client.post(
        "/api/change-password",
        headers=headers,
        json={"current_password": "old-password", "new_password": "old-password"},
    )
    assert same_password.status_code == 400
    assert client.get("/api/me", headers=headers).status_code == 200


def test_change_password_rolls_back_session_revocation_if_password_update_fails(client, tmp_path):
    credentials = {"email": "atomic@example.com", "password": "old-password"}
    token = client.post("/api/register", json=credentials).json()["token"]
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.execute(
            """
            CREATE TRIGGER reject_password_update BEFORE UPDATE OF password_hash ON users
            BEGIN SELECT RAISE(ABORT, 'update rejected'); END
            """
        )
    with pytest.raises(sqlite3.IntegrityError):
        client.post(
            "/api/change-password",
            headers=auth(token),
            json={"current_password": "old-password", "new_password": "new-password"},
        )
    assert client.get("/api/me", headers=auth(token)).status_code == 200
    assert client.post("/api/login", json=credentials).status_code == 200


def test_registration_creates_independent_currency_accounts_and_initial_ledger(client, tmp_path):
    response = client.post(
        "/api/register", json={"email": "accounts@example.com", "password": "test12345"}
    )
    assert response.status_code == 201
    user_id = response.json()["user"]["id"]
    with sqlite3.connect(tmp_path / "test.db") as db:
        balances = dict(
            db.execute(
                "SELECT currency_code, balance_minor FROM accounts WHERE user_id = ?", (user_id,)
            ).fetchall()
        )
        assert balances == {"PLN": 100_000, "EUR": 0, "USD": 0, "GBP": 0, "CZK": 0}
        assert db.execute(
            "SELECT kind, destination_amount_minor, destination_currency_code FROM transactions WHERE sender_user_id = ?",
            (user_id,),
        ).fetchall() == [("opening", 100_000, "PLN")]
        assert db.execute(
            "SELECT amount_minor FROM ledger_entries WHERE transaction_id IN (SELECT id FROM transactions WHERE sender_user_id = ?)",
            (user_id,),
        ).fetchall() == [(100_000,)]


def test_initial_account_provisioning_is_idempotent(client, tmp_path):
    response = client.post(
        "/api/register", json={"email": "idempotent@example.com", "password": "test12345"}
    )
    user_id = response.json()["user"]["id"]
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.row_factory = sqlite3.Row
        db.execute(
            "UPDATE accounts SET balance_minor = 250 WHERE user_id = ? AND currency_code = 'EUR'",
            (user_id,),
        )
        initialize_user_accounts(db, user_id, 123)
        balances = db.execute(
            "SELECT currency_code, balance_minor FROM accounts WHERE user_id = ? ORDER BY currency_code",
            (user_id,),
        ).fetchall()
        assert {row["currency_code"]: row["balance_minor"] for row in balances} == {
            "CZK": 0, "EUR": 250, "GBP": 0, "PLN": 100_000, "USD": 0
        }
        assert db.execute(
            "SELECT count(*) FROM transactions WHERE sender_user_id = ? AND idempotency_key = ?",
            (user_id, "opening-balance-pln-v1"),
        ).fetchone()[0] == 1


def test_registration_rolls_back_user_accounts_and_grant_on_ledger_failure(client, tmp_path):
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.execute(
            """
            CREATE TRIGGER reject_opening_entry BEFORE INSERT ON ledger_entries
            BEGIN SELECT RAISE(ABORT, 'entry rejected'); END
            """
        )
    with pytest.raises(sqlite3.IntegrityError):
        client.post(
            "/api/register", json={"email": "rollback@example.com", "password": "test12345"}
        )
    with sqlite3.connect(tmp_path / "test.db") as db:
        assert db.execute("SELECT count(*) FROM users WHERE email = 'rollback@example.com'").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM accounts").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM transactions").fetchone() == (0,)


def add_financial_transaction(
    db, *, transaction_id, sender_id, recipient_id, source_account, source_owner,
    destination_account, destination_owner, kind, source_currency, destination_currency,
    source_minor, destination_minor, exchange_rate, idempotency_key, created_at,
):
    db.execute(
        """
        INSERT INTO transactions(
            id, kind, status, sender_user_id, recipient_user_id,
            source_account_id, source_account_user_id,
            destination_account_id, destination_account_user_id,
            source_currency_code, destination_currency_code,
            source_amount_minor, destination_amount_minor, exchange_rate,
            idempotency_key, created_at
        ) VALUES (?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transaction_id, kind, sender_id, recipient_id, source_account, source_owner,
            destination_account, destination_owner, source_currency, destination_currency,
            source_minor, destination_minor, exchange_rate, idempotency_key, created_at,
        ),
    )
    if source_account is not None:
        db.execute(
            "INSERT INTO ledger_entries(transaction_id, account_id, account_user_id, amount_minor, created_at) VALUES (?, ?, ?, ?, ?)",
            (transaction_id, source_account, source_owner, -source_minor, created_at),
        )
    db.execute(
        "INSERT INTO ledger_entries(transaction_id, account_id, account_user_id, amount_minor, created_at) VALUES (?, ?, ?, ?, ?)",
        (transaction_id, destination_account, destination_owner, destination_minor, created_at),
    )


def test_accounts_endpoint_returns_each_currency_for_the_authenticated_owner(client):
    first = client.post(
        "/api/register", json={"email": "first-account@example.com", "password": "test12345"}
    ).json()
    second = client.post(
        "/api/register", json={"email": "second-account@example.com", "password": "test12345"}
    ).json()
    first_response = client.get("/api/accounts", headers=auth(first["token"]))
    assert first_response.status_code == 200
    accounts = first_response.json()["accounts"]
    assert {row["currency_code"]: row["balance"] for row in accounts} == {
        "PLN": "1000.00", "EUR": "0.00", "USD": "0.00", "GBP": "0.00", "CZK": "0.00"
    }
    assert all(isinstance(row["balance_minor"], int) for row in accounts)
    second_account_ids = {
        row["id"] for row in client.get("/api/accounts", headers=auth(second["token"])).json()["accounts"]
    }
    assert not ({row["id"] for row in accounts} & second_account_ids)
    assert client.get("/api/accounts").status_code == 401
    analyst_id = create_analyst("read-only-analyst@example.com", "analyst-password")
    assert analyst_id > 0
    analyst_login = client.post(
        "/api/login", json={"email": "read-only-analyst@example.com", "password": "analyst-password"}
    ).json()
    assert client.get("/api/accounts", headers=auth(analyst_login["token"])).status_code == 403


def test_transaction_history_is_paginated_sorted_and_shows_both_transfer_sides(client, tmp_path):
    sender = client.post(
        "/api/register", json={"email": "sender@example.com", "password": "test12345"}
    ).json()
    recipient = client.post(
        "/api/register", json={"email": "recipient@example.com", "password": "test12345"}
    ).json()
    sender_id = sender["user"]["id"]
    recipient_id = recipient["user"]["id"]
    with sqlite3.connect(tmp_path / "test.db") as db:
        sender_pln = db.execute(
            "SELECT id FROM accounts WHERE user_id = ? AND currency_code = 'PLN'", (sender_id,)
        ).fetchone()[0]
        recipient_pln = db.execute(
            "SELECT id FROM accounts WHERE user_id = ? AND currency_code = 'PLN'", (recipient_id,)
        ).fetchone()[0]
        sender_eur = db.execute(
            "SELECT id FROM accounts WHERE user_id = ? AND currency_code = 'EUR'", (sender_id,)
        ).fetchone()[0]
        created_at = 2_000_000_000
        add_financial_transaction(
            db, transaction_id="transfer-a", sender_id=sender_id, recipient_id=recipient_id,
            source_account=sender_pln, source_owner=sender_id, destination_account=recipient_pln,
            destination_owner=recipient_id, kind="transfer", source_currency="PLN",
            destination_currency="PLN", source_minor=1_000, destination_minor=1_000,
            exchange_rate=None, idempotency_key="transfer-a", created_at=created_at,
        )
        add_financial_transaction(
            db, transaction_id="transfer-z", sender_id=sender_id, recipient_id=recipient_id,
            source_account=sender_pln, source_owner=sender_id, destination_account=recipient_pln,
            destination_owner=recipient_id, kind="transfer", source_currency="PLN",
            destination_currency="PLN", source_minor=500, destination_minor=500,
            exchange_rate=None, idempotency_key="transfer-z", created_at=created_at,
        )
        add_financial_transaction(
            db, transaction_id="exchange-1", sender_id=sender_id, recipient_id=None,
            source_account=sender_pln, source_owner=sender_id, destination_account=sender_eur,
            destination_owner=sender_id, kind="exchange", source_currency="PLN",
            destination_currency="EUR", source_minor=2_500, destination_minor=610,
            exchange_rate="0.2440000000000000001", idempotency_key="exchange-1",
            created_at=created_at + 1,
        )

    first_page = client.get(
        "/api/transactions?limit=2&offset=0", headers=auth(sender["token"])
    ).json()
    assert first_page["total"] == 4
    assert [item["id"] for item in first_page["transactions"]] == ["exchange-1", "transfer-z"]
    exchange = first_page["transactions"][0]
    assert exchange["direction"] == "internal"
    assert exchange["currency_code"] == "PLN"
    assert exchange["amount"] == "25.00"
    assert exchange["source_amount"] == "25.00"
    assert exchange["destination_amount"] == "6.10"
    assert exchange["exchange_rate"] == "0.2440000000000000001"
    transfer = first_page["transactions"][1]
    assert transfer["direction"] == "outgoing"
    assert transfer["amount"] == "5.00"
    assert transfer["counterparty_email"] == "recipient@example.com"
    assert transfer["source_account_id"] == sender_pln
    assert transfer["destination_account_id"] == recipient_pln
    assert transfer["created_at"].endswith("Z")

    second_page = client.get(
        "/api/transactions?limit=2&offset=2", headers=auth(sender["token"])
    ).json()
    assert second_page["transactions"][0]["id"] == "transfer-a"
    assert second_page["transactions"][1]["type"] == "opening"
    incoming = client.get(
        "/api/transactions", headers=auth(recipient["token"])
    ).json()
    transfer_records = [item for item in incoming["transactions"] if item["type"] == "transfer"]
    assert len(transfer_records) == 2
    assert all(item["direction"] == "incoming" for item in transfer_records)
    assert all(item["counterparty_email"] == "sender@example.com" for item in transfer_records)
    assert client.get(
        f"/api/transactions/{incoming['transactions'][-1]['id']}", headers=auth(sender["token"])
    ).status_code == 404


def test_transaction_details_are_owner_scoped_and_pagination_is_validated(client, tmp_path):
    sender = client.post(
        "/api/register", json={"email": "detail-sender@example.com", "password": "test12345"}
    ).json()
    recipient = client.post(
        "/api/register", json={"email": "detail-recipient@example.com", "password": "test12345"}
    ).json()
    sender_id, recipient_id = sender["user"]["id"], recipient["user"]["id"]
    with sqlite3.connect(tmp_path / "test.db") as db:
        sender_account = db.execute(
            "SELECT id FROM accounts WHERE user_id = ? AND currency_code = 'EUR'", (sender_id,)
        ).fetchone()[0]
        recipient_account = db.execute(
            "SELECT id FROM accounts WHERE user_id = ? AND currency_code = 'EUR'", (recipient_id,)
        ).fetchone()[0]
        add_financial_transaction(
            db, transaction_id="visible-transfer", sender_id=sender_id,
            recipient_id=recipient_id, source_account=sender_account, source_owner=sender_id,
            destination_account=recipient_account, destination_owner=recipient_id,
            kind="transfer", source_currency="EUR", destination_currency="EUR",
            source_minor=2_000, destination_minor=2_000, exchange_rate=None,
            idempotency_key="visible-transfer", created_at=123,
        )
    detail = client.get(
        "/api/transactions/visible-transfer", headers=auth(recipient["token"])
    )
    assert detail.status_code == 200
    assert detail.json()["direction"] == "incoming"
    assert detail.json()["amount"] == "20.00"
    assert client.get(
        "/api/transactions/visible-transfer", headers=auth(sender["token"])
    ).status_code == 200
    assert client.get(
        f"/api/transactions/{sender['user']['id']}", headers=auth(recipient["token"])
    ).status_code == 404
    assert client.get("/api/transactions", headers=auth(sender["token"]), params={"limit": 101}).status_code == 422
    assert client.get("/api/transactions?offset=-1", headers=auth(sender["token"])).status_code == 422


def test_transfer_moves_same_currency_atomically_and_replays_idempotently(client, tmp_path):
    sender = client.post(
        "/api/register", json={"email": "transfer-sender@example.com", "password": "test12345"}
    ).json()
    recipient = client.post(
        "/api/register", json={"email": "transfer-recipient@example.com", "password": "test12345"}
    ).json()
    source_id = next(
        account["id"]
        for account in client.get("/api/accounts", headers=auth(sender["token"])).json()["accounts"]
        if account["currency_code"] == "PLN"
    )
    payload = {
        "recipient_email": "TRANSFER-RECIPIENT@example.com",
        "source_account_id": source_id,
        "currency_code": "PLN",
        "amount_minor": 2_000,
    }
    headers = {**auth(sender["token"]), "Idempotency-Key": "transfer-request-001"}
    response = client.post("/api/transfers", headers=headers, json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["amount"] == "20.00"
    assert body["amount_minor"] == 2_000
    assert body["recipient_email"] == "transfer-recipient@example.com"
    assert body["idempotent_replay"] is False

    sender_accounts = client.get("/api/accounts", headers=auth(sender["token"])).json()["accounts"]
    recipient_accounts = client.get("/api/accounts", headers=auth(recipient["token"])).json()["accounts"]
    assert next(a["balance_minor"] for a in sender_accounts if a["currency_code"] == "PLN") == 98_000
    assert next(a["balance_minor"] for a in recipient_accounts if a["currency_code"] == "PLN") == 102_000

    replay = client.post("/api/transfers", headers=headers, json=payload)
    assert replay.status_code == 201
    assert replay.json()["transaction_id"] == body["transaction_id"]
    assert replay.json()["idempotent_replay"] is True
    changed_request = client.post(
        "/api/transfers", headers=headers, json={**payload, "amount_minor": 2_001}
    )
    assert changed_request.status_code == 409
    with sqlite3.connect(tmp_path / "test.db") as db:
        assert db.execute(
            "SELECT count(*) FROM ledger_entries WHERE transaction_id = ?",
            (body["transaction_id"],),
        ).fetchone() == (2,)
        entries = db.execute(
            "SELECT amount_minor FROM ledger_entries WHERE transaction_id = ? ORDER BY amount_minor",
            (body["transaction_id"],),
        ).fetchall()
        assert entries == [(-2_000,), (2_000,)]
        assert sum(row[0] for row in entries) == 0

    sender_history = client.get("/api/transactions", headers=auth(sender["token"])).json()
    recipient_history = client.get("/api/transactions", headers=auth(recipient["token"])).json()
    sent = next(item for item in sender_history["transactions"] if item["id"] == body["transaction_id"])
    received = next(item for item in recipient_history["transactions"] if item["id"] == body["transaction_id"])
    assert sent["direction"] == "outgoing"
    assert received["direction"] == "incoming"


def test_transfer_rejects_invalid_targets_currency_and_insufficient_funds(client):
    sender = client.post(
        "/api/register", json={"email": "validation-sender@example.com", "password": "test12345"}
    ).json()
    recipient = client.post(
        "/api/register", json={"email": "validation-recipient@example.com", "password": "test12345"}
    ).json()
    sender_accounts = client.get("/api/accounts", headers=auth(sender["token"])).json()["accounts"]
    recipient_accounts = client.get("/api/accounts", headers=auth(recipient["token"])).json()["accounts"]
    pln_id = next(a["id"] for a in sender_accounts if a["currency_code"] == "PLN")
    eur_id = next(a["id"] for a in sender_accounts if a["currency_code"] == "EUR")
    recipient_pln_id = next(a["id"] for a in recipient_accounts if a["currency_code"] == "PLN")
    headers = auth(sender["token"])
    valid = {
        "recipient_email": "validation-recipient@example.com",
        "source_account_id": pln_id,
        "currency_code": "PLN",
        "amount_minor": 100,
    }
    assert client.post("/api/transfers", headers=headers, json=valid).status_code == 422
    assert client.post(
        "/api/transfers", headers={**headers, "Idempotency-Key": "self"},
        json={**valid, "recipient_email": "validation-sender@example.com"},
    ).status_code == 400
    assert client.post(
        "/api/transfers", headers={**headers, "Idempotency-Key": "missing"},
        json={**valid, "recipient_email": "nobody@example.com"},
    ).status_code == 404
    assert client.post(
        "/api/transfers", headers={**headers, "Idempotency-Key": "foreign-account"},
        json={**valid, "source_account_id": recipient_pln_id},
    ).status_code == 404
    assert client.post(
        "/api/transfers", headers={**headers, "Idempotency-Key": "currency-mismatch"},
        json={**valid, "currency_code": "EUR"},
    ).status_code == 422
    assert client.post(
        "/api/transfers", headers={**headers, "Idempotency-Key": "invalid-currency"},
        json={**valid, "currency_code": "CAD"},
    ).status_code == 422
    assert client.post(
        "/api/transfers", headers={**headers, "Idempotency-Key": "negative"},
        json={**valid, "amount_minor": -1},
    ).status_code == 422
    no_eur_fallback = client.post(
        "/api/transfers", headers={**headers, "Idempotency-Key": "no-fallback"},
        json={**valid, "source_account_id": eur_id, "currency_code": "EUR", "amount_minor": 1},
    )
    assert no_eur_fallback.status_code == 409
    after = client.get("/api/accounts", headers=headers).json()["accounts"]
    assert next(a["balance_minor"] for a in after if a["currency_code"] == "PLN") == 100_000
    analyst_id = create_analyst("transfer-analyst@example.com", "analyst-password")
    assert analyst_id > 0
    analyst = client.post(
        "/api/login", json={"email": "transfer-analyst@example.com", "password": "analyst-password"}
    ).json()
    assert client.post(
        "/api/transfers", headers={**auth(analyst["token"]), "Idempotency-Key": "analyst"},
        json=valid,
    ).status_code == 403


def test_transfer_rejects_recipient_balance_overflow(client, tmp_path):
    sender = client.post(
        "/api/register", json={"email": "overflow-sender@example.com", "password": "test12345"}
    ).json()
    recipient = client.post(
        "/api/register", json={"email": "overflow-recipient@example.com", "password": "test12345"}
    ).json()
    source_id = next(
        a["id"] for a in client.get("/api/accounts", headers=auth(sender["token"])).json()["accounts"]
        if a["currency_code"] == "PLN"
    )
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.execute(
            "UPDATE accounts SET balance_minor = 9000000000000000 WHERE user_id = ? AND currency_code = 'PLN'",
            (recipient["user"]["id"],),
        )
    response = client.post(
        "/api/transfers",
        headers={**auth(sender["token"]), "Idempotency-Key": "overflow"},
        json={
            "recipient_email": recipient["user"]["email"],
            "source_account_id": source_id,
            "currency_code": "PLN",
            "amount_minor": 1,
        },
    )
    assert response.status_code == 409
    sender_after = client.get("/api/accounts", headers=auth(sender["token"])).json()["accounts"]
    assert next(a["balance_minor"] for a in sender_after if a["currency_code"] == "PLN") == 100_000


def test_concurrent_transfers_cannot_overdraw_source_account(client):
    sender = client.post(
        "/api/register", json={"email": "race-sender@example.com", "password": "test12345"}
    ).json()
    recipients = [
        client.post(
            "/api/register", json={"email": f"race-{index}@example.com", "password": "test12345"}
        ).json()
        for index in range(2)
    ]
    pln_id = next(
        a["id"] for a in client.get("/api/accounts", headers=auth(sender["token"])).json()["accounts"]
        if a["currency_code"] == "PLN"
    )

    def send(index):
        return client.post(
            "/api/transfers",
            headers={**auth(sender["token"]), "Idempotency-Key": f"race-{index}"},
            json={
                "recipient_email": recipients[index]["user"]["email"],
                "source_account_id": pln_id,
                "currency_code": "PLN",
                "amount_minor": 70_000,
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(send, range(2)))
    assert sorted(response.status_code for response in results) == [201, 409]
    sender_accounts = client.get("/api/accounts", headers=auth(sender["token"])).json()["accounts"]
    assert next(a["balance_minor"] for a in sender_accounts if a["currency_code"] == "PLN") == 30_000
    received_totals = [
        next(
            a["balance_minor"]
            for a in client.get("/api/accounts", headers=auth(recipient["token"])).json()["accounts"]
            if a["currency_code"] == "PLN"
        )
        - 100_000
        for recipient in recipients
    ]
    assert sorted(received_totals) == [0, 70_000]


def test_transfer_failure_after_balance_updates_rolls_back_everything(client, tmp_path):
    sender = client.post(
        "/api/register", json={"email": "rollback-sender@example.com", "password": "test12345"}
    ).json()
    recipient = client.post(
        "/api/register", json={"email": "rollback-recipient@example.com", "password": "test12345"}
    ).json()
    pln_id = next(
        a["id"] for a in client.get("/api/accounts", headers=auth(sender["token"])).json()["accounts"]
        if a["currency_code"] == "PLN"
    )
    with sqlite3.connect(tmp_path / "test.db") as db:
        db.execute(
            """
            CREATE TRIGGER reject_transfer_debit BEFORE INSERT ON ledger_entries
            WHEN NEW.amount_minor < 0
            BEGIN SELECT RAISE(ABORT, 'debit rejected'); END
            """
        )
    with pytest.raises(sqlite3.IntegrityError):
        client.post(
            "/api/transfers", headers={**auth(sender["token"]), "Idempotency-Key": "rollback"},
            json={
                "recipient_email": recipient["user"]["email"],
                "source_account_id": pln_id,
                "currency_code": "PLN",
                "amount_minor": 1_000,
            },
        )
    sender_after = client.get("/api/accounts", headers=auth(sender["token"])).json()["accounts"]
    recipient_after = client.get("/api/accounts", headers=auth(recipient["token"])).json()["accounts"]
    assert next(a["balance_minor"] for a in sender_after if a["currency_code"] == "PLN") == 100_000
    assert next(a["balance_minor"] for a in recipient_after if a["currency_code"] == "PLN") == 100_000
    assert client.get("/api/transactions", headers=auth(sender["token"])).json()["total"] == 1
