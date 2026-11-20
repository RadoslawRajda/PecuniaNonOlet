"""NBP-backed exchange rates, short-lived quotes, and atomic exchanges."""

from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import closing
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.adapters.nbp_rates import NBPRateProvider, RateProvider, RateProviderUnavailable, RateTable
from app.authorization import AuthenticatedSession, current_session, require_roles
from app.database import connect_db
from app.money import format_minor_units
from app.rate_limits import client_ip, enforce_rate_limit, identity_bucket, ip_bucket
from app.schemas import (
    CurrencyCode,
    ExchangeQuoteRequest,
    ExchangeQuoteResponse,
    ExchangeRate,
    ExchangeRatesResponse,
    ExchangeRequest,
    ExchangeResponse,
    User,
)
from app.services.exchanges import execute_exchange_transaction

router = APIRouter(prefix="/api")
AuthenticatedUser = Annotated[User, Depends(require_roles("user"))]
ActiveSession = Annotated[AuthenticatedSession, Depends(current_session)]
MAX_BALANCE_MINOR = 9_000_000_000_000_000
QUOTE_TTL_SECONDS = 120
MAX_RATE_AGE_DAYS = 7
SUPPORTED_CURRENCIES: tuple[CurrencyCode, ...] = ("PLN", "EUR", "USD", "GBP", "CZK")


def get_rate_provider() -> RateProvider:
    return NBPRateProvider()


def provider_response(table: RateTable) -> ExchangeRatesResponse:
    return ExchangeRatesResponse(
        provider=table.provider,
        effective_date=table.effective_date,
        table_id=table.table_id,
        rates=[
            ExchangeRate(currency_code=code, pln_per_unit=format(table.pln_per_unit[code], "f"))
            for code in SUPPORTED_CURRENCIES
        ],
    )


def require_rate_table(provider: RateProvider) -> RateTable:
    try:
        table = provider.current_rates()
    except RateProviderUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Kursy walut są chwilowo niedostępne.",
        ) from exc
    try:
        effective_date = date.fromisoformat(table.effective_date)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Kursy walut są chwilowo niedostępne."
        ) from exc
    age_days = (date.today() - effective_date).days
    if age_days < 0 or age_days > MAX_RATE_AGE_DAYS:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Kursy walut są zbyt stare.")
    if set(table.pln_per_unit) != set(SUPPORTED_CURRENCIES):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Kursy walut są chwilowo niedostępne."
        )
    if any(
        not isinstance(rate, Decimal) or not rate.is_finite() or rate <= 0
        for rate in table.pln_per_unit.values()
    ):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Kursy walut są chwilowo niedostępne."
        )
    return table


def amount_in_minor_units(
    source_minor: int,
    source_pln_rate: Decimal,
    destination_pln_rate: Decimal,
    source_minor_unit: int = 2,
    destination_minor_unit: int = 2,
) -> int:
    """Convert with exact decimal ratios, flooring only the final minor-unit result."""
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


def timestamp(value: int) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def quote_response(row: sqlite3.Row) -> ExchangeQuoteResponse:
    return ExchangeQuoteResponse(
        quote_id=row["id"],
        source_account_id=row["source_account_id"],
        destination_account_id=row["destination_account_id"],
        source_currency_code=row["source_currency_code"],
        destination_currency_code=row["destination_currency_code"],
        source_amount_minor=row["source_amount_minor"],
        source_amount=format_minor_units(row["source_amount_minor"], row["source_minor_unit"]),
        destination_amount_minor=row["destination_amount_minor"],
        destination_amount=format_minor_units(
            row["destination_amount_minor"], row["destination_minor_unit"]
        ),
        exchange_rate=row["exchange_rate"],
        source_pln_rate=row["source_pln_rate"],
        destination_pln_rate=row["destination_pln_rate"],
        provider=row["provider"],
        table_id=row["rate_table_id"],
        effective_date=row["effective_date"],
        expires_at=timestamp(row["expires_at"]),
    )


def exchange_response(row: sqlite3.Row, *, replay: bool) -> ExchangeResponse:
    return ExchangeResponse(
        transaction_id=row["id"],
        quote_id=row["quote_id"],
        status="completed",
        source_amount_minor=row["source_amount_minor"],
        source_amount=format_minor_units(row["source_amount_minor"], row["source_minor_unit"]),
        destination_amount_minor=row["destination_amount_minor"],
        destination_amount=format_minor_units(
            row["destination_amount_minor"], row["destination_minor_unit"]
        ),
        source_currency_code=row["source_currency_code"],
        destination_currency_code=row["destination_currency_code"],
        exchange_rate=row["exchange_rate"],
        created_at=timestamp(row["created_at"]),
        idempotent_replay=replay,
    )


@router.get("/exchange-rates", response_model=ExchangeRatesResponse)
def get_exchange_rates(
    user: AuthenticatedUser,
    request: Request,
    provider: Annotated[RateProvider, Depends(get_rate_provider)],
) -> ExchangeRatesResponse:
    address = client_ip(request.client.host if request.client else None)
    enforce_rate_limit(
        [ip_bucket("exchange_rates", address), identity_bucket("exchange_rates", str(user.id))],
        limits=[60, 30],
    )
    return provider_response(require_rate_table(provider))


@router.post("/exchange/quote", response_model=ExchangeQuoteResponse, status_code=201)
def create_exchange_quote(
    payload: ExchangeQuoteRequest,
    user: AuthenticatedUser,
    request: Request,
    provider: Annotated[RateProvider, Depends(get_rate_provider)],
) -> ExchangeQuoteResponse:
    address = client_ip(request.client.host if request.client else None)
    enforce_rate_limit(
        [ip_bucket("exchange_quote", address), identity_bucket("exchange_quote", str(user.id))],
        limits=[60, 30],
    )
    table = require_rate_table(provider)
    with closing(connect_db()) as db, db:
        source = db.execute(
            "SELECT id, currency_code FROM accounts WHERE id = ? AND user_id = ?",
            (payload.source_account_id, user.id),
        ).fetchone()
        destination = db.execute(
            "SELECT id, currency_code FROM accounts WHERE id = ? AND user_id = ?",
            (payload.destination_account_id, user.id),
        ).fetchone()
        if source is None or destination is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono wskazanego rachunku.")
        if (
            source["id"] == destination["id"]
            or source["currency_code"] == destination["currency_code"]
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Wybierz dwa rachunki w różnych walutach."
            )

        source_code = source["currency_code"]
        destination_code = destination["currency_code"]
        with localcontext() as context:
            context.prec = 50
            context.rounding = ROUND_HALF_EVEN
            cross_rate = table.pln_per_unit[source_code] / table.pln_per_unit[destination_code]
        units = db.execute(
            "SELECT code, minor_unit FROM currencies WHERE code IN (?, ?)",
            (source_code, destination_code),
        ).fetchall()
        minor_units = {row["code"]: row["minor_unit"] for row in units}
        if minor_units.get(source_code) != 2 or minor_units.get(destination_code) != 2:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Nieobsługiwana precyzja waluty."
            )
        destination_minor = amount_in_minor_units(
            payload.source_amount_minor,
            table.pln_per_unit[source_code],
            table.pln_per_unit[destination_code],
            minor_units[source_code],
            minor_units[destination_code],
        )
        now = int(time.time())
        quote_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO exchange_quotes(
                id, user_id, source_account_id, destination_account_id,
                source_currency_code, destination_currency_code,
                source_amount_minor, destination_amount_minor, exchange_rate,
                source_pln_rate, destination_pln_rate, provider, rate_table_id,
                effective_date, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                quote_id,
                user.id,
                source["id"],
                destination["id"],
                source_code,
                destination_code,
                payload.source_amount_minor,
                destination_minor,
                format(cross_rate, "f"),
                format(table.pln_per_unit[source_code], "f"),
                format(table.pln_per_unit[destination_code], "f"),
                table.provider,
                table.table_id,
                table.effective_date,
                now,
                now + QUOTE_TTL_SECONDS,
            ),
        )
        db.execute(
            """INSERT INTO exchange_rate_snapshots(
                base_currency_code, quote_currency_code, rate, provider, fetched_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                source_code,
                destination_code,
                format(cross_rate, "f"),
                table.provider,
                now,
                now + QUOTE_TTL_SECONDS,
            ),
        )
        row = db.execute(
            """SELECT q.*, sc.minor_unit AS source_minor_unit,
                      dc.minor_unit AS destination_minor_unit
               FROM exchange_quotes q
               JOIN currencies sc ON sc.code = q.source_currency_code
               JOIN currencies dc ON dc.code = q.destination_currency_code
               WHERE q.id = ?""",
            (quote_id,),
        ).fetchone()
    return quote_response(row)


@router.post("/exchange", response_model=ExchangeResponse, status_code=201)
def execute_exchange(
    payload: ExchangeRequest,
    user: AuthenticatedUser,
    session: ActiveSession,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> ExchangeResponse:
    address = client_ip(request.client.host if request.client else None)
    enforce_rate_limit(
        [ip_bucket("exchange_execute", address), identity_bucket("exchange_execute", str(user.id))],
        limits=[60, 30],
    )
    row, replay = execute_exchange_transaction(payload, user, session.session_id, idempotency_key)
    return exchange_response(row, replay=replay)
