"""Same-currency transfer use case and its atomic ledger transaction."""

from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, status

from app.audit import write_audit_event
from app.database import connect_db
from app.money import MAX_BALANCE_MINOR, format_minor_units
from app.schemas import TransferRequest, TransferResponse, User


@dataclass(frozen=True, slots=True)
class TransferParties:
    recipient_id: int
    recipient_email: str
    source_account_id: int
    destination_account_id: int


def _require_active_session(db: sqlite3.Connection, session_id: str, user_id: int) -> None:
    now = int(time.time())
    active = db.execute(
        """SELECT 1 FROM auth_sessions
           WHERE session_id = ? AND user_id = ?
             AND access_expires_at > ? AND refresh_expires_at > ?
             AND absolute_expires_at > ? AND revoked_at IS NULL""",
        (session_id, user_id, now, now, now),
    ).fetchone()
    if active is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")


def _replayed_transfer(
    db: sqlite3.Connection, payload: TransferRequest, user_id: int, key: str
) -> TransferResponse | None:
    prior = db.execute(
        "SELECT * FROM transactions WHERE sender_user_id = ? AND idempotency_key = ?",
        (user_id, key),
    ).fetchone()
    if prior is None:
        return None
    recipient = db.execute(
        "SELECT id, email FROM users WHERE email = ?", (payload.recipient_email,)
    ).fetchone()
    if not (
        prior["kind"] == "transfer"
        and prior["recipient_user_id"] is not None
        and prior["source_account_id"] == payload.source_account_id
        and prior["source_currency_code"] == payload.currency_code
        and prior["source_amount_minor"] == payload.amount_minor
        and prior["destination_currency_code"] == payload.currency_code
        and recipient is not None
        and recipient["id"] == prior["recipient_user_id"]
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Klucz idempotencji został już użyty dla innej operacji.",
        )
    return _response_from_row(prior, recipient["email"], idempotent_replay=True)


def _resolve_parties(
    db: sqlite3.Connection, payload: TransferRequest, user_id: int
) -> TransferParties:
    recipient = db.execute(
        "SELECT id, email FROM users WHERE email = ?", (payload.recipient_email,)
    ).fetchone()
    if recipient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono odbiorcy.")
    if recipient["id"] == user_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Nie można wykonać przelewu na własny rachunek."
        )

    source = db.execute(
        "SELECT id, currency_code, balance_minor FROM accounts WHERE id = ? AND user_id = ?",
        (payload.source_account_id, user_id),
    ).fetchone()
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono rachunku źródłowego.")
    if source["currency_code"] != payload.currency_code:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Waluta nie zgadza się z rachunkiem źródłowym.",
        )
    if source["balance_minor"] < payload.amount_minor:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Niewystarczające środki na wybranym rachunku."
        )

    destination = db.execute(
        "SELECT id, balance_minor FROM accounts WHERE user_id = ? AND currency_code = ?",
        (recipient["id"], payload.currency_code),
    ).fetchone()
    if destination is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Odbiorca nie ma rachunku w wybranej walucie."
        )
    if destination["balance_minor"] > MAX_BALANCE_MINOR - payload.amount_minor:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Saldo rachunku odbiorcy przekroczyłoby limit."
        )
    return TransferParties(
        recipient_id=recipient["id"],
        recipient_email=recipient["email"],
        source_account_id=source["id"],
        destination_account_id=destination["id"],
    )


def _move_balance(
    db: sqlite3.Connection, payload: TransferRequest, user_id: int, parties: TransferParties
) -> None:
    db.execute(
        """UPDATE accounts SET balance_minor = balance_minor - ?
           WHERE id = ? AND user_id = ? AND balance_minor >= ?""",
        (payload.amount_minor, parties.source_account_id, user_id, payload.amount_minor),
    )
    if db.execute("SELECT changes()").fetchone()[0] != 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Niewystarczające środki na wybranym rachunku."
        )
    db.execute(
        """UPDATE accounts SET balance_minor = balance_minor + ?
           WHERE id = ? AND user_id = ?""",
        (payload.amount_minor, parties.destination_account_id, parties.recipient_id),
    )
    if db.execute("SELECT changes()").fetchone()[0] != 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nie udało się uznać rachunku odbiorcy.")


def _response_from_row(
    row: sqlite3.Row,
    recipient_email: str,
    *,
    idempotent_replay: bool,
) -> TransferResponse:
    return TransferResponse(
        transaction_id=row["id"],
        status=row["status"],
        currency_code=row["source_currency_code"],
        amount_minor=row["source_amount_minor"],
        amount=format_minor_units(row["source_amount_minor"], 2),
        source_account_id=row["source_account_id"],
        destination_account_id=row["destination_account_id"],
        recipient_email=recipient_email,
        created_at=datetime.fromtimestamp(row["created_at"], tz=UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        idempotent_replay=idempotent_replay,
    )


def _record_transfer(
    db: sqlite3.Connection,
    payload: TransferRequest,
    user: User,
    parties: TransferParties,
    key: str,
    transaction_id: str,
    created_at: int,
) -> None:
    """Record transaction, both ledger entries and audit on the caller's connection."""
    db.execute(
        """INSERT INTO transactions(
            id, kind, status, sender_user_id, recipient_user_id,
            source_account_id, source_account_user_id,
            destination_account_id, destination_account_user_id,
            source_currency_code, destination_currency_code,
            source_amount_minor, destination_amount_minor,
            exchange_rate, provider, idempotency_key, created_at
        ) VALUES (?, 'transfer', 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)""",
        (
            transaction_id,
            user.id,
            parties.recipient_id,
            parties.source_account_id,
            user.id,
            parties.destination_account_id,
            parties.recipient_id,
            payload.currency_code,
            payload.currency_code,
            payload.amount_minor,
            payload.amount_minor,
            key,
            created_at,
        ),
    )
    db.execute(
        """INSERT INTO ledger_entries(
            transaction_id, account_id, account_user_id, amount_minor, created_at
        ) VALUES (?, ?, ?, ?, ?)""",
        (transaction_id, parties.source_account_id, user.id, -payload.amount_minor, created_at),
    )
    db.execute(
        """INSERT INTO ledger_entries(
            transaction_id, account_id, account_user_id, amount_minor, created_at
        ) VALUES (?, ?, ?, ?, ?)""",
        (
            transaction_id,
            parties.destination_account_id,
            parties.recipient_id,
            payload.amount_minor,
            created_at,
        ),
    )
    write_audit_event(
        db,
        actor_user_id=user.id,
        actor_role=user.role,
        action="financial.transaction_completed",
        entity_type="transaction",
        entity_id=transaction_id,
        details={
            "kind": "transfer",
            "status": "completed",
            "source_currency_code": payload.currency_code,
            "source_amount_minor": payload.amount_minor,
            "destination_currency_code": payload.currency_code,
            "destination_amount_minor": payload.amount_minor,
            "recipient_user_id": parties.recipient_id,
        },
        created_at=created_at,
    )


def create_transfer(
    payload: TransferRequest,
    user: User,
    session_id: str,
    idempotency_key: str,
) -> TransferResponse:
    """Transfer funds and audit them atomically; replay an identical key without new writes.

    BEGIN IMMEDIATE protects the session check, idempotency lookup and both balances.
    Any error rolls back debit, credit, transaction, ledger entries and audit together.
    """
    key = idempotency_key.strip()
    if not key:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Klucz idempotencji nie może być pusty."
        )

    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        _require_active_session(db, session_id, user.id)
        replay = _replayed_transfer(db, payload, user.id, key)
        if replay is not None:
            return replay
        parties = _resolve_parties(db, payload, user.id)
        _move_balance(db, payload, user.id, parties)
        created_at = int(time.time())
        transaction_id = str(uuid.uuid4())
        _record_transfer(db, payload, user, parties, key, transaction_id, created_at)
        row = db.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    return _response_from_row(row, parties.recipient_email, idempotent_replay=False)
