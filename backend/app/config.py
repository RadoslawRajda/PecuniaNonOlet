"""Typed environment configuration and startup validation."""

from __future__ import annotations

import base64
import binascii
import ipaddress
import re
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
_request_settings: ContextVar[Settings | None] = ContextVar("request_settings", default=None)
DEBUG_ANDROID_FINGERPRINT = (
    "FA:C6:17:45:DC:09:03:78:6F:B9:ED:E6:2A:96:2B:39:9F:73:48:F0:"
    "BB:6F:89:9B:83:32:66:75:91:03:3B:9C"
)
DEBUG_ANDROID_ORIGIN = "android:apk-key-hash:-sYXRdwJA3hvue3mKpYrOZ9zSPC7b4mbgzJmdZEDO5w"
_FINGERPRINT = re.compile(r"(?:[0-9A-F]{2}:){31}[0-9A-F]{2}\Z")
_DOMAIN = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\Z")
_APPLE_TEAM_ID = re.compile(r"[A-Z0-9]{10}\Z")
_IOS_BUNDLE_ID = re.compile(r"[A-Za-z][A-Za-z0-9-]*(?:\.[A-Za-z][A-Za-z0-9-]*)+\Z")
_ANDROID_PACKAGE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\Z")


def _list_items(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _public_domain(value: str) -> bool:
    if not _DOMAIN.fullmatch(value) or ".." in value or "." not in value:
        return False
    if value.endswith((".local", ".localhost", ".test", ".invalid", ".example")):
        return False
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return all(
            0 < len(label) <= 63 and not label.startswith("-") and not label.endswith("-")
            for label in value.split(".")
        )
    return False


def _valid_android_origin(value: str) -> bool:
    prefix = "android:apk-key-hash:"
    if not value.startswith(prefix):
        return False
    digest = value[len(prefix) :]
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", digest):
        return False
    try:
        return len(base64.urlsafe_b64decode(digest + "=")) == 32
    except (ValueError, binascii.Error):
        return False


def _valid_https_origin(value: str, rp_id: str) -> bool:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.username is None
        and parsed.password is None
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
        and port in (None, 443)
        and _public_domain(host)
        and (host == rp_id or host.endswith("." + rp_id))
    )


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
    google_ios_client_id: str = ""
    google_android_client_id: str = ""
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

    @field_validator(
        "trusted_hosts",
        "webauthn_allowed_origins",
        "google_ios_client_id",
        "google_android_client_id",
        "android_sha256_cert_fingerprints",
        mode="before",
    )
    @classmethod
    def normalize_list(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        items = _list_items(value)
        if len(items) != len(value.split(",")) and value.strip():
            raise ValueError("Configuration lists must not contain empty items")
        return ",".join(dict.fromkeys(items))

    @field_validator("webauthn_rp_id", mode="before")
    @classmethod
    def normalize_rp_id(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("trusted_hosts", mode="after")
    @classmethod
    def normalize_trusted_hosts(cls, value: str) -> str:
        return ",".join(dict.fromkeys(host.lower() for host in _list_items(value)))

    @field_validator("android_sha256_cert_fingerprints", mode="after")
    @classmethod
    def normalize_fingerprints(cls, value: str) -> str:
        return ",".join(item.upper() for item in _list_items(value))

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
        google_client_ids = (self.google_ios_client_id, self.google_android_client_id)
        if any(
            not re.fullmatch(r"[A-Za-z0-9_-]+\.apps\.googleusercontent\.com", item)
            for item in google_client_ids
        ):
            errors.append("GOOGLE_IOS_CLIENT_ID and GOOGLE_ANDROID_CLIENT_ID must be valid client IDs")
        trusted_hosts = _list_items(self.trusted_hosts)
        if not trusted_hosts or any(not _public_domain(host.lower()) for host in trusted_hosts):
            errors.append("TRUSTED_HOSTS must list explicit production hostnames")
        if not _public_domain(self.webauthn_rp_id):
            errors.append("WEBAUTHN_RP_ID must be a public production domain")
        if self.webauthn_rp_id not in {host.lower() for host in trusted_hosts}:
            errors.append("TRUSTED_HOSTS must include WEBAUTHN_RP_ID for association documents")
        origins = _list_items(self.webauthn_allowed_origins)
        if not origins or any(
            not (
                (_valid_android_origin(item) and item != DEBUG_ANDROID_ORIGIN)
                or _valid_https_origin(item, self.webauthn_rp_id)
            )
            for item in origins
        ):
            errors.append("WEBAUTHN_ALLOWED_ORIGINS must contain valid production origins")
        if f"https://{self.webauthn_rp_id}" not in origins:
            errors.append("WEBAUTHN_ALLOWED_ORIGINS must include the RP's HTTPS origin")
        fingerprints = _list_items(self.android_sha256_cert_fingerprints)
        if any(item == DEBUG_ANDROID_FINGERPRINT for item in fingerprints):
            errors.append("ANDROID_SHA256_CERT_FINGERPRINTS must not use the debug certificate")
        if any(not _FINGERPRINT.fullmatch(item) for item in fingerprints):
            errors.append("ANDROID_SHA256_CERT_FINGERPRINTS must contain SHA-256 fingerprints")
        if not _APPLE_TEAM_ID.fullmatch(self.apple_team_id):
            errors.append("APPLE_TEAM_ID must be a 10-character Apple team identifier")
        if not _IOS_BUNDLE_ID.fullmatch(self.ios_bundle_id):
            errors.append("IOS_BUNDLE_ID must be a valid reverse-DNS bundle identifier")
        if (
            not _ANDROID_PACKAGE_NAME.fullmatch(self.android_package_name)
            or not self.android_sha256_cert_fingerprints.strip()
        ):
            errors.append("Android package name and signing fingerprints must be valid")
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
