"""Add append-only security event records for authentication and access failures."""

import sqlalchemy as sa
from alembic import op

revision = "0014_security_events"
down_revision = "0013_opaque_refresh_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("authentication_method", sa.String(16), nullable=False),
        sa.Column("endpoint", sa.String(128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('authentication','authorization','session','credential_change')",
            name="ck_security_events_type",
        ),
        sa.CheckConstraint(
            "outcome IN ('success','failure','challenge')",
            name="ck_security_events_outcome",
        ),
        sa.CheckConstraint(
            "authentication_method IN ('password','totp','google','passkey','refresh','bearer')",
            name="ck_security_events_authentication_method",
        ),
        sa.CheckConstraint(
            "length(endpoint) BETWEEN 1 AND 128", name="ck_security_events_endpoint"
        ),
    )
    op.create_index("idx_security_events_time", "security_events", ["occurred_at"])
    op.create_index("idx_security_events_user_time", "security_events", ["user_id", "occurred_at"])
    op.execute(
        "CREATE TRIGGER trg_security_events_no_update BEFORE UPDATE ON security_events "
        "BEGIN SELECT RAISE(ABORT, 'security events are append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_security_events_no_delete BEFORE DELETE ON security_events "
        "BEGIN SELECT RAISE(ABORT, 'security events are append-only'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_security_events_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_security_events_no_update")
    op.drop_table("security_events")
