"""Add persistent rate-limit buckets for authentication endpoints."""

import sqlalchemy as sa
from alembic import op

revision = "0012_auth_rate_limits"
down_revision = "0011_session_auth_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_limits",
        sa.Column("bucket_hash", sa.String(64), primary_key=True),
        sa.Column("window_started_at", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_auth_rate_limits_attempts_nonnegative"),
        sa.CheckConstraint("window_started_at >= 0", name="ck_auth_rate_limits_window_nonnegative"),
    )
    op.create_index("idx_auth_rate_limits_window", "auth_rate_limits", ["window_started_at"])


def downgrade() -> None:
    connection = op.get_bind()
    if connection.exec_driver_sql("SELECT 1 FROM auth_rate_limits LIMIT 1").first():
        raise RuntimeError("Authentication rate-limit data must not be discarded by downgrade.")
    op.drop_index("idx_auth_rate_limits_window", table_name="auth_rate_limits")
    op.drop_table("auth_rate_limits")
