"""Atomic exchange execution use case over a previously issued quote."""

from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import closing

from fastapi import HTTPException, status

from app.audit import write_audit_event
from app.database import connect_db
from app.schemas import ExchangeRequest, User

MAX_BALANCE_MINOR = 9_000_000_000_000_000


def execute_exchange_transaction(
    payload: ExchangeRequest, user: User, session_id: str, idempotency_key: str
) -> tuple[sqlite3.Row, bool]:
    key = idempotency_key.strip()
    if not key:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Klucz idempotencji nie może być pusty."
        )
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        now = int(time.time())
        session_row = db.execute(
            """SELECT 1 FROM auth_sessions WHERE session_id = ? AND user_id = ?
               AND access_expires_at > ? AND refresh_expires_at > ?
               AND absolute_expires_at > ? AND revoked_at IS NULL""",
            (session_id, user.id, now, now, now),
        ).fetchone()
        if session_row is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")
        prior = db.execute(
            """SELECT t.*, q.id AS quote_id, sc.minor_unit AS source_minor_unit,
                      dc.minor_unit AS destination_minor_unit
               FROM transactions t
               LEFT JOIN exchange_quotes q ON q.consumed_transaction_id = t.id
               LEFT JOIN currencies sc ON sc.code = t.source_currency_code
               JOIN currencies dc ON dc.code = t.destination_currency_code
               WHERE t.sender_user_id = ? AND t.idempotency_key = ?""",
            (user.id, key),
        ).fetchone()
        if prior is not None:
            if prior["kind"] != "exchange" or prior["quote_id"] != payload.quote_id:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "Klucz idempotencji został użyty dla innej operacji."
                )
            return prior, True

        quote = db.execute(
            "SELECT * FROM exchange_quotes WHERE id = ? AND user_id = ?",
            (payload.quote_id, user.id),
        ).fetchone()
        if quote is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono wyceny.")
        if quote["expires_at"] <= now:
            raise HTTPException(status.HTTP_409_CONFLICT, "Wycena wygasła. Pobierz nową.")
        if quote["consumed_at"] is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Wycena została już wykorzystana.")
        source = db.execute(
            "SELECT balance_minor FROM accounts WHERE id = ? AND user_id = ? AND currency_code = ?",
            (quote["source_account_id"], user.id, quote["source_currency_code"]),
        ).fetchone()
        destination = db.execute(
            "SELECT balance_minor FROM accounts WHERE id = ? AND user_id = ? AND currency_code = ?",
            (quote["destination_account_id"], user.id, quote["destination_currency_code"]),
        ).fetchone()
        if source is None or destination is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono wskazanego rachunku.")
        if source["balance_minor"] < quote["source_amount_minor"]:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Niewystarczające środki na rachunku źródłowym."
            )
        if destination["balance_minor"] > MAX_BALANCE_MINOR - quote["destination_amount_minor"]:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Saldo rachunku docelowego przekroczyłoby limit."
            )

        db.execute(
            "UPDATE accounts SET balance_minor = balance_minor - ? WHERE id = ? AND user_id = ? AND balance_minor >= ?",
            (
                quote["source_amount_minor"],
                quote["source_account_id"],
                user.id,
                quote["source_amount_minor"],
            ),
        )
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Niewystarczające środki na rachunku źródłowym."
            )
        db.execute(
            "UPDATE accounts SET balance_minor = balance_minor + ? WHERE id = ? AND user_id = ?",
            (quote["destination_amount_minor"], quote["destination_account_id"], user.id),
        )
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Nie udało się uznać rachunku docelowego."
            )

        transaction_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO transactions(
                id, kind, status, sender_user_id, recipient_user_id,
                source_account_id, source_account_user_id, destination_account_id,
                destination_account_user_id, source_currency_code, destination_currency_code,
                source_amount_minor, destination_amount_minor, exchange_rate, provider,
                idempotency_key, created_at
            ) VALUES (?, 'exchange', 'completed', ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                transaction_id,
                user.id,
                quote["source_account_id"],
                user.id,
                quote["destination_account_id"],
                user.id,
                quote["source_currency_code"],
                quote["destination_currency_code"],
                quote["source_amount_minor"],
                quote["destination_amount_minor"],
                quote["exchange_rate"],
                quote["provider"],
                key,
                now,
            ),
        )
        db.execute(
            "INSERT INTO ledger_entries(transaction_id, account_id, account_user_id, amount_minor, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                transaction_id,
                quote["source_account_id"],
                user.id,
                -quote["source_amount_minor"],
                now,
            ),
        )
        db.execute(
            "INSERT INTO ledger_entries(transaction_id, account_id, account_user_id, amount_minor, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                transaction_id,
                quote["destination_account_id"],
                user.id,
                quote["destination_amount_minor"],
                now,
            ),
        )
        db.execute(
            """UPDATE exchange_quotes
               SET consumed_at = ?, consumed_transaction_id = ?
               WHERE id = ? AND consumed_at IS NULL AND expires_at > ?""",
            (now, transaction_id, quote["id"], now),
        )
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Wycena wygasła lub została już wykorzystana."
            )
        write_audit_event(
            db,
            actor_user_id=user.id,
            actor_role=user.role,
            action="financial.transaction_completed",
            entity_type="transaction",
            entity_id=transaction_id,
            details={
                "kind": "exchange",
                "status": "completed",
                "source_currency_code": quote["source_currency_code"],
                "source_amount_minor": quote["source_amount_minor"],
                "destination_currency_code": quote["destination_currency_code"],
                "destination_amount_minor": quote["destination_amount_minor"],
                "exchange_rate": quote["exchange_rate"],
            },
            created_at=now,
        )
        row = db.execute(
            """SELECT t.*, q.id AS quote_id, sc.minor_unit AS source_minor_unit,
                      dc.minor_unit AS destination_minor_unit
               FROM transactions t
               LEFT JOIN exchange_quotes q ON q.consumed_transaction_id = t.id
               JOIN currencies sc ON sc.code = t.source_currency_code
               JOIN currencies dc ON dc.code = t.destination_currency_code
               WHERE t.id = ?""",
            (transaction_id,),
        ).fetchone()
    return row, False
