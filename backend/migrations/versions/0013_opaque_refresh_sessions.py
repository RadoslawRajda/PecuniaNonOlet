"""Replace long-lived bearer sessions with rotating opaque token sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0013_opaque_refresh_sessions"
down_revision = "0012_auth_rate_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing sessions contain only hashes of the old seven-day token. They cannot
    # be upgraded into refresh sessions without the raw token, so require sign-in
    # once after deployment and remove the obsolete session table.
    op.drop_table("sessions")

    op.create_table(
        "auth_sessions",
        sa.Column("session_id", sa.String(43), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("access_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("access_expires_at", sa.Integer(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("refresh_expires_at", sa.Integer(), nullable=False),
        sa.Column("absolute_expires_at", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("authenticated_at", sa.Integer(), nullable=False),
        sa.Column("authentication_method", sa.String(16), nullable=False),
        sa.Column("provider_authenticated_at", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "authentication_method IN ('legacy','password','google','passkey')",
            name="ck_auth_sessions_authentication_method",
        ),
        sa.CheckConstraint(
            "authentication_method = 'google' OR provider_authenticated_at IS NULL",
            name="ck_auth_sessions_provider_auth_time_method",
        ),
        sa.CheckConstraint(
            "access_expires_at <= refresh_expires_at "
            "AND refresh_expires_at <= absolute_expires_at",
            name="ck_auth_sessions_expiry_order",
        ),
    )
    op.create_index("idx_auth_sessions_user_created", "auth_sessions", ["user_id", "created_at"])
    op.create_index("idx_auth_sessions_refresh_expiry", "auth_sessions", ["refresh_expires_at"])

    op.create_table(
        "consumed_refresh_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(43),
            sa.ForeignKey("auth_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("consumed_at", sa.Integer(), nullable=False),
    )
    op.create_index(
        "idx_consumed_refresh_tokens_session",
        "consumed_refresh_tokens",
        ["session_id", "consumed_at"],
    )


def downgrade() -> None:
    op.drop_table("consumed_refresh_tokens")
    op.drop_table("auth_sessions")

    # Sessions revoked by the upgrade are intentionally not restored.
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.Text(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("authenticated_at", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "authentication_method", sa.String(16), nullable=False, server_default="legacy"
        ),
        sa.Column("provider_authenticated_at", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "authentication_method IN ('legacy','password','google','passkey')",
            name="ck_sessions_authentication_method",
        ),
        sa.CheckConstraint(
            "authentication_method = 'google' OR provider_authenticated_at IS NULL",
            name="ck_sessions_provider_auth_time_method",
        ),
    )
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"])
    op.create_index("idx_sessions_expires_at", "sessions", ["expires_at"])
