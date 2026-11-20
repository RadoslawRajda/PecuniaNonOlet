"""Quote creation from a validated rate table and the caller's own accounts."""

from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from fastapi import HTTPException, status

from app.adapters.nbp_rates import RateTable
from app.database import connect_db
from app.money import MAX_BALANCE_MINOR
from app.schemas import CurrencyCode, ExchangeQuoteRequest

QUOTE_TTL_SECONDS = 120


@dataclass(frozen=True, slots=True)
class QuoteResult:
    quote_id: str
    source_account_id: int
    destination_account_id: int
    source_currency_code: CurrencyCode
    destination_currency_code: CurrencyCode
    source_amount_minor: int
    destination_amount_minor: int
    source_minor_unit: int
    destination_minor_unit: int
    exchange_rate: str
    source_pln_rate: str
    destination_pln_rate: str
    provider: str
    table_id: str | None
    effective_date: str
    expires_at: int


def amount_in_minor_units(
    source_minor: int,
    source_pln_rate: Decimal,
    destination_pln_rate: Decimal,
    source_minor_unit: int = 2,
    destination_minor_unit: int = 2,
) -> int:
    """Convert exact decimal ratios and floor only the final destination minor units."""
    source_numerator, source_denominator = source_pln_rate.as_integer_ratio()
    destination_numerator, destination_denominator = destination_pln_rate.as_integer_ratio()
    numerator = (
        source_minor * source_numerator * destination_denominator * 10**destination_minor_unit
    )
    denominator = source_denominator * destination_numerator * 10**source_minor_unit
    result = numerator // denominator
    if result < 1 or result > MAX_BALANCE_MINOR:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Kwota po przewalutowaniu jest poza zakresem."
        )
    return result


def _quote_accounts(
    db: sqlite3.Connection, payload: ExchangeQuoteRequest, user_id: int
) -> tuple[CurrencyCode, CurrencyCode]:
    source = db.execute(
        "SELECT id, currency_code FROM accounts WHERE id = ? AND user_id = ?",
        (payload.source_account_id, user_id),
    ).fetchone()
    destination = db.execute(
        "SELECT id, currency_code FROM accounts WHERE id = ? AND user_id = ?",
        (payload.destination_account_id, user_id),
    ).fetchone()
    if source is None or destination is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono wskazanego rachunku.")
    if source["id"] == destination["id"] or source["currency_code"] == destination["currency_code"]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Wybierz dwa rachunki w różnych walutach."
        )
    return source["currency_code"], destination["currency_code"]


def _minor_units(
    db: sqlite3.Connection, source_code: CurrencyCode, destination_code: CurrencyCode
) -> tuple[int, int]:
    units = db.execute(
        "SELECT code, minor_unit FROM currencies WHERE code IN (?, ?)",
        (source_code, destination_code),
    ).fetchall()
    by_code = {row["code"]: row["minor_unit"] for row in units}
    if by_code.get(source_code) != 2 or by_code.get(destination_code) != 2:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Nieobsługiwana precyzja waluty.")
    return by_code[source_code], by_code[destination_code]


def _cross_rate(source_pln_rate: Decimal, destination_pln_rate: Decimal) -> str:
    # Presentation only. Settlement uses the exact source and destination rates.
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        return format(source_pln_rate / destination_pln_rate, "f")


def _store_quote(db: sqlite3.Connection, result: QuoteResult, user_id: int, now: int) -> None:
    """Persist the quote and its display-rate snapshot in the caller's transaction."""
    db.execute(
        """INSERT INTO exchange_quotes(
            id, user_id, source_account_id, destination_account_id,
            source_currency_code, destination_currency_code,
            source_amount_minor, destination_amount_minor, exchange_rate,
            source_pln_rate, destination_pln_rate, provider, rate_table_id,
            effective_date, created_at, expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            result.quote_id,
            user_id,
            result.source_account_id,
            result.destination_account_id,
            result.source_currency_code,
            result.destination_currency_code,
            result.source_amount_minor,
            result.destination_amount_minor,
            result.exchange_rate,
            result.source_pln_rate,
            result.destination_pln_rate,
            result.provider,
            result.table_id,
            result.effective_date,
            now,
            result.expires_at,
        ),
    )
    db.execute(
        """INSERT INTO exchange_rate_snapshots(
            base_currency_code, quote_currency_code, rate, provider, fetched_at, expires_at
        ) VALUES (?, ?, ?, ?, ?, ?)""",
        (
            result.source_currency_code,
            result.destination_currency_code,
            result.exchange_rate,
            result.provider,
            now,
            result.expires_at,
        ),
    )


def create_quote(payload: ExchangeQuoteRequest, user_id: int, table: RateTable) -> QuoteResult:
    """Issue one quote using owned accounts and a previously validated rate table.

    The quote and rate snapshot commit together. Funds are checked again under the
    execution lock; issuing a quote does not reserve the user's balance.
    """
    with closing(connect_db()) as db, db:
        source_code, destination_code = _quote_accounts(db, payload, user_id)
        source_unit, destination_unit = _minor_units(db, source_code, destination_code)
        source_rate = table.pln_per_unit[source_code]
        destination_rate = table.pln_per_unit[destination_code]
        destination_minor = amount_in_minor_units(
            payload.source_amount_minor,
            source_rate,
            destination_rate,
            source_unit,
            destination_unit,
        )
        now = int(time.time())
        result = QuoteResult(
            quote_id=str(uuid.uuid4()),
            source_account_id=payload.source_account_id,
            destination_account_id=payload.destination_account_id,
            source_currency_code=source_code,
            destination_currency_code=destination_code,
            source_amount_minor=payload.source_amount_minor,
            destination_amount_minor=destination_minor,
            source_minor_unit=source_unit,
            destination_minor_unit=destination_unit,
            exchange_rate=_cross_rate(source_rate, destination_rate),
            source_pln_rate=format(source_rate, "f"),
            destination_pln_rate=format(destination_rate, "f"),
            provider=table.provider,
            table_id=table.table_id,
            effective_date=table.effective_date,
            expires_at=now + QUOTE_TTL_SECONDS,
        )
        _store_quote(db, result, user_id, now)
    return result
