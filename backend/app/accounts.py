"""Currency account provisioning and the one-time opening balance."""

from __future__ import annotations

import sqlite3
import uuid

from app.audit import write_audit_event

SUPPORTED_CURRENCIES = ("PLN", "EUR", "USD", "GBP", "CZK")
INITIAL_PLN_MINOR = 100_000
INITIAL_BALANCE_IDEMPOTENCY_KEY = "opening-balance-pln-v1"


def initialize_user_accounts(db: sqlite3.Connection, user_id: int, created_at: int) -> None:
    if not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")
    for currency in SUPPORTED_CURRENCIES:
        db.execute(
            "INSERT OR IGNORE INTO accounts(user_id, currency_code, balance_minor) VALUES (?, ?, 0)",
            (user_id, currency),
        )

    existing_grant = db.execute(
        "SELECT id FROM transactions WHERE sender_user_id = ? AND idempotency_key = ?",
        (user_id, INITIAL_BALANCE_IDEMPOTENCY_KEY),
    ).fetchone()
    if existing_grant is not None:
        return

    account = db.execute(
        "SELECT id FROM accounts WHERE user_id = ? AND currency_code = 'PLN'", (user_id,)
    ).fetchone()
    if account is None:
        raise RuntimeError("Nie udało się utworzyć rachunku PLN.")

    db.execute(
        "UPDATE accounts SET balance_minor = balance_minor + ? WHERE id = ?",
        (INITIAL_PLN_MINOR, account["id"]),
    )
    transaction_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO transactions(
            id, kind, status, sender_user_id, recipient_user_id,
            source_account_id, source_account_user_id,
            destination_account_id, destination_account_user_id,
            source_currency_code, destination_currency_code,
            source_amount_minor, destination_amount_minor,
            exchange_rate, provider, idempotency_key, created_at
        ) VALUES (?, 'opening', 'completed', ?, NULL, NULL, NULL, ?, ?, NULL, 'PLN',
                  NULL, ?, NULL, NULL, ?, ?)
        """,
        (
            transaction_id,
            user_id,
            account["id"],
            user_id,
            INITIAL_PLN_MINOR,
            INITIAL_BALANCE_IDEMPOTENCY_KEY,
            created_at,
        ),
    )
    db.execute(
        """
        INSERT INTO ledger_entries(
            transaction_id, account_id, account_user_id, amount_minor, created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (transaction_id, account["id"], user_id, INITIAL_PLN_MINOR, created_at),
    )
    write_audit_event(
        db,
        actor_user_id=user_id,
        actor_role="user",
        action="financial.transaction_completed",
        entity_type="transaction",
        entity_id=transaction_id,
        details={
            "kind": "opening",
            "status": "completed",
            "currency_code": "PLN",
            "amount_minor": INITIAL_PLN_MINOR,
        },
        created_at=created_at,
    )
