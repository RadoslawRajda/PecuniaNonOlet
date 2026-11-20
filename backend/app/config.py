"""Typed environment configuration and startup validation."""

from __future__ import annotations

import base64
import binascii
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
_request_settings: ContextVar[Settings | None] = ContextVar("request_settings", default=None)


class Settings(BaseSettings):
    """Application settings; production rejects local/test identity configuration."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_path: Path = Path("data/pecunia.db")
    profile_photo_dir: Path | None = None
    mfa_encryption_key: SecretStr = SecretStr("")
    turnstile_secret_key: SecretStr = SecretStr("")
    turnstile_expected_hostname: str = ""
    trusted_hosts: str = ""
    lan_ip: str = ""
    webauthn_rp_id: str = "pecunianonolet.local"
    webauthn_allowed_origins: str = (
        "https://pecunianonolet.local,https://pecunianonolet.local:8000,"
        "android:apk-key-hash:-sYXRdwJA3hvue3mKpYrOZ9zSPC7b4mbgzJmdZEDO5w"
    )
    google_oauth_client_ids: str = ""
    apple_team_id: str = "96UM85TJJ7"
    ios_bundle_id: str = "com.rajda.pecunianonolet"
    android_package_name: str = "com.pecunianonolet"
    android_sha256_cert_fingerprints: str = (
        "FA:C6:17:45:DC:09:03:78:6F:B9:ED:E6:2A:96:2B:39:9F:73:48:F0:"
        "BB:6F:89:9B:83:32:66:75:91:03:3B:9C"
    )

    @field_validator("database_path", mode="before")
    @classmethod
    def nonempty_database_path(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("DATABASE_PATH must not be empty")
        return value

    @model_validator(mode="after")
    def validate_production_profile(self) -> Settings:
        if self.app_env != "production":
            return self

        errors: list[str] = []
        key = self.mfa_encryption_key.get_secret_value().strip()
        try:
            decoded_key = base64.b64decode(key.encode("ascii"), altchars=b"-_", validate=True)
        except (ValueError, UnicodeEncodeError, binascii.Error):
            decoded_key = b""
        if len(decoded_key) != 32:
            errors.append("MFA_ENCRYPTION_KEY must encode exactly 32 bytes")

        secret = self.turnstile_secret_key.get_secret_value().strip()
        if not secret or secret == "1x0000000000000000000000000000000AA":
            errors.append("TURNSTILE_SECRET_KEY must be a private production key")
        if not self.google_oauth_client_ids.strip():
            errors.append("GOOGLE_OAUTH_CLIENT_IDS must be configured")
        trusted_hosts = [value.strip() for value in self.trusted_hosts.split(",") if value.strip()]
        if not trusted_hosts or any("*" in host for host in trusted_hosts):
            errors.append("TRUSTED_HOSTS must list explicit production hostnames")
        if not self.webauthn_rp_id.strip() or self.webauthn_rp_id.endswith(".local"):
            errors.append("WEBAUTHN_RP_ID must be a public production domain")
        origins = [
            item.strip() for item in self.webauthn_allowed_origins.split(",") if item.strip()
        ]
        if not origins or any(
            not (
                item.startswith("android:apk-key-hash:")
                or (
                    item.startswith("https://")
                    and bool(urlsplit(item).hostname)
                    and not (urlsplit(item).hostname or "").endswith(".local")
                )
            )
            for item in origins
        ):
            errors.append("WEBAUTHN_ALLOWED_ORIGINS must contain HTTPS or Android origins")
        if self.android_sha256_cert_fingerprints.strip().upper() == (
            "FA:C6:17:45:DC:09:03:78:6F:B9:ED:E6:2A:96:2B:39:9F:73:48:F0:"
            "BB:6F:89:9B:83:32:66:75:91:03:3B:9C"
        ):
            errors.append("ANDROID_SHA256_CERT_FINGERPRINTS must not use the debug certificate")
        if not self.apple_team_id.strip() or not self.ios_bundle_id.strip():
            errors.append("APPLE_TEAM_ID and IOS_BUNDLE_ID must be configured")
        if (
            not self.android_package_name.strip()
            or not self.android_sha256_cert_fingerprints.strip()
        ):
            errors.append("Android app id and signing fingerprints must be configured")
        if errors:
            raise ValueError("Invalid production configuration: " + "; ".join(errors))
        return self


def load_settings() -> Settings:
    """Return request-scoped settings or load environment settings without caching."""
    return _request_settings.get() or Settings()


def bind_settings(settings: Settings) -> Token[Settings | None]:
    """Bind app-specific configuration to this request and its worker-thread context."""
    return _request_settings.set(settings)


def reset_settings(token: Token[Settings | None]) -> None:
    """Restore the previous request configuration after response processing."""
    _request_settings.reset(token)
