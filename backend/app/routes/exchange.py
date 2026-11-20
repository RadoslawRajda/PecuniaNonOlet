"""NBP-backed exchange rates, short-lived quotes, and atomic exchanges."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.adapters.nbp_rates import NBPRateProvider, RateProvider, RateProviderUnavailable, RateTable
from app.authorization import AuthenticatedSession, current_session, require_roles
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
from app.services.exchange_quotes import (
    QuoteResult,
    create_quote,
)
from app.services.exchanges import ExchangeExecution, execute_exchange_transaction

router = APIRouter(prefix="/api")
AuthenticatedUser = Annotated[User, Depends(require_roles("user"))]
ActiveSession = Annotated[AuthenticatedSession, Depends(current_session)]
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


def timestamp(value: int) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def quote_response(result: QuoteResult) -> ExchangeQuoteResponse:
    return ExchangeQuoteResponse(
        quote_id=result.quote_id,
        source_account_id=result.source_account_id,
        destination_account_id=result.destination_account_id,
        source_currency_code=result.source_currency_code,
        destination_currency_code=result.destination_currency_code,
        source_amount_minor=result.source_amount_minor,
        source_amount=format_minor_units(result.source_amount_minor, result.source_minor_unit),
        destination_amount_minor=result.destination_amount_minor,
        destination_amount=format_minor_units(
            result.destination_amount_minor, result.destination_minor_unit
        ),
        exchange_rate=result.exchange_rate,
        source_pln_rate=result.source_pln_rate,
        destination_pln_rate=result.destination_pln_rate,
        provider=result.provider,
        table_id=result.table_id,
        effective_date=result.effective_date,
        expires_at=timestamp(result.expires_at),
    )


def exchange_response(result: ExchangeExecution) -> ExchangeResponse:
    return ExchangeResponse(
        transaction_id=result.transaction_id,
        quote_id=result.quote_id,
        status="completed",
        source_amount_minor=result.source_amount_minor,
        source_amount=format_minor_units(result.source_amount_minor, result.source_minor_unit),
        destination_amount_minor=result.destination_amount_minor,
        destination_amount=format_minor_units(
            result.destination_amount_minor, result.destination_minor_unit
        ),
        source_currency_code=result.source_currency_code,
        destination_currency_code=result.destination_currency_code,
        exchange_rate=result.exchange_rate,
        created_at=timestamp(result.created_at),
        idempotent_replay=result.replay,
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
    return quote_response(create_quote(payload, user.id, table))


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
    result = execute_exchange_transaction(payload, user, session.session_id, idempotency_key)
    return exchange_response(result)
