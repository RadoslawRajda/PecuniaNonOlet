from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.money import MAX_BALANCE_MINOR
from app.password_policy import validate_password

MAX_SQLITE_INTEGER = 9_223_372_036_854_775_807
CurrencyCode = Literal["PLN", "EUR", "USD", "GBP", "CZK"]
TransactionDirection = Literal["incoming", "outgoing", "internal"]


class LoginCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128, repr=False)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class RegisterCredentials(LoginCredentials):
    password: str = Field(min_length=8, max_length=128, repr=False)

    @model_validator(mode="after")
    def reject_common_or_contextual_password(self) -> RegisterCredentials:
        validate_password(self.password, email=str(self.email))
        return self


class PublicRegisterRequest(RegisterCredentials):
    captcha_token: str = Field(min_length=1, max_length=2048, repr=False)


class User(BaseModel):
    id: int
    email: EmailStr
    role: Literal["user", "analyst"]


class AuthResponse(BaseModel):
    user: User
    access_token: str = Field(repr=False)
    refresh_token: str = Field(repr=False)
    token_type: str = "bearer"
    expires_in: int = 15 * 60
    refresh_expires_in: int = 30 * 24 * 60 * 60


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(
        min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]{43}$", repr=False
    )


class LogoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str | None = Field(
        default=None, min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]{43}$", repr=False
    )


class SessionSummary(BaseModel):
    session_id: str
    authentication_method: Literal["legacy", "password", "google", "passkey"]
    created_at: int
    authenticated_at: int
    current: bool


class SessionListResponse(BaseModel):
    current_session_id: str
    sessions: list[SessionSummary]


class RevokeSessionsResponse(BaseModel):
    revoked_count: int


class MfaLoginChallengeResponse(BaseModel):
    mfa_required: Literal[True] = True
    challenge_token: str
    expires_in: int


LoginResponse = AuthResponse | MfaLoginChallengeResponse


class MfaSetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str | None = Field(default=None, min_length=1, max_length=128, repr=False)


class MfaSetupResponse(BaseModel):
    secret: str = Field(repr=False)
    provisioning_uri: str = Field(repr=False)
    expires_at: int


class MfaCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        min_length=6,
        max_length=22,
        pattern=r"^(?:[0-9]{6}|(?:[A-Za-z0-9_-]{16}|[A-Za-z0-9_-]{22}))$",
        repr=False,
    )


class MfaLoginRequest(MfaCodeRequest):
    challenge_token: str = Field(
        min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]{43}$", repr=False
    )


class MfaTotpCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$", repr=False)


class MfaEnableResponse(BaseModel):
    totp_enabled: Literal[True] = True
    recovery_codes: list[str] = Field(repr=False)
    reauthentication_required: Literal[True] = True


class MfaDisableRequest(MfaCodeRequest):
    current_password: str | None = Field(default=None, min_length=1, max_length=128, repr=False)


class MfaDisableResponse(BaseModel):
    totp_enabled: Literal[False] = False
    reauthentication_required: Literal[True] = True


class MfaStatusResponse(BaseModel):
    totp_enabled: bool


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str | None = Field(default=None, min_length=1, max_length=128, repr=False)
    new_password: str = Field(min_length=8, max_length=128, repr=False)
    mfa_code: str | None = Field(
        default=None,
        min_length=6,
        max_length=22,
        pattern=r"^(?:[0-9]{6}|(?:[A-Za-z0-9_-]{16}|[A-Za-z0-9_-]{22}))$",
        repr=False,
    )

    @model_validator(mode="after")
    def reject_common_password(self) -> ChangePasswordRequest:
        validate_password(self.new_password)
        return self


class ChangePasswordResponse(BaseModel):
    message: str
    reauthentication_required: bool = True


class AccountBalance(BaseModel):
    id: int
    currency_code: CurrencyCode
    balance_minor: int
    balance: str


class AccountListResponse(BaseModel):
    accounts: list[AccountBalance]


class FinancialTransaction(BaseModel):
    id: str
    type: Literal["opening", "transfer", "exchange"]
    status: Literal["completed", "reversed"]
    direction: TransactionDirection
    currency_code: CurrencyCode
    amount_minor: int
    amount: str
    source_account_id: int | None
    destination_account_id: int | None
    source_currency_code: CurrencyCode | None
    destination_currency_code: CurrencyCode
    source_amount_minor: int | None
    source_amount: str | None
    destination_amount_minor: int
    destination_amount: str
    exchange_rate: str | None
    counterparty_email: EmailStr | None
    created_at: str


class TransactionPage(BaseModel):
    transactions: list[FinancialTransaction]
    limit: int
    offset: int
    total: int


class TransferRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "recipient_email": "odbiorca@example.test",
                    "source_account_id": 1,
                    "currency_code": "PLN",
                    "amount_minor": 1250,
                }
            ]
        },
    )

    recipient_email: EmailStr
    source_account_id: int = Field(gt=0, le=MAX_SQLITE_INTEGER, strict=True)
    currency_code: CurrencyCode
    amount_minor: int = Field(gt=0, le=MAX_BALANCE_MINOR, strict=True)

    @field_validator("recipient_email", mode="before")
    @classmethod
    def normalize_recipient_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class TransferResponse(BaseModel):
    transaction_id: str
    status: Literal["completed", "reversed"]
    currency_code: CurrencyCode
    amount_minor: int
    amount: str
    source_account_id: int
    destination_account_id: int
    recipient_email: EmailStr
    created_at: str
    idempotent_replay: bool


class ExchangeRate(BaseModel):
    currency_code: CurrencyCode
    pln_per_unit: str


class ExchangeRatesResponse(BaseModel):
    provider: str
    effective_date: str
    table_id: str | None = None
    base_currency_code: Literal["PLN"] = "PLN"
    rates: list[ExchangeRate]


class ExchangeQuoteRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "source_account_id": 1,
                    "destination_account_id": 2,
                    "source_amount_minor": 424,
                }
            ]
        },
    )

    source_account_id: int = Field(gt=0, le=MAX_SQLITE_INTEGER, strict=True)
    destination_account_id: int = Field(gt=0, le=MAX_SQLITE_INTEGER, strict=True)
    source_amount_minor: int = Field(gt=0, le=MAX_BALANCE_MINOR, strict=True)


class ExchangeQuoteResponse(BaseModel):
    quote_id: str
    source_account_id: int
    destination_account_id: int
    source_currency_code: CurrencyCode
    destination_currency_code: CurrencyCode
    source_amount_minor: int
    source_amount: str
    destination_amount_minor: int
    destination_amount: str
    exchange_rate: str
    # Quotes created before migration 0007 do not have the exact input rates.
    source_pln_rate: str | None
    destination_pln_rate: str | None
    provider: str
    table_id: str | None
    effective_date: str
    expires_at: str


class ExchangeRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"quote_id": "9fbe98e3-48e1-4e66-91e9-0dcb9ef0e70d"}]},
    )

    quote_id: UUID


class ExchangeResponse(BaseModel):
    transaction_id: str
    quote_id: str
    status: Literal["completed"]
    source_amount_minor: int
    source_amount: str
    destination_amount_minor: int
    destination_amount: str
    source_currency_code: CurrencyCode
    destination_currency_code: CurrencyCode
    exchange_rate: str
    created_at: str
    idempotent_replay: bool
