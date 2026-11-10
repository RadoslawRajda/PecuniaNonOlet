from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, event, pool

config = context.config
database_path = Path(os.getenv("DATABASE_PATH", "data/pecunia.db")).resolve()
database_path.parent.mkdir(parents=True, exist_ok=True)
config.set_main_option(
    "sqlalchemy.url", f"sqlite:///{database_path.as_posix()}".replace("%", "%%")
)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
        connect_args={"timeout": 10},
    )

    @event.listens_for(connectable, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        # Disable sqlite3's legacy implicit transaction handling so Alembic's
        # transaction includes DDL as well as data changes.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    @event.listens_for(connectable, "begin")
    def begin_immediate(connection) -> None:
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            render_as_batch=True,
            transactional_ddl=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
