"""append-only domain audit events

Revision ID: 0010_append_only_audit_events
Revises: 0009_production_traceability
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010_append_only_audit_events"
down_revision = "0009_production_traceability"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_no", sa.String(50), nullable=False, unique=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("entity_ref", sa.String(120), nullable=False),
        sa.Column("actor_name", sa.String(120), nullable=False),
        sa.Column("summary", sa.String(240), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column(
            "payload_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"])
    op.create_index(
        "ix_audit_events_entity", "audit_events", ["entity_type", "entity_ref"]
    )
    op.execute(
        """
        CREATE FUNCTION slc_prevent_audit_event_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION slc_prevent_audit_event_mutation()
        """
    )


def downgrade():
    op.execute("DROP TRIGGER trg_audit_events_append_only ON audit_events")
    op.drop_table("audit_events")
    op.execute("DROP FUNCTION slc_prevent_audit_event_mutation()")
