"""Add currency accounts and financial ledger."""

import sqlalchemy as sa
from alembic import op

revision = "0001_currency_accounts"
down_revision = None
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing = _table_names()
    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("email", sa.Text(), nullable=False, unique=True),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Integer(), nullable=False),
        )
    if "sessions" not in existing:
        op.create_table(
            "sessions",
            sa.Column("token_hash", sa.Text(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("expires_at", sa.Integer(), nullable=False),
        )
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)")

    if "currencies" not in existing:
        op.create_table(
            "currencies",
            sa.Column("code", sa.String(3), primary_key=True),
            sa.Column("minor_unit", sa.Integer(), nullable=False),
            sa.CheckConstraint("length(code) = 3", name="ck_currencies_code_length"),
            sa.CheckConstraint("minor_unit BETWEEN 0 AND 3", name="ck_currencies_minor_unit"),
        )
    # Idempotent to recover a database left with just this table by an older,
    # non-transactional SQLite migration attempt.
    op.get_bind().exec_driver_sql(
        """INSERT OR IGNORE INTO currencies(code, minor_unit) VALUES
           ('PLN', 2), ('EUR', 2), ('USD', 2), ('GBP', 2), ('CZK', 2)"""
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("currency_code", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("balance_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "currency_code", name="uq_accounts_user_currency"),
        sa.UniqueConstraint("id", "user_id", name="uq_accounts_id_user"),
        sa.CheckConstraint("balance_minor >= 0 AND balance_minor <= 9000000000000000", name="ck_accounts_balance_range"),
    )
    op.create_index("idx_accounts_user_id", "accounts", ["user_id"])
    op.create_table(
        "transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="completed"),
        sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("source_account_id", sa.Integer()),
        sa.Column("source_account_user_id", sa.Integer()),
        sa.Column("destination_account_id", sa.Integer()),
        sa.Column("destination_account_user_id", sa.Integer()),
        sa.Column("source_currency_code", sa.String(3), sa.ForeignKey("currencies.code")),
        sa.Column("destination_currency_code", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("source_amount_minor", sa.Integer()),
        sa.Column("destination_amount_minor", sa.Integer(), nullable=False),
        sa.Column("exchange_rate", sa.Text()),
        sa.Column("provider", sa.Text()),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["source_account_id", "source_account_user_id"], ["accounts.id", "accounts.user_id"]),
        sa.ForeignKeyConstraint(["destination_account_id", "destination_account_user_id"], ["accounts.id", "accounts.user_id"]),
        sa.UniqueConstraint("sender_user_id", "idempotency_key", name="uq_transactions_sender_idempotency"),
        sa.CheckConstraint("kind IN ('opening', 'transfer', 'exchange')", name="ck_transactions_kind"),
        sa.CheckConstraint("status IN ('completed', 'reversed')", name="ck_transactions_status"),
        sa.CheckConstraint("destination_amount_minor > 0 AND destination_amount_minor <= 9000000000000000", name="ck_transactions_destination_amount"),
        sa.CheckConstraint("source_amount_minor IS NULL OR (source_amount_minor > 0 AND source_amount_minor <= 9000000000000000)", name="ck_transactions_source_amount"),
        sa.CheckConstraint("(kind = 'opening' AND source_account_id IS NULL AND source_account_user_id IS NULL AND destination_account_id IS NOT NULL AND destination_account_user_id = sender_user_id AND source_amount_minor IS NULL AND recipient_user_id IS NULL AND source_currency_code IS NULL AND exchange_rate IS NULL) OR (kind = 'transfer' AND source_account_id IS NOT NULL AND source_account_user_id = sender_user_id AND destination_account_id IS NOT NULL AND recipient_user_id = destination_account_user_id AND source_amount_minor IS NOT NULL AND exchange_rate IS NULL AND source_currency_code = destination_currency_code) OR (kind = 'exchange' AND source_account_id IS NOT NULL AND source_account_user_id = sender_user_id AND destination_account_id IS NOT NULL AND destination_account_user_id = sender_user_id AND source_amount_minor IS NOT NULL AND recipient_user_id IS NULL AND exchange_rate IS NOT NULL AND source_currency_code <> destination_currency_code)", name="ck_transactions_shape"),
    )
    op.create_index("idx_transactions_sender_created", "transactions", ["sender_user_id", "created_at", "id"])
    op.create_index("idx_transactions_recipient_created", "transactions", ["recipient_user_id", "created_at", "id"])
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("account_user_id", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["account_id", "account_user_id"], ["accounts.id", "accounts.user_id"]),
        sa.UniqueConstraint("transaction_id", "account_id", name="uq_ledger_transaction_account"),
        sa.CheckConstraint("amount_minor <> 0 AND amount_minor BETWEEN -9000000000000000 AND 9000000000000000", name="ck_ledger_amount_range"),
    )
    op.create_index("idx_ledger_account_created", "ledger_entries", ["account_id", "created_at", "id"])
    op.create_table(
        "exchange_rate_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("base_currency_code", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("quote_currency_code", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("rate", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("base_currency_code <> quote_currency_code", name="ck_rates_distinct_currencies"),
        sa.CheckConstraint("length(rate) > 0", name="ck_rates_nonempty"),
        sa.CheckConstraint("expires_at > fetched_at", name="ck_rates_expiry"),
    )
    op.create_index("idx_rates_pair_expiry", "exchange_rate_snapshots", ["base_currency_code", "quote_currency_code", "expires_at"])


def downgrade() -> None:
    op.drop_index("idx_rates_pair_expiry", table_name="exchange_rate_snapshots")
    op.drop_table("exchange_rate_snapshots")
    op.drop_index("idx_ledger_account_created", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_index("idx_transactions_recipient_created", table_name="transactions")
    op.drop_index("idx_transactions_sender_created", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("idx_accounts_user_id", table_name="accounts")
    op.drop_table("accounts")
    op.drop_table("currencies")
