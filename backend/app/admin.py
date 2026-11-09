"""Trusted local administrative operations for account provisioning."""

from __future__ import annotations

import argparse
import getpass
import sqlite3
import time
from contextlib import closing

from pwdlib import PasswordHash
from pydantic import ValidationError

from app.database import connect_db, migrate_database
from app.schemas import RegisterCredentials


def create_analyst(email: str, password: str) -> int:
    credentials = RegisterCredentials(email=email, password=password)
    password_hash = PasswordHash.recommended().hash(credentials.password)
    migrate_database()
    with closing(connect_db()) as db:
        try:
            with db:
                cursor = db.execute(
                    "INSERT INTO users(email, password_hash, created_at) VALUES (?, ?, ?)",
                    (credentials.email, password_hash, int(time.time())),
                )
                user_id = int(cursor.lastrowid)
                db.execute(
                    "INSERT INTO user_roles(user_id, role_name) VALUES (?, 'analyst')",
                    (user_id,),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Konto o podanym adresie e-mail już istnieje.") from exc
    return user_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Lokalne operacje administracyjne backendu.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyst_parser = subparsers.add_parser("create-analyst", help="Utwórz konto analityka")
    analyst_parser.add_argument("email")
    args = parser.parse_args()

    password = getpass.getpass("Hasło analityka (min. 8 znaków): ")
    confirmation = getpass.getpass("Powtórz hasło: ")
    if password != confirmation:
        parser.error("Hasła nie są zgodne.")
    try:
        user_id = create_analyst(args.email, password)
    except ValidationError:
        parser.error("Nieprawidłowy adres e-mail lub hasło (hasło musi mieć co najmniej 8 znaków).")
    except ValueError as exc:
        parser.error(str(exc))
    except sqlite3.Error:
        parser.error("Nie udało się utworzyć konta.")
    print(f"Utworzono konto analityka (ID: {user_id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
