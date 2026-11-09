"""NBP-backed exchange rates, short-lived quotes, and atomic exchanges."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import (
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    Decimal,
    InvalidOperation,
    localcontext,
)
from typing import Annotated, Protocol

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.audit import write_audit_event
from app.authorization import current_session, require_roles, token_hash
from app.database import connect_db
from app.routes.finance import format_minor_units
from app.schemas import (
    ExchangeQuoteRequest,
    ExchangeQuoteResponse,
    ExchangeRate,
    ExchangeRatesResponse,
    ExchangeRequest,
    ExchangeResponse,
    User,
)

router = APIRouter(prefix="/api")
AuthenticatedUser = Annotated[User, Depends(require_roles("user"))]
ActiveSession = Annotated[tuple[str, User], Depends(current_session)]
MAX_BALANCE_MINOR = 9_000_000_000_000_000
QUOTE_TTL_SECONDS = 120
SUPPORTED_CURRENCIES = ("PLN", "EUR", "USD", "GBP", "CZK")
NBP_URL = "https://api.nbp.pl/api/exchangerates/tables/A/"


class RateProviderUnavailable(Exception):
    """The trusted rate source could not provide a valid current rate table."""


@dataclass(frozen=True)
class RateTable:
    provider: str
    effective_date: str
    pln_per_unit: dict[str, Decimal]


class RateProvider(Protocol):
    def current_rates(self) -> RateTable: ...


class NBPRateProvider:
    def current_rates(self) -> RateTable:
        try:
            with httpx.Client(timeout=httpx.Timeout(5.0, connect=3.0), follow_redirects=False) as client:
                response = client.get(NBP_URL, headers={"Accept": "application/json"})
                response.raise_for_status()
            payload = json.loads(response.text, parse_float=Decimal)
            if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
                raise ValueError("Invalid table response")
            table = payload[0]
            if table.get("table") != "A" or not isinstance(table.get("effectiveDate"), str):
                raise ValueError("Unexpected table metadata")
            datetime.strptime(table["effectiveDate"], "%Y-%m-%d")
            raw_rates = table.get("rates")
            if not isinstance(raw_rates, list):
                raise TypeError("Missing rates")
            rates = {"PLN": Decimal(1)}
            for item in raw_rates:
                if not isinstance(item, dict) or not isinstance(item.get("code"), str):
                    continue
                if item["code"] not in SUPPORTED_CURRENCIES or item["code"] == "PLN":
                    continue
                value = item.get("mid")
                rate = value if isinstance(value, Decimal) else Decimal(str(value))
                if not rate.is_finite() or rate <= 0:
                    raise ValueError("Invalid currency rate")
                rates[item["code"]] = rate
            if set(rates) != set(SUPPORTED_CURRENCIES):
                raise ValueError("The rate table does not cover all supported currencies")
            return RateTable("NBP Table A", table["effectiveDate"], rates)
        except (httpx.HTTPError, ValueError, TypeError, KeyError, InvalidOperation) as exc:
            raise RateProviderUnavailable from exc


def get_rate_provider() -> RateProvider:
    return NBPRateProvider()


def provider_response(table: RateTable) -> ExchangeRatesResponse:
    return ExchangeRatesResponse(
        provider=table.provider,
        effective_date=table.effective_date,
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
    if set(table.pln_per_unit) != set(SUPPORTED_CURRENCIES):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Kursy walut są chwilowo niedostępne.")
    return table


def amount_in_minor_units(source_minor: int, rate: Decimal, minor_unit: int) -> int:
    with localcontext() as context:
        context.prec = 50
        quantum = Decimal(1).scaleb(-minor_unit)
        target_major = (Decimal(source_minor) / (10**2) * rate).quantize(
            quantum, rounding=ROUND_HALF_UP
        )
    result = int(target_major * (10**minor_unit))
    if result < 1 or result > MAX_BALANCE_MINOR:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Kwota po przewalutowaniu jest poza zakresem.")
    return result


def timestamp(value: int) -> str:
    return datetime.fromtimestamp(value, tz=UTC).isoformat().replace("+00:00", "Z")


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
        destination_amount=format_minor_units(row["destination_amount_minor"], row["destination_minor_unit"]),
        exchange_rate=row["exchange_rate"],
        provider=row["provider"],
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
        destination_amount=format_minor_units(row["destination_amount_minor"], row["destination_minor_unit"]),
        source_currency_code=row["source_currency_code"],
        destination_currency_code=row["destination_currency_code"],
        exchange_rate=row["exchange_rate"],
        created_at=timestamp(row["created_at"]),
        idempotent_replay=replay,
    )


@router.get("/exchange-rates", response_model=ExchangeRatesResponse)
def get_exchange_rates(
    _: AuthenticatedUser,
    provider: Annotated[RateProvider, Depends(get_rate_provider)],
) -> ExchangeRatesResponse:
    return provider_response(require_rate_table(provider))


@router.post("/exchange/quote", response_model=ExchangeQuoteResponse, status_code=201)
def create_exchange_quote(
    payload: ExchangeQuoteRequest,
    user: AuthenticatedUser,
    provider: Annotated[RateProvider, Depends(get_rate_provider)],
) -> ExchangeQuoteResponse:
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
        if source["id"] == destination["id"] or source["currency_code"] == destination["currency_code"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Wybierz dwa rachunki w różnych walutach.")

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
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Nieobsługiwana precyzja waluty.")
        destination_minor = amount_in_minor_units(payload.source_amount_minor, cross_rate, 2)
        now = int(time.time())
        quote_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO exchange_quotes(
                id, user_id, source_account_id, destination_account_id,
                source_currency_code, destination_currency_code,
                source_amount_minor, destination_amount_minor, exchange_rate,
                provider, effective_date, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                quote_id, user.id, source["id"], destination["id"], source_code,
                destination_code, payload.source_amount_minor, destination_minor,
                format(cross_rate, "f"), table.provider, table.effective_date,
                now, now + QUOTE_TTL_SECONDS,
            ),
        )
        db.execute(
            """INSERT INTO exchange_rate_snapshots(
                base_currency_code, quote_currency_code, rate, provider, fetched_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (source_code, destination_code, format(cross_rate, "f"), table.provider, now, now + QUOTE_TTL_SECONDS),
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
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> ExchangeResponse:
    key = idempotency_key.strip()
    if not key:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Klucz idempotencji nie może być pusty.")
    with closing(connect_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        now = int(time.time())
        session_row = db.execute(
            "SELECT 1 FROM sessions WHERE token_hash = ? AND user_id = ? AND expires_at > ?",
            (token_hash(session[0]), user.id, now),
        ).fetchone()
        if session_row is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesja jest nieważna lub wygasła.")
        prior = db.execute(
            """SELECT t.*, q.id AS quote_id, sc.minor_unit AS source_minor_unit,
                      dc.minor_unit AS destination_minor_unit
               FROM transactions t
               LEFT JOIN exchange_quotes q ON q.consumed_transaction_id = t.id
               JOIN currencies sc ON sc.code = t.source_currency_code
               JOIN currencies dc ON dc.code = t.destination_currency_code
               WHERE t.sender_user_id = ? AND t.idempotency_key = ?""",
            (user.id, key),
        ).fetchone()
        if prior is not None:
            if prior["kind"] != "exchange" or prior["quote_id"] != payload.quote_id:
                raise HTTPException(status.HTTP_409_CONFLICT, "Klucz idempotencji został użyty dla innej operacji.")
            return exchange_response(prior, replay=True)

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
            raise HTTPException(status.HTTP_409_CONFLICT, "Niewystarczające środki na rachunku źródłowym.")
        if destination["balance_minor"] > MAX_BALANCE_MINOR - quote["destination_amount_minor"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Saldo rachunku docelowego przekroczyłoby limit.")

        db.execute(
            "UPDATE accounts SET balance_minor = balance_minor - ? WHERE id = ? AND user_id = ? AND balance_minor >= ?",
            (quote["source_amount_minor"], quote["source_account_id"], user.id, quote["source_amount_minor"]),
        )
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Niewystarczające środki na rachunku źródłowym.")
        db.execute(
            "UPDATE accounts SET balance_minor = balance_minor + ? WHERE id = ? AND user_id = ?",
            (quote["destination_amount_minor"], quote["destination_account_id"], user.id),
        )
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Nie udało się uznać rachunku docelowego.")

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
                transaction_id, user.id, quote["source_account_id"], user.id,
                quote["destination_account_id"], user.id, quote["source_currency_code"],
                quote["destination_currency_code"], quote["source_amount_minor"],
                quote["destination_amount_minor"], quote["exchange_rate"], quote["provider"],
                key, now,
            ),
        )
        db.execute(
            "INSERT INTO ledger_entries(transaction_id, account_id, account_user_id, amount_minor, created_at) VALUES (?, ?, ?, ?, ?)",
            (transaction_id, quote["source_account_id"], user.id, -quote["source_amount_minor"], now),
        )
        db.execute(
            "INSERT INTO ledger_entries(transaction_id, account_id, account_user_id, amount_minor, created_at) VALUES (?, ?, ?, ?, ?)",
            (transaction_id, quote["destination_account_id"], user.id, quote["destination_amount_minor"], now),
        )
        db.execute(
            """UPDATE exchange_quotes
               SET consumed_at = ?, consumed_transaction_id = ?
               WHERE id = ? AND consumed_at IS NULL AND expires_at > ?""",
            (now, transaction_id, quote["id"], now),
        )
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Wycena wygasła lub została już wykorzystana.")
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
    return exchange_response(row, replay=False)
