import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.admin import create_analyst
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "analytics.db"))
    with TestClient(app) as test_client:
        yield test_client


def register(client, email):
    return client.post(
        "/api/register", json={"email": email, "password": "strong-password"}
    ).json()


def authorization(token):
    return {"Authorization": f"Bearer {token}"}


def test_analytics_requires_analyst_role(client):
    user = register(client, "user@example.com")
    for endpoint in ("overview", "users", "transactions"):
        response = client.get(
            f"/api/analytics/{endpoint}", headers=authorization(user["token"])
        )
        assert response.status_code == 403
    assert client.get("/api/analytics/overview").status_code == 401


def test_analyst_can_read_aggregates_and_paginated_users_without_secrets(client, tmp_path):
    analyst_id = create_analyst("analyst@example.com", "analyst-password")
    analyst = client.post(
        "/api/login", json={"email": "analyst@example.com", "password": "analyst-password"}
    ).json()
    register(client, "customer@example.com")
    headers = authorization(analyst["token"])

    overview = client.get("/api/analytics/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["users_total"] == 2
    assert overview.json()["transactions_total"] == 1
    assert overview.json()["transactions_by_kind"] == {"opening": 1}
    assert overview.json()["active_sessions"] == 2

    page = client.get("/api/analytics/users?role=user&limit=1", headers=headers)
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["users"][0]["email"] == "customer@example.com"
    assert page.json()["users"][0]["accounts_count"] == 5
    serialized = page.text.lower()
    assert "password_hash" not in serialized
    assert "token" not in serialized
    with sqlite3.connect(tmp_path / "analytics.db") as db:
        assert db.execute("SELECT count(*) FROM sessions WHERE user_id = ?", (analyst_id,)).fetchone()[0] == 1


def test_analyst_transaction_listing_supports_bound_filters(client):
    create_analyst("analyst@example.com", "analyst-password")
    analyst = client.post(
        "/api/login", json={"email": "analyst@example.com", "password": "analyst-password"}
    ).json()
    customer = register(client, "customer@example.com")
    headers = authorization(analyst["token"])
    response = client.get(
        f"/api/analytics/transactions?kind=opening&user_id={customer['user']['id']}",
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["transactions"][0]["sender_email"] == "customer@example.com"
    assert body["transactions"][0]["destination_amount_minor"] == 100_000
    assert "password" not in response.text.lower()
    assert "token" not in response.text.lower()

    assert client.get(
        "/api/analytics/transactions?kind=opening%27%20OR%201%3D1", headers=headers
    ).status_code == 422


def test_analytics_pagination_is_bounded(client):
    create_analyst("analyst@example.com", "analyst-password")
    analyst = client.post(
        "/api/login", json={"email": "analyst@example.com", "password": "analyst-password"}
    ).json()
    headers = authorization(analyst["token"])
    assert client.get("/api/analytics/users?limit=101", headers=headers).status_code == 422
    assert client.get("/api/analytics/transactions?offset=-1", headers=headers).status_code == 422
    assert client.get("/api/analytics/users?offset=1000001", headers=headers).status_code == 422
    too_large = 9_223_372_036_854_775_808
    assert client.get(f"/api/analytics/transactions?user_id={too_large}", headers=headers).status_code == 422
    assert client.get(f"/api/analytics/audit-events?actor_user_id={too_large}", headers=headers).status_code == 422
    assert client.get(f"/api/analytics/audit-events?from={too_large}", headers=headers).status_code == 422
