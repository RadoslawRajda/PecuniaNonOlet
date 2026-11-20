"""Record the authentication method and upstream authentication time on sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0011_session_auth_context"
down_revision = "0010_auth_identity_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(
            sa.Column(
                "authentication_method", sa.String(16), nullable=False, server_default="legacy"
            )
        )
        batch.add_column(sa.Column("provider_authenticated_at", sa.Integer(), nullable=True))
        batch.create_check_constraint(
            "ck_sessions_authentication_method",
            "authentication_method IN ('legacy','password','google','passkey')",
        )
        batch.create_check_constraint(
            "ck_sessions_provider_auth_time_method",
            "authentication_method = 'google' OR provider_authenticated_at IS NULL",
        )

    with op.batch_alter_table("totp_login_challenges") as batch:
        batch.add_column(
            sa.Column(
                "authentication_method", sa.String(16), nullable=False, server_default="legacy"
            )
        )
        batch.add_column(sa.Column("provider_authenticated_at", sa.Integer(), nullable=True))
        batch.create_check_constraint(
            "ck_totp_challenges_authentication_method",
            "authentication_method IN ('legacy','password','google','passkey')",
        )
        batch.create_check_constraint(
            "ck_totp_challenges_provider_auth_time_method",
            "authentication_method = 'google' OR provider_authenticated_at IS NULL",
        )

    # Pending challenges predate the stored proof context. Force those few-minute
    # login flows to restart rather than issue an ambiguously classified session.
    op.execute("DELETE FROM totp_login_challenges")


def downgrade() -> None:
    connection = op.get_bind()
    if connection.exec_driver_sql(
        "SELECT 1 FROM sessions WHERE authentication_method != 'legacy' LIMIT 1"
    ).first():
        raise RuntimeError("Authentication method data must not be discarded by downgrade.")
    if connection.exec_driver_sql(
        "SELECT 1 FROM totp_login_challenges WHERE authentication_method != 'legacy' LIMIT 1"
    ).first():
        raise RuntimeError("MFA challenge authentication data must not be discarded by downgrade.")

    with op.batch_alter_table("totp_login_challenges") as batch:
        batch.drop_constraint("ck_totp_challenges_provider_auth_time_method", type_="check")
        batch.drop_constraint("ck_totp_challenges_authentication_method", type_="check")
        batch.drop_column("provider_authenticated_at")
        batch.drop_column("authentication_method")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_constraint("ck_sessions_provider_auth_time_method", type_="check")
        batch.drop_constraint("ck_sessions_authentication_method", type_="check")
        batch.drop_column("provider_authenticated_at")
        batch.drop_column("authentication_method")
