"""TOTP primitives and authenticated encryption for MFA secrets."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time

import pyotp
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import load_settings

TOTP_PERIOD_SECONDS = 30
TOTP_DIGITS = 6
TOTP_WINDOW_STEPS = 1
TOTP_SETUP_LIFETIME_SECONDS = 10 * 60
LOGIN_CHALLENGE_LIFETIME_SECONDS = 5 * 60
MFA_FAILURE_WINDOW_SECONDS = 15 * 60
MFA_LOCKOUT_SECONDS = 15 * 60
MFA_MAX_FAILED_ATTEMPTS = 5
RECOVERY_CODE_COUNT = 10
_TOTP_CODE = re.compile(r"^[0-9]{6}$")


class MFAConfigurationError(RuntimeError):
    """The server cannot safely encrypt or decrypt MFA secrets."""


def _encryption_key() -> bytes:
    configured = load_settings().mfa_encryption_key.get_secret_value().strip()
    if not configured:
        raise MFAConfigurationError("MFA_ENCRYPTION_KEY is not configured")
    try:
        key = base64.b64decode(configured.encode("ascii"), altchars=b"-_", validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise MFAConfigurationError("MFA_ENCRYPTION_KEY must be URL-safe base64") from exc
    if len(key) != 32:
        raise MFAConfigurationError("MFA_ENCRYPTION_KEY must decode to exactly 32 bytes")
    return key


def encrypt_secret(user_id: int, secret: str, *, purpose: str) -> bytes:
    nonce = secrets.token_bytes(12)
    associated_data = f"pecunianonolet:totp:{user_id}:{purpose}:v1".encode("ascii")
    ciphertext = AESGCM(_encryption_key()).encrypt(nonce, secret.encode("ascii"), associated_data)
    return nonce + ciphertext


def decrypt_secret(user_id: int, ciphertext: bytes, *, purpose: str) -> str:
    if len(ciphertext) < 12 + 16:
        raise MFAConfigurationError("Stored MFA secret is invalid")
    nonce, encrypted = ciphertext[:12], ciphertext[12:]
    associated_data = f"pecunianonolet:totp:{user_id}:{purpose}:v1".encode("ascii")
    try:
        secret = AESGCM(_encryption_key()).decrypt(nonce, encrypted, associated_data)
        return secret.decode("ascii")
    except (InvalidTag, UnicodeDecodeError, ValueError) as exc:
        raise MFAConfigurationError("Stored MFA secret cannot be decrypted") from exc


def create_totp_secret() -> str:
    return pyotp.random_base32(length=32)


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(
        secret, digits=TOTP_DIGITS, interval=TOTP_PERIOD_SECONDS, digest=hashlib.sha1
    ).provisioning_uri(name=email, issuer_name="Pecunia non olet")


def matching_totp_step(secret: str, code: str, *, now: int | None = None) -> int | None:
    """Return the matched 30-second counter, within one step of server time."""
    if not _TOTP_CODE.fullmatch(code):
        return None
    current_step = int(time.time() if now is None else now) // TOTP_PERIOD_SECONDS
    totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_PERIOD_SECONDS, digest=hashlib.sha1)
    matches: list[int] = []
    # OWASP recommends the current step and at most one previous step to
    # account for network delay. Accepting future steps can prematurely burn
    # a code and increases the validity window without helping delayed requests.
    for step in range(max(0, current_step - TOTP_WINDOW_STEPS), current_step + 1):
        if step >= 0 and hmac.compare_digest(totp.at(step * TOTP_PERIOD_SECONDS), code):
            matches.append(step)
    # Choosing the oldest matching counter errs toward rejecting ambiguous replay.
    return min(matches) if matches else None


def challenge_hash(challenge: str) -> str:
    return hashlib.sha256(challenge.encode("ascii")).hexdigest()


def new_challenge() -> str:
    return secrets.token_urlsafe(32)


def recovery_code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("ascii")).hexdigest()


def create_recovery_codes() -> list[str]:
    """Generate one-time recovery secrets with 128 bits of entropy each."""
    return [secrets.token_urlsafe(16) for _ in range(RECOVERY_CODE_COUNT)]


def unix_time() -> int:
    return int(time.time())
