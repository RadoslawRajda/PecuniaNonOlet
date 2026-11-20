import pytest
from app.password_policy import validate_password
from app.schemas import ChangePasswordRequest, RegisterCredentials
from pydantic import ValidationError


def test_password_policy_rejects_common_passwords_and_simple_variants():
    for password in ("password", "Password!", "P@ssword"):
        with pytest.raises(ValueError, match="popularne|wyciekłych"):
            validate_password(password)


def test_registration_rejects_context_words_and_email_name():
    with pytest.raises(ValidationError, match="nazwy aplikacji"):
        RegisterCredentials(email="person@example.com", password="Pecunia2026!")
    with pytest.raises(ValidationError, match="loginu"):
        RegisterCredentials(email="violet@example.com", password="Violet-bridge-2026!")


def test_password_change_applies_common_password_policy():
    with pytest.raises(ValidationError, match="popularne|wyciekłych"):
        ChangePasswordRequest(new_password="Password!")


def test_long_password_is_permitted_and_checked_locally():
    password = "violet-bridge-2026-with-a-long-unique-passphrase-r7Kp!x9Qm!z7Pq2"
    assert len(password) >= 64
    assert RegisterCredentials(email="person@example.com", password=password).password == password
