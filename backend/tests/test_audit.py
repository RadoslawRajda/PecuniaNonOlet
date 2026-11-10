import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.admin import create_analyst
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "audit.db"))
    with TestClient(app) as test_client:
        yield test_client


def register(client, email):
    return client.post(
        "/api/register", json={"email": email, "password": "strong-password"}
    ).json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def analyst_login(client):
    create_analyst("analyst@example.com", "analyst-password")
    response = client.post(
        "/api/login", json={"email": "analyst@example.com", "password": "analyst-password"}
    )
    return auth(response.json()["token"])


def test_records_opening_financial_and_local_admin_events(client, tmp_path):
    sender = register(client, "sender@example.com")
    register(client, "receiver@example.com")
    headers = analyst_login(client)

    transfer = client.post(
        "/api/transfers",
        headers={**auth(sender["token"]), "Idempotency-Key": "audit-test-transfer"},
        json={
            "recipient_email": "receiver@example.com",
            "source_account_id": 1,
            "currency_code": "PLN",
            "amount_minor": 250,
        },
    )
    assert transfer.status_code == 201
    transaction_id = transfer.json()["transaction_id"]

    page = client.get("/api/analytics/audit-events?limit=100", headers=headers)
    assert page.status_code == 200
    events = page.json()["events"]
    assert page.json()["total"] == 4
    transfer_event = next(event for event in events if event["entity_id"] == transaction_id)
    assert transfer_event["action"] == "financial.transaction_completed"
    assert transfer_event["details"]["source_amount_minor"] == 250
    admin_event = next(event for event in events if event["action"] == "administration.analyst_created")
    assert admin_event["actor_role"] == "local_admin"
    assert admin_event["actor_user_id"] is None
    assert "password" not in json.dumps(events).lower()
    assert "token" not in json.dumps(events).lower()

    filtered = client.get(
        "/api/analytics/audit-events?action=financial.transaction_completed&entity_type=transaction",
        headers=headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 3
    assert client.get("/api/analytics/audit-events?from=10&to=1", headers=headers).status_code == 422

    with sqlite3.connect(tmp_path / "audit.db") as db:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("UPDATE audit_events SET action = 'changed' WHERE entity_id = ?", (transaction_id,))
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM audit_events WHERE entity_id = ?", (transaction_id,))
        db.rollback()


def test_regular_user_cannot_read_audit_events(client):
    user = register(client, "user@example.com")
    assert client.get("/api/analytics/audit-events", headers=auth(user["token"])).status_code == 403
    assert client.get("/api/analytics/audit-events").status_code == 401


def test_audit_failure_rolls_back_transfer_and_balances(client, tmp_path, monkeypatch):
    sender = register(client, "sender@example.com")
    register(client, "receiver@example.com")

    def fail_audit(*args, **kwargs):
        raise sqlite3.IntegrityError("simulated audit write failure")

    monkeypatch.setattr("app.routes.transfers.write_audit_event", fail_audit)
    with pytest.raises(sqlite3.IntegrityError, match="simulated audit write failure"):
        client.post(
            "/api/transfers",
            headers={**auth(sender["token"]), "Idempotency-Key": "rollback-audit-test"},
            json={
                "recipient_email": "receiver@example.com",
                "source_account_id": 1,
                "currency_code": "PLN",
                "amount_minor": 250,
            },
        )

    with sqlite3.connect(tmp_path / "audit.db") as db:
        balances = db.execute("SELECT balance_minor FROM accounts ORDER BY id").fetchall()
        assert balances == [(100_000,), (0,), (0,), (0,), (0,), (100_000,), (0,), (0,), (0,), (0,)]
        assert db.execute("SELECT count(*) FROM transactions WHERE kind = 'transfer'").fetchone()[0] == 0
