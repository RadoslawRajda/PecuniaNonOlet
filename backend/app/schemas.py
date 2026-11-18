from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

MAX_SQLITE_INTEGER = 9_223_372_036_854_775_807

class LoginCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class RegisterCredentials(LoginCredentials):
    password: str = Field(min_length=8, max_length=128)


class PublicRegisterRequest(RegisterCredentials):
    captcha_token: str = Field(min_length=1, max_length=2048)


class User(BaseModel):
    id: int
    email: EmailStr
    role: Literal["user", "analyst"]


class AuthResponse(BaseModel):
    user: User
    token: str
    token_type: str = "bearer"
    expires_in: int = 7 * 24 * 60 * 60


class MfaLoginChallengeResponse(BaseModel):
    mfa_required: Literal[True] = True
    challenge_token: str
    expires_in: int


LoginResponse = AuthResponse | MfaLoginChallengeResponse


class MfaSetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)


class MfaSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    expires_at: int


class MfaCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=16, pattern=r"^(?:[0-9]{6}|[A-Za-z0-9_-]{16})$")


class MfaLoginRequest(MfaCodeRequest):
    challenge_token: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]{43}$")


class MfaTotpCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class MfaEnableResponse(BaseModel):
    totp_enabled: Literal[True] = True
    recovery_codes: list[str]
    reauthentication_required: Literal[True] = True


class MfaDisableRequest(MfaCodeRequest):
    current_password: str = Field(min_length=1, max_length=128)


class MfaDisableResponse(BaseModel):
    totp_enabled: Literal[False] = False
    reauthentication_required: Literal[True] = True


class MfaStatusResponse(BaseModel):
    totp_enabled: bool


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordResponse(BaseModel):
    message: str
    reauthentication_required: bool = True


class AccountBalance(BaseModel):
    id: int
    currency_code: Literal["PLN", "EUR", "USD", "GBP", "CZK"]
    balance_minor: int
    balance: str


class AccountListResponse(BaseModel):
    accounts: list[AccountBalance]


class FinancialTransaction(BaseModel):
    id: str
    type: Literal["opening", "transfer", "exchange"]
    status: Literal["completed", "reversed"]
    direction: Literal["incoming", "outgoing", "internal"]
    currency_code: Literal["PLN", "EUR", "USD", "GBP", "CZK"]
    amount_minor: int
    amount: str
    source_account_id: int | None
    destination_account_id: int | None
    source_currency_code: Literal["PLN", "EUR", "USD", "GBP", "CZK"] | None
    destination_currency_code: Literal["PLN", "EUR", "USD", "GBP", "CZK"]
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
    model_config = ConfigDict(extra="forbid")

    recipient_email: EmailStr
    source_account_id: int = Field(gt=0, le=MAX_SQLITE_INTEGER, strict=True)
    currency_code: Literal["PLN", "EUR", "USD", "GBP", "CZK"]
    amount_minor: int = Field(gt=0, le=9_000_000_000_000_000, strict=True)

    @field_validator("recipient_email", mode="before")
    @classmethod
    def normalize_recipient_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class TransferResponse(BaseModel):
    transaction_id: str
    status: Literal["completed", "reversed"]
    currency_code: Literal["PLN", "EUR", "USD", "GBP", "CZK"]
    amount_minor: int
    amount: str
    source_account_id: int
    destination_account_id: int
    recipient_email: EmailStr
    created_at: str
    idempotent_replay: bool


class ExchangeRate(BaseModel):
    currency_code: Literal["PLN", "EUR", "USD", "GBP", "CZK"]
    pln_per_unit: str


class ExchangeRatesResponse(BaseModel):
    provider: str
    effective_date: str
    table_id: str | None = None
    base_currency_code: Literal["PLN"] = "PLN"
    rates: list[ExchangeRate]


class ExchangeQuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_account_id: int = Field(gt=0, le=MAX_SQLITE_INTEGER, strict=True)
    destination_account_id: int = Field(gt=0, le=MAX_SQLITE_INTEGER, strict=True)
    source_amount_minor: int = Field(gt=0, le=9_000_000_000_000_000, strict=True)


class ExchangeQuoteResponse(BaseModel):
    quote_id: str
    source_account_id: int
    destination_account_id: int
    source_currency_code: Literal["PLN", "EUR", "USD", "GBP", "CZK"]
    destination_currency_code: Literal["PLN", "EUR", "USD", "GBP", "CZK"]
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
    model_config = ConfigDict(extra="forbid")

    quote_id: str = Field(min_length=36, max_length=36)


class ExchangeResponse(BaseModel):
    transaction_id: str
    quote_id: str
    status: Literal["completed"]
    source_amount_minor: int
    source_amount: str
    destination_amount_minor: int
    destination_amount: str
    source_currency_code: Literal["PLN", "EUR", "USD", "GBP", "CZK"]
    destination_currency_code: Literal["PLN", "EUR", "USD", "GBP", "CZK"]
    exchange_rate: str
    created_at: str
    idempotent_replay: bool
