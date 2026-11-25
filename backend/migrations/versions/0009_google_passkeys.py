"""Add Google identities, one-time auth challenges and WebAuthn credentials."""

import sqlalchemy as sa
from alembic import op

revision = "0009_google_passkeys"
down_revision = "0008_totp_mfa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("authenticated_at", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "oauth_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("issuer", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("email_at_link", sa.String(320), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("provider", "issuer", "subject", name="uq_oauth_provider_subject"),
        sa.UniqueConstraint("user_id", "provider", name="uq_oauth_user_provider"),
    )
    op.create_table(
        "passkeys",
        sa.Column("credential_id", sa.String(1024), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("transports", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.Integer()),
        sa.CheckConstraint("sign_count >= 0", name="ck_passkeys_sign_count_nonnegative"),
    )
    op.create_index("idx_passkeys_user", "passkeys", ["user_id"])
    op.create_table(
        "auth_challenges",
        sa.Column("challenge_hash", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("challenge_value", sa.String(128), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("attempts BETWEEN 0 AND 5", name="ck_auth_challenge_attempts"),
    )
    op.create_index("idx_auth_challenges_expiry", "auth_challenges", ["expires_at"])


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("passkeys", "oauth_identities", "auth_challenges"):
        if connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one():
            raise RuntimeError(f"{table} contains authentication data and cannot be discarded.")
    op.drop_index("idx_auth_challenges_expiry", table_name="auth_challenges")
    op.drop_table("auth_challenges")
    op.drop_index("idx_passkeys_user", table_name="passkeys")
    op.drop_table("passkeys")
    op.drop_table("oauth_identities")
    op.drop_column("sessions", "authenticated_at")
