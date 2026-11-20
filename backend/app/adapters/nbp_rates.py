"""Bounded NBP Table A client and its normalized rate-table contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

import httpx

from app.schemas import CurrencyCode

NBP_URL = "https://api.nbp.pl/api/exchangerates/tables/A/"
SUPPORTED_CURRENCIES: tuple[CurrencyCode, ...] = ("PLN", "EUR", "USD", "GBP", "CZK")


class RateProviderUnavailable(Exception):
    """The trusted rate source could not provide a valid current rate table."""


@dataclass(frozen=True)
class RateTable:
    provider: str
    effective_date: str
    pln_per_unit: dict[str, Decimal]
    table_id: str | None = None


class RateProvider(Protocol):
    def current_rates(self) -> RateTable: ...


class NBPRateProvider:
    """Fetch NBP's fixed endpoint with a short timeout and no redirects."""

    def current_rates(self) -> RateTable:
        try:
            with httpx.Client(
                timeout=httpx.Timeout(5.0, connect=3.0), follow_redirects=False
            ) as client:
                response = client.get(NBP_URL, headers={"Accept": "application/json"})
                response.raise_for_status()
            payload = json.loads(response.text, parse_float=Decimal)
            if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
                raise ValueError("Invalid table response")
            table = payload[0]
            if table.get("table") != "A" or not isinstance(table.get("effectiveDate"), str):
                raise ValueError("Unexpected table metadata")
            table_id = table.get("no")
            if table_id is not None and (not isinstance(table_id, str) or len(table_id) > 64):
                raise ValueError("Invalid table identifier")
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
            return RateTable("NBP Table A", table["effectiveDate"], rates, table_id)
        except (httpx.HTTPError, ValueError, TypeError, KeyError, InvalidOperation) as exc:
            raise RateProviderUnavailable from exc
