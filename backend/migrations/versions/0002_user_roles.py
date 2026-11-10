"""Add user and analyst roles."""

import sqlalchemy as sa
from alembic import op

revision = "0002_user_roles"
down_revision = "0001_currency_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("name", sa.String(32), primary_key=True),
        sa.CheckConstraint("name IN ('user', 'analyst')", name="ck_roles_name"),
    )
    op.bulk_insert(
        sa.table("roles", sa.column("name", sa.String)),
        [{"name": "user"}, {"name": "analyst"}],
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_name", sa.String(32), sa.ForeignKey("roles.name"), nullable=False),
    )
    op.create_index("idx_user_roles_role_name", "user_roles", ["role_name"])
    op.execute("INSERT INTO user_roles(user_id, role_name) SELECT id, 'user' FROM users")


def downgrade() -> None:
    op.drop_index("idx_user_roles_role_name", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_table("roles")
