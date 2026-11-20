"""Support passwordless identities and stable opaque WebAuthn user handles."""

import secrets

import sqlalchemy as sa
from alembic import op

revision = "0010_auth_identity_hardening"
down_revision = "0009_google_passkeys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    op.add_column("users", sa.Column("webauthn_user_handle", sa.LargeBinary(), nullable=True))
    op.add_column(
        "users",
        sa.Column("has_local_password", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    with op.batch_alter_table("auth_challenges") as batch:
        batch.add_column(sa.Column("session_hash", sa.String(64), nullable=True))
    with op.batch_alter_table("totp_login_challenges") as batch:
        batch.add_column(sa.Column("authenticated_at", sa.Integer(), nullable=True))

    for user in connection.exec_driver_sql("SELECT id FROM users ORDER BY id").mappings():
        user_id = int(user["id"])
        has_passkeys = connection.exec_driver_sql(
            "SELECT 1 FROM passkeys WHERE user_id=? LIMIT 1", (user_id,)
        ).first()
        # Retain the old handle for credentials already registered by earlier clients.
        handle = user_id.to_bytes(8, "big") if has_passkeys else secrets.token_bytes(32)
        connection.exec_driver_sql(
            "UPDATE users SET webauthn_user_handle=? WHERE id=?", (handle, user_id)
        )
    connection.exec_driver_sql(
        "UPDATE totp_login_challenges SET authenticated_at=created_at WHERE authenticated_at IS NULL"
    )
    op.create_index("uq_users_webauthn_user_handle", "users", ["webauthn_user_handle"], unique=True)


def downgrade() -> None:
    connection = op.get_bind()
    if connection.exec_driver_sql("SELECT 1 FROM users WHERE has_local_password=0 LIMIT 1").first():
        raise RuntimeError("Passwordless accounts exist and cannot be downgraded safely.")
    if connection.exec_driver_sql(
        "SELECT 1 FROM auth_challenges WHERE session_hash IS NOT NULL LIMIT 1"
    ).first():
        raise RuntimeError("Session-bound challenges exist and cannot be downgraded safely.")
    op.drop_index("uq_users_webauthn_user_handle", table_name="users")
    with op.batch_alter_table("totp_login_challenges") as batch:
        batch.drop_column("authenticated_at")
    with op.batch_alter_table("auth_challenges") as batch:
        batch.drop_column("session_hash")
    op.drop_column("users", "webauthn_user_handle")
    op.drop_column("users", "has_local_password")
