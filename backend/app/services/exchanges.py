"""Atomic exchange execution over a previously issued quote."""

from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass

from fastapi import HTTPException, status

from app.audit import write_audit_event
from app.database import connect_db
from app.money import MAX_BALANCE_MINOR
from app.schemas import CurrencyCode, ExchangeRequest, User


@dataclass(frozen=True, slots=True)
class ExchangeExecution:
    """Named result of a committed exchange or an identical idempotent replay."""

    transaction_id: str
    quote_id: str
    source_amount_minor: int
    destination_amount_minor: int
    source_currency_code: CurrencyCode
    destination_currency_code: CurrencyCode
    source_minor_unit: int
    destination_minor_unit: int
    exchange_rate: str
    created_at: int
    replay: bool


def _require_active_session(
    db: sqlite3.Connection, session_id: str, user_id: int, now: int
) -> None:
    active = db.execute(
        """SELECT 1 FROM auth_sessions WHERE session_id = ? AND user_id = ?
           AND access_expires_at > ? AND refresh_expires_at > ?
           AND absolute_expires_at > ? AND revoked_at IS NULL""",
        (session_id, user_id, now, now, now),
    ).fetchone()
    if active is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")


def _execution_from_row(row: sqlite3.Row, *, replay: bool) -> ExchangeExecution:
    return ExchangeExecution(
        transaction_id=row["id"],
        quote_id=row["quote_id"],
        source_amount_minor=row["source_amount_minor"],
        destination_amount_minor=row["destination_amount_minor"],
        source_currency_code=row["source_currency_code"],
        destination_currency_code=row["destination_currency_code"],
        source_minor_unit=row["source_minor_unit"],
        destination_minor_unit=row["destination_minor_unit"],
        exchange_rate=row["exchange_rate"],
        created_at=row["created_at"],
        replay=replay,
    )


def _find_execution(
    db: sqlite3.Connection,
    *,
    user_id: int | None = None,
    key: str | None = None,
    transaction_id: str | None = None,
) -> sqlite3.Row | None:
    parameters: tuple[int | str, ...]
    if transaction_id is not None:
        condition, parameters = "t.id = ?", (transaction_id,)
    elif user_id is not None and key is not None:
        condition, parameters = "t.sender_user_id = ? AND t.idempotency_key = ?", (user_id, key)
    else:
        raise ValueError("Provide either transaction ID or user ID with idempotency key")
    return db.execute(
        """SELECT t.*, q.id AS quote_id, sc.minor_unit AS source_minor_unit,
                  dc.minor_unit AS destination_minor_unit
           FROM transactions t
           LEFT JOIN exchange_quotes q ON q.consumed_transaction_id = t.id
           LEFT JOIN currencies sc ON sc.code = t.source_currency_code
           JOIN currencies dc ON dc.code = t.destination_currency_code
           WHERE """
        + condition,
        parameters,
    ).fetchone()


def _replayed_exchange(
    db: sqlite3.Connection, payload: ExchangeRequest, user_id: int, key: str
) -> ExchangeExecution | None:
    prior = _find_execution(db, user_id=user_id, key=key)
    if prior is None:
        return None
    if prior["kind"] != "exchange" or prior["quote_id"] != str(payload.quote_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Klucz idempotencji został użyty dla innej operacji."
        )
    return _execution_from_row(prior, replay=True)


def _usable_quote(db: sqlite3.Connection, quote_id: str, user_id: int, now: int) -> sqlite3.Row:
    quote = db.execute(
        "SELECT * FROM exchange_quotes WHERE id = ? AND user_id = ?", (quote_id, user_id)
    ).fetchone()
    if quote is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono wyceny.")
    if quote["expires_at"] <= now:
        raise HTTPException(status.HTTP_409_CONFLICT, "Wycena wygasła. Pobierz nową.")
    if quote["consumed_at"] is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Wycena została już wykorzystana.")
    return quote


def _check_balances(db: sqlite3.Connection, quote: sqlite3.Row, user_id: int) -> None:
    source = db.execute(
        "SELECT balance_minor FROM accounts WHERE id = ? AND user_id = ? AND currency_code = ?",
        (quote["source_account_id"], user_id, quote["source_currency_code"]),
    ).fetchone()
    destination = db.execute(
        "SELECT balance_minor FROM accounts WHERE id = ? AND user_id = ? AND currency_code = ?",
        (quote["destination_account_id"], user_id, quote["destination_currency_code"]),
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


def _move_balances(db: sqlite3.Connection, quote: sqlite3.Row, user_id: int) -> None:
    db.execute(
        """UPDATE accounts SET balance_minor = balance_minor - ?
           WHERE id = ? AND user_id = ? AND balance_minor >= ?""",
        (
            quote["source_amount_minor"],
            quote["source_account_id"],
            user_id,
            quote["source_amount_minor"],
        ),
    )
    if db.execute("SELECT changes()").fetchone()[0] != 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Niewystarczające środki na rachunku źródłowym."
        )
    db.execute(
        """UPDATE accounts SET balance_minor = balance_minor + ?
           WHERE id = ? AND user_id = ?""",
        (quote["destination_amount_minor"], quote["destination_account_id"], user_id),
    )
    if db.execute("SELECT changes()").fetchone()[0] != 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nie udało się uznać rachunku docelowego.")


def _record_exchange(
    db: sqlite3.Connection,
    quote: sqlite3.Row,
    user: User,
    key: str,
    transaction_id: str,
    now: int,
) -> None:
    """Insert transaction, ledger and audit, and consume the quote on the caller's connection."""
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
        """INSERT INTO ledger_entries(
            transaction_id, account_id, account_user_id, amount_minor, created_at
        ) VALUES (?, ?, ?, ?, ?)""",
        (transaction_id, quote["source_account_id"], user.id, -quote["source_amount_minor"], now),
    )
    db.execute(
        """INSERT INTO ledger_entries(
            transaction_id, account_id, account_user_id, amount_minor, created_at
        ) VALUES (?, ?, ?, ?, ?)""",
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


def execute_exchange_transaction(
    payload: ExchangeRequest, user: User, session_id: str, idempotency_key: str
) -> ExchangeExecution:
    """Execute one quote atomically; replay only an identical idempotency key.

    BEGIN IMMEDIATE owns the active-session check, balance movement, quote consumption,
    transaction, ledger and audit. An error rolls every write back together.
    """
    key = idempotency_key.strip()
    if not key:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Klucz idempotencji nie może być pusty."
        )
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        now = int(time.time())
        _require_active_session(db, session_id, user.id, now)
        replay = _replayed_exchange(db, payload, user.id, key)
        if replay is not None:
            return replay
        quote = _usable_quote(db, str(payload.quote_id), user.id, now)
        _check_balances(db, quote, user.id)
        _move_balances(db, quote, user.id)
        transaction_id = str(uuid.uuid4())
        _record_exchange(db, quote, user, key, transaction_id, now)
        row = _find_execution(db, transaction_id=transaction_id)
        if row is None:
            raise RuntimeError("Recorded exchange transaction is missing")
    return _execution_from_row(row, replay=False)
