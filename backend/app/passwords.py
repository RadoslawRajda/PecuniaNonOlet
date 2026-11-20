"""Password hashing configuration shared by registration and auth services."""

from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hasher.hash("invalid-account-password")
