"""Store private profile photo metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0005_profile_photos"
down_revision = "0004_exchange_quotes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_photos",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("storage_key", sa.String(36), nullable=False, unique=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("length(storage_key) = 36", name="ck_profile_photos_storage_key_length"),
        sa.CheckConstraint("size_bytes BETWEEN 1 AND 2097152", name="ck_profile_photos_size"),
    )
    op.create_index("idx_profile_photos_updated_at", "profile_photos", ["updated_at"])


def downgrade() -> None:
    connection = op.get_bind()
    if connection.exec_driver_sql("SELECT count(*) FROM profile_photos").scalar_one():
        raise RuntimeError("Profile photo migration is forward-only while user photos exist.")
    op.drop_index("idx_profile_photos_updated_at", table_name="profile_photos")
    op.drop_table("profile_photos")
