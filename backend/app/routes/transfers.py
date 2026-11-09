"""Atomic same-currency transfers between user accounts."""

from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import closing
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.audit import write_audit_event
from app.authorization import current_session, require_roles, token_hash
from app.database import connect_db
from app.routes.finance import format_minor_units
from app.schemas import TransferRequest, TransferResponse, User

router = APIRouter(prefix="/api")
AuthenticatedUser = Annotated[User, Depends(require_roles("user"))]
ActiveSession = Annotated[tuple[str, User], Depends(current_session)]
MAX_BALANCE_MINOR = 9_000_000_000_000_000


def response_from_row(
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


@router.post("/transfers", response_model=TransferResponse, status_code=201)
def create_transfer(
    payload: TransferRequest,
    user: AuthenticatedUser,
    session: ActiveSession,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> TransferResponse:
    key = idempotency_key.strip()
    if not key:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Klucz idempotencji nie może być pusty.")

    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        active_session = db.execute(
            "SELECT 1 FROM sessions WHERE token_hash = ? AND user_id = ? AND expires_at > ?",
            (token_hash(session[0]), user.id, int(time.time())),
        ).fetchone()
        if active_session is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")
        prior = db.execute(
            """
            SELECT * FROM transactions
            WHERE sender_user_id = ? AND idempotency_key = ?
            """,
            (user.id, key),
        ).fetchone()
        if prior is not None:
            same_request = (
                prior["kind"] == "transfer"
                and prior["recipient_user_id"] is not None
                and prior["source_account_id"] == payload.source_account_id
                and prior["source_currency_code"] == payload.currency_code
                and prior["source_amount_minor"] == payload.amount_minor
                and prior["destination_currency_code"] == payload.currency_code
            )
            recipient = db.execute(
                "SELECT id, email FROM users WHERE email = ?", (payload.recipient_email,)
            ).fetchone()
            if not same_request or recipient is None or recipient["id"] != prior["recipient_user_id"]:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Klucz idempotencji został już użyty dla innej operacji.",
                )
            return response_from_row(prior, recipient["email"], idempotent_replay=True)

        recipient = db.execute(
            "SELECT id, email FROM users WHERE email = ?", (payload.recipient_email,)
        ).fetchone()
        if recipient is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono odbiorcy.")
        if recipient["id"] == user.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nie można wykonać przelewu na własny rachunek.")

        source = db.execute(
            "SELECT id, currency_code, balance_minor FROM accounts WHERE id = ? AND user_id = ?",
            (payload.source_account_id, user.id),
        ).fetchone()
        if source is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono rachunku źródłowego.")
        if source["currency_code"] != payload.currency_code:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Waluta nie zgadza się z rachunkiem źródłowym.")
        if source["balance_minor"] < payload.amount_minor:
            raise HTTPException(status.HTTP_409_CONFLICT, "Niewystarczające środki na wybranym rachunku.")

        destination = db.execute(
            "SELECT id, balance_minor FROM accounts WHERE user_id = ? AND currency_code = ?",
            (recipient["id"], payload.currency_code),
        ).fetchone()
        if destination is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Odbiorca nie ma rachunku w wybranej walucie.")
        if destination["balance_minor"] > MAX_BALANCE_MINOR - payload.amount_minor:
            raise HTTPException(status.HTTP_409_CONFLICT, "Saldo rachunku odbiorcy przekroczyłoby limit.")

        created_at = int(time.time())
        transaction_id = str(uuid.uuid4())
        db.execute(
            "UPDATE accounts SET balance_minor = balance_minor - ? WHERE id = ? AND user_id = ? AND balance_minor >= ?",
            (payload.amount_minor, source["id"], user.id, payload.amount_minor),
        )
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Niewystarczające środki na wybranym rachunku.")
        db.execute(
            "UPDATE accounts SET balance_minor = balance_minor + ? WHERE id = ? AND user_id = ?",
            (payload.amount_minor, destination["id"], recipient["id"]),
        )
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Nie udało się uznać rachunku odbiorcy.")

        db.execute(
            """
            INSERT INTO transactions(
                id, kind, status, sender_user_id, recipient_user_id,
                source_account_id, source_account_user_id,
                destination_account_id, destination_account_user_id,
                source_currency_code, destination_currency_code,
                source_amount_minor, destination_amount_minor,
                exchange_rate, provider, idempotency_key, created_at
            ) VALUES (?, 'transfer', 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                transaction_id,
                user.id,
                recipient["id"],
                source["id"],
                user.id,
                destination["id"],
                recipient["id"],
                payload.currency_code,
                payload.currency_code,
                payload.amount_minor,
                payload.amount_minor,
                key,
                created_at,
            ),
        )
        db.execute(
            "INSERT INTO ledger_entries(transaction_id, account_id, account_user_id, amount_minor, created_at) VALUES (?, ?, ?, ?, ?)",
            (transaction_id, source["id"], user.id, -payload.amount_minor, created_at),
        )
        db.execute(
            "INSERT INTO ledger_entries(transaction_id, account_id, account_user_id, amount_minor, created_at) VALUES (?, ?, ?, ?, ?)",
            (transaction_id, destination["id"], recipient["id"], payload.amount_minor, created_at),
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
                "recipient_user_id": recipient["id"],
            },
            created_at=created_at,
        )
        row = db.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    return response_from_row(row, recipient["email"], idempotent_replay=False)
