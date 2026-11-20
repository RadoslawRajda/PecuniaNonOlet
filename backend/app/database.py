"""SQLite connection and schema migration configuration."""

from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import Settings, load_settings

SQLITE_BUSY_TIMEOUT_MS = 5000


def _prepare_database_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError("DATABASE_PATH must not be a symbolic link")
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    except FileExistsError:
        if not path.is_file():
            raise ValueError("DATABASE_PATH must point to a regular file")
    else:
        os.close(descriptor)
    if os.name != "nt":
        os.chmod(path, 0o600)
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("DATABASE_PATH must point to a regular file")


def database_path() -> Path:
    return load_settings().database_path


def connect_db(settings: Settings | None = None) -> sqlite3.Connection:
    path = settings.database_path if settings is not None else database_path()
    _prepare_database_file(path)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    return db


def migrate_database(settings: Settings | None = None) -> None:
    configured_path = settings.database_path if settings is not None else database_path()
    path = configured_path.expanduser().absolute()
    _prepare_database_file(path)
    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(config_path))
    url = f"sqlite:///{path.as_posix()}".replace("%", "%%")
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["database_path"] = path
    config.set_main_option("script_location", str(config_path.parent / "migrations"))
    command.upgrade(config, "head")
