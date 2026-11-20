"""Local, privacy-preserving checks for common and context-specific passwords."""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

COMMON_PASSWORDS_PATH = Path(__file__).resolve().parent / "resources" / "common-passwords.txt"
CONTEXT_WORDS = (
    "pecunia",
    "pecunianonolet",
    "nonolet",
    "pecunianonoletlocal",
    "analyst",
)


def _normalize(value: str) -> str:
    normalized = (
        unicodedata.normalize("NFKC", value)
        .casefold()
        .translate(
            str.maketrans(
                {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
            )
        )
    )
    return "".join(character for character in normalized if character.isalnum())


@lru_cache(maxsize=1)
def _common_passwords() -> frozenset[str]:
    with COMMON_PASSWORDS_PATH.open(encoding="utf-8") as wordlist:
        return frozenset(
            normalized for line in wordlist if (normalized := _normalize(line.strip()))
        )


def validate_password(password: str, *, email: str | None = None) -> None:
    """Reject passwords found in the bundled common list or naming this app/user."""
    candidate = _normalize(password)
    if candidate in _common_passwords():
        raise ValueError("Hasło jest zbyt popularne lub znajduje się na liście haseł wyciekłych.")

    contextual_terms = set(CONTEXT_WORDS)
    if email:
        email_name = email.partition("@")[0]
        normalized_email = _normalize(email_name)
        if len(normalized_email) >= 3:
            contextual_terms.add(normalized_email)

    if any(term in candidate for term in contextual_terms):
        raise ValueError("Hasło nie może zawierać nazwy aplikacji, roli ani loginu.")
