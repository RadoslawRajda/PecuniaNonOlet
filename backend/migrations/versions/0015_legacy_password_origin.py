"""Record ambiguous legacy passwords for Google-linked accounts."""

import sqlalchemy as sa
from alembic import op

revision = "0015_legacy_password_origin"
down_revision = "0014_security_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_origin", sa.String(24), nullable=False, server_default="local"),
    )
    connection = op.get_bind()
    connection.exec_driver_sql(
        "UPDATE users SET password_origin='google_generated' WHERE has_local_password=0"
    )
    connection.exec_driver_sql(
        """UPDATE users SET password_origin='legacy_unknown'
           WHERE has_local_password=1 AND EXISTS (
               SELECT 1 FROM oauth_identities oi WHERE oi.user_id=users.id AND oi.provider='google'
           )"""
    )


def downgrade() -> None:
    op.drop_column("users", "password_origin")
