"""Authenticated read-only endpoints for balances and financial history."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.authorization import require_roles
from app.database import connect_db
from app.schemas import (
    AccountBalance,
    AccountListResponse,
    FinancialTransaction,
    TransactionPage,
    User,
)

router = APIRouter(prefix="/api")
AuthenticatedUser = Annotated[User, Depends(require_roles("user"))]


def format_minor_units(amount_minor: int, minor_unit: int) -> str:
    sign = "-" if amount_minor < 0 else ""
    whole, fraction = divmod(abs(amount_minor), 10**minor_unit)
    if minor_unit == 0:
        return f"{sign}{whole}"
    return f"{sign}{whole}.{fraction:0{minor_unit}d}"


def transaction_view(row: sqlite3.Row, user_id: int) -> FinancialTransaction:
    direction = "internal"
    if row["kind"] == "transfer":
        direction = "incoming" if row["recipient_user_id"] == user_id else "outgoing"
    if direction == "incoming":
        amount_minor = row["destination_amount_minor"]
        currency_code = row["destination_currency_code"]
        counterparty_email = row["sender_email"]
    elif row["kind"] == "opening":
        amount_minor = row["destination_amount_minor"]
        currency_code = row["destination_currency_code"]
        counterparty_email = None
    else:
        amount_minor = row["source_amount_minor"] or row["destination_amount_minor"]
        currency_code = row["source_currency_code"] or row["destination_currency_code"]
        counterparty_email = row["recipient_email"] if direction == "outgoing" else None

    source_minor_unit = row["source_minor_unit"]
    destination_minor_unit = row["destination_minor_unit"]
    return FinancialTransaction(
        id=row["id"],
        type=row["kind"],
        status=row["status"],
        direction=direction,
        currency_code=currency_code,
        amount_minor=amount_minor,
        amount=format_minor_units(
            amount_minor,
            destination_minor_unit if direction == "incoming" or row["kind"] == "opening" else source_minor_unit,
        ),
        source_account_id=row["source_account_id"],
        destination_account_id=row["destination_account_id"],
        source_currency_code=row["source_currency_code"],
        destination_currency_code=row["destination_currency_code"],
        source_amount_minor=row["source_amount_minor"],
        source_amount=(
            format_minor_units(row["source_amount_minor"], source_minor_unit)
            if row["source_amount_minor"] is not None
            else None
        ),
        destination_amount_minor=row["destination_amount_minor"],
        destination_amount=format_minor_units(
            row["destination_amount_minor"], destination_minor_unit
        ),
        exchange_rate=row["exchange_rate"],
        counterparty_email=counterparty_email,
        created_at=datetime.fromtimestamp(row["created_at"], tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    )


_TRANSACTION_SELECT = """
    SELECT t.*, sender.email AS sender_email, recipient.email AS recipient_email,
           source_currency.minor_unit AS source_minor_unit,
           destination_currency.minor_unit AS destination_minor_unit
    FROM transactions AS t
    JOIN currencies AS destination_currency ON destination_currency.code = t.destination_currency_code
    LEFT JOIN currencies AS source_currency ON source_currency.code = t.source_currency_code
    JOIN users AS sender ON sender.id = t.sender_user_id
    LEFT JOIN users AS recipient ON recipient.id = t.recipient_user_id
"""


@router.get("/accounts", response_model=AccountListResponse)
def list_accounts(user: AuthenticatedUser) -> AccountListResponse:
    with closing(connect_db()) as db:
        rows = db.execute(
            """
            SELECT a.id, a.currency_code, a.balance_minor, c.minor_unit
            FROM accounts AS a
            JOIN currencies AS c ON c.code = a.currency_code
            WHERE a.user_id = ?
            ORDER BY a.currency_code
            """,
            (user.id,),
        ).fetchall()
    return AccountListResponse(
        accounts=[
            AccountBalance(
                id=row["id"],
                currency_code=row["currency_code"],
                balance_minor=row["balance_minor"],
                balance=format_minor_units(row["balance_minor"], row["minor_unit"]),
            )
            for row in rows
        ]
    )


@router.get("/transactions", response_model=TransactionPage)
def list_transactions(
    user: AuthenticatedUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
) -> TransactionPage:
    predicate = "(t.sender_user_id = ? OR t.recipient_user_id = ?)"
    with closing(connect_db()) as db:
        db.execute("BEGIN")
        total = db.execute(
            f"SELECT count(*) FROM transactions AS t WHERE {predicate}", (user.id, user.id)
        ).fetchone()[0]
        rows = db.execute(
            f"{_TRANSACTION_SELECT} WHERE {predicate} ORDER BY t.created_at DESC, t.id DESC LIMIT ? OFFSET ?",
            (user.id, user.id, limit, offset),
        ).fetchall()
    return TransactionPage(
        transactions=[transaction_view(row, user.id) for row in rows],
        limit=limit,
        offset=offset,
        total=total,
    )


@router.get("/transactions/{transaction_id}", response_model=FinancialTransaction)
def get_transaction(
    transaction_id: str,
    user: AuthenticatedUser,
) -> FinancialTransaction:
    with closing(connect_db()) as db:
        row = db.execute(
            f"{_TRANSACTION_SELECT} WHERE t.id = ? AND (t.sender_user_id = ? OR t.recipient_user_id = ?)",
            (transaction_id, user.id, user.id),
        ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono transakcji.")
    return transaction_view(row, user.id)

