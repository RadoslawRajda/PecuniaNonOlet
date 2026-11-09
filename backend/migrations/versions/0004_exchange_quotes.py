"""Persist short-lived exchange quotes and link them to transactions."""

import sqlalchemy as sa
from alembic import op

revision = "0004_exchange_quotes"
down_revision = "0003_initial_balances"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_accounts_identity_currency_quote",
        "accounts",
        ["id", "user_id", "currency_code"],
        unique=True,
    )
    op.create_table(
        "exchange_quotes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_account_id", sa.Integer(), nullable=False),
        sa.Column("destination_account_id", sa.Integer(), nullable=False),
        sa.Column("source_currency_code", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("destination_currency_code", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("source_amount_minor", sa.Integer(), nullable=False),
        sa.Column("destination_amount_minor", sa.Integer(), nullable=False),
        sa.Column("exchange_rate", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("effective_date", sa.String(10), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.Integer()),
        sa.Column("consumed_transaction_id", sa.String(36), sa.ForeignKey("transactions.id"), unique=True),
        sa.ForeignKeyConstraint(
            ["source_account_id", "user_id", "source_currency_code"],
            ["accounts.id", "accounts.user_id", "accounts.currency_code"],
        ),
        sa.ForeignKeyConstraint(
            ["destination_account_id", "user_id", "destination_currency_code"],
            ["accounts.id", "accounts.user_id", "accounts.currency_code"],
        ),
        sa.CheckConstraint("source_account_id <> destination_account_id", name="ck_quotes_distinct_accounts"),
        sa.CheckConstraint("source_currency_code <> destination_currency_code", name="ck_quotes_distinct_currencies"),
        sa.CheckConstraint("source_amount_minor BETWEEN 1 AND 9000000000000000", name="ck_quotes_source_amount"),
        sa.CheckConstraint("destination_amount_minor BETWEEN 1 AND 9000000000000000", name="ck_quotes_destination_amount"),
        sa.CheckConstraint("length(exchange_rate) > 0", name="ck_quotes_rate_nonempty"),
        sa.CheckConstraint("expires_at > created_at", name="ck_quotes_expiry"),
        sa.CheckConstraint(
            "(consumed_at IS NULL AND consumed_transaction_id IS NULL) OR "
            "(consumed_at IS NOT NULL AND consumed_transaction_id IS NOT NULL)",
            name="ck_quotes_consumption_pair",
        ),
    )
    op.create_index("idx_exchange_quotes_user_expiry", "exchange_quotes", ["user_id", "expires_at"])
    op.create_index("idx_exchange_quotes_source", "exchange_quotes", ["source_account_id", "user_id"])
    op.create_index("idx_exchange_quotes_destination", "exchange_quotes", ["destination_account_id", "user_id"])


def downgrade() -> None:
    connection = op.get_bind()
    quotes = connection.exec_driver_sql("SELECT count(*) FROM exchange_quotes").scalar_one()
    if quotes:
        raise RuntimeError("Exchange quote migration is forward-only after quotes have been issued.")
    op.drop_index("idx_exchange_quotes_destination", table_name="exchange_quotes")
    op.drop_index("idx_exchange_quotes_source", table_name="exchange_quotes")
    op.drop_index("idx_exchange_quotes_user_expiry", table_name="exchange_quotes")
    op.drop_table("exchange_quotes")
    op.drop_index("uq_accounts_identity_currency_quote", table_name="accounts")
