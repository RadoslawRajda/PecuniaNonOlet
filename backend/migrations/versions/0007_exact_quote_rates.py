"""Persist exact input rates used to calculate exchange quote payouts."""

import sqlalchemy as sa
from alembic import op

revision = "0007_exact_quote_rates"
down_revision = "0006_audit_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exchange_quotes", sa.Column("source_pln_rate", sa.Text()))
    op.add_column("exchange_quotes", sa.Column("destination_pln_rate", sa.Text()))
    op.add_column("exchange_quotes", sa.Column("rate_table_id", sa.String(64)))


def downgrade() -> None:
    connection = op.get_bind()
    quotes = connection.exec_driver_sql("SELECT count(*) FROM exchange_quotes").scalar_one()
    if quotes:
        raise RuntimeError("Exact quote source rates are audit data and cannot be discarded.")
    op.drop_column("exchange_quotes", "rate_table_id")
    op.drop_column("exchange_quotes", "destination_pln_rate")
    op.drop_column("exchange_quotes", "source_pln_rate")
