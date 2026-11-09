import sqlite3

import pytest

from app.database import migrate_database


@pytest.fixture
def database_path(tmp_path, monkeypatch):
    path = tmp_path / "migration.db"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    return path


def test_migrates_empty_database(database_path):
    migrate_database()
    with sqlite3.connect(database_path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"users", "sessions", "currencies", "accounts", "transactions", "ledger_entries", "exchange_rate_snapshots", "alembic_version"} <= tables
        assert db.execute("SELECT code FROM currencies ORDER BY code").fetchall() == [
            ("CZK",), ("EUR",), ("GBP",), ("PLN",), ("USD",)
        ]


def test_migrates_existing_users_and_active_sessions_without_loss(database_path):
    with sqlite3.connect(database_path) as db:
        db.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            );
            INSERT INTO users VALUES (41, 'old@example.com', 'argon2-hash', 123456);
            INSERT INTO sessions VALUES ('saved-token-hash', 41, 9876543210);
            """
        )

    migrate_database()

    with sqlite3.connect(database_path) as db:
        assert db.execute("SELECT id, email, password_hash, created_at FROM users").fetchall() == [
            (41, "old@example.com", "argon2-hash", 123456)
        ]
        assert db.execute("SELECT token_hash, user_id, expires_at FROM sessions").fetchall() == [
            ("saved-token-hash", 41, 9876543210)
        ]
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0002_user_roles",)
        assert db.execute("SELECT role_name FROM user_roles WHERE user_id = 41").fetchone() == ("user",)


def test_migration_is_repeatable_and_preserves_financial_data(database_path):
    migrate_database()
    with sqlite3.connect(database_path) as db:
        db.execute("INSERT INTO users(email, password_hash, created_at) VALUES (?, ?, ?)", ("repeat@example.com", "hash", 1))
        user_id = db.execute("SELECT id FROM users WHERE email = ?", ("repeat@example.com",)).fetchone()[0]
        db.execute("INSERT INTO accounts(user_id, currency_code, balance_minor) VALUES (?, 'PLN', 100000)", (user_id,))
    migrate_database()
    with sqlite3.connect(database_path) as db:
        assert db.execute("SELECT balance_minor FROM accounts WHERE user_id = ?", (user_id,)).fetchone() == (100000,)


def test_constraints_reject_duplicate_accounts_negative_balance_and_unknown_currency(database_path):
    migrate_database()
    with sqlite3.connect(database_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("INSERT INTO users(email, password_hash, created_at) VALUES ('owner@example.com', 'hash', 1)")
        user_id = db.execute("SELECT id FROM users").fetchone()[0]
        db.execute("INSERT INTO accounts(user_id, currency_code, balance_minor) VALUES (?, 'PLN', 0)", (user_id,))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO accounts(user_id, currency_code, balance_minor) VALUES (?, 'PLN', 0)", (user_id,))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO accounts(user_id, currency_code, balance_minor) VALUES (?, 'EUR', -1)", (user_id,))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO accounts(user_id, currency_code, balance_minor) VALUES (?, 'ABC', 0)", (user_id,))


def test_foreign_keys_prevent_orphan_sessions_accounts_and_entries(database_path):
    migrate_database()
    with sqlite3.connect(database_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO sessions(token_hash, user_id, expires_at) VALUES ('orphan', 999, 1)")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO accounts(user_id, currency_code) VALUES (999, 'PLN')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO ledger_entries(transaction_id, account_id, account_user_id, amount_minor, created_at) VALUES ('missing', 1, 1, 10, 1)")
