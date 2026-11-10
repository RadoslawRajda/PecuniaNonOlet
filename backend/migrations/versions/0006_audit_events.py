"""Add append-only financial and administrative audit events."""

import sqlalchemy as sa
from alembic import op

revision = "0006_audit_events"
down_revision = "0005_profile_photos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(128), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("length(actor_role) BETWEEN 1 AND 32", name="ck_audit_actor_role_length"),
        sa.CheckConstraint("length(action) BETWEEN 1 AND 64", name="ck_audit_action_length"),
        sa.CheckConstraint("length(entity_type) BETWEEN 1 AND 32", name="ck_audit_entity_type_length"),
        sa.CheckConstraint("length(entity_id) BETWEEN 1 AND 128", name="ck_audit_entity_id_length"),
        sa.CheckConstraint("json_valid(details_json)", name="ck_audit_details_json"),
    )
    op.create_index("idx_audit_events_created", "audit_events", ["created_at", "id"])
    op.create_index("idx_audit_events_actor_created", "audit_events", ["actor_user_id", "created_at", "id"])
    op.create_index("idx_audit_events_action_created", "audit_events", ["action", "created_at", "id"])
    op.execute(
        """CREATE TRIGGER audit_events_no_update
           BEFORE UPDATE ON audit_events
           BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END"""
    )
    op.execute(
        """CREATE TRIGGER audit_events_no_delete
           BEFORE DELETE ON audit_events
           BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END"""
    )
    # Preserve a basic audit trail for financial operations created before this release.
    op.execute(
        """INSERT INTO audit_events(
               actor_user_id, actor_role, action, entity_type, entity_id, details_json, created_at
           )
           SELECT t.sender_user_id, COALESCE(r.role_name, 'user'), 'financial.transaction_recorded',
                  'transaction', t.id,
                  json_object('kind', t.kind, 'status', t.status,
                              'source_currency_code', t.source_currency_code,
                              'source_amount_minor', t.source_amount_minor,
                              'destination_currency_code', t.destination_currency_code,
                              'destination_amount_minor', t.destination_amount_minor,
                              'recipient_user_id', t.recipient_user_id),
                  t.created_at
           FROM transactions AS t
           LEFT JOIN user_roles AS r ON r.user_id = t.sender_user_id
           ORDER BY t.created_at, t.id"""
    )


def downgrade() -> None:
    count = op.get_bind().exec_driver_sql("SELECT count(*) FROM audit_events").scalar_one()
    if count:
        raise RuntimeError("Audit history is append-only and cannot be discarded by downgrade.")
    op.execute("DROP TRIGGER audit_events_no_delete")
    op.execute("DROP TRIGGER audit_events_no_update")
    op.drop_index("idx_audit_events_action_created", table_name="audit_events")
    op.drop_index("idx_audit_events_actor_created", table_name="audit_events")
    op.drop_index("idx_audit_events_created", table_name="audit_events")
    op.drop_table("audit_events")
