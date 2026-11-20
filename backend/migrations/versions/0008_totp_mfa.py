"""Add encrypted TOTP credentials, one-time login challenges and recovery codes."""

import sqlalchemy as sa
from alembic import op

revision = "0008_totp_mfa"
down_revision = "0007_exact_quote_rates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_totp",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("secret_ciphertext", sa.LargeBinary()),
        sa.Column("pending_secret_ciphertext", sa.LargeBinary()),
        sa.Column("pending_expires_at", sa.Integer()),
        sa.Column("enabled_at", sa.Integer()),
        sa.Column("last_used_step", sa.Integer(), nullable=False, server_default="-1"),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_window_started_at", sa.Integer()),
        sa.Column("locked_until", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("failed_attempts >= 0", name="ck_user_totp_failed_attempts_nonnegative"),
        sa.CheckConstraint("locked_until >= 0", name="ck_user_totp_locked_until_nonnegative"),
        sa.CheckConstraint(
            "(enabled_at IS NULL AND secret_ciphertext IS NULL) OR "
            "(enabled_at IS NOT NULL AND secret_ciphertext IS NOT NULL)",
            name="ck_user_totp_enabled_has_secret",
        ),
        sa.CheckConstraint(
            "(pending_secret_ciphertext IS NULL AND pending_expires_at IS NULL) OR "
            "(pending_secret_ciphertext IS NOT NULL AND pending_expires_at IS NOT NULL)",
            name="ck_user_totp_pending_has_expiry",
        ),
    )
    op.create_table(
        "totp_login_challenges",
        sa.Column("challenge_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("attempts >= 0", name="ck_totp_challenge_attempts_nonnegative"),
    )
    op.create_index("idx_totp_challenges_user_expiry", "totp_login_challenges", ["user_id", "expires_at"])
    op.create_table(
        "totp_recovery_codes",
        sa.Column("code_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
    )
    op.create_index("idx_totp_recovery_user", "totp_recovery_codes", ["user_id"])


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("totp_recovery_codes", "totp_login_challenges", "user_totp"):
        if connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one():
            raise RuntimeError("TOTP credentials or recovery data must not be discarded by downgrade.")
    op.drop_index("idx_totp_recovery_user", table_name="totp_recovery_codes")
    op.drop_table("totp_recovery_codes")
    op.drop_index("idx_totp_challenges_user_expiry", table_name="totp_login_challenges")
    op.drop_table("totp_login_challenges")
    op.drop_table("user_totp")
