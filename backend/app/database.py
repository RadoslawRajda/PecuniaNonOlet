"""SQLite connection and schema migration configuration."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

SQLITE_BUSY_TIMEOUT_MS = 5000


def database_path() -> Path:
    return Path(os.getenv("DATABASE_PATH", "data/pecunia.db"))


def connect_db() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    return db


def migrate_database() -> None:
    path = database_path().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(config_path))
    url = f"sqlite:///{path.as_posix()}".replace("%", "%%")
    config.set_main_option("sqlalchemy.url", url)
    config.set_main_option("script_location", str(config_path.parent / "migrations"))
    command.upgrade(config, "head")
