"""Bind new audit events to authenticated principals while preserving declarations."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0016_authenticated_audit_actors"
down_revision = "0015_identity_roles"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "audit_events",
        sa.Column("actor_principal_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("actor_display_name", sa.String(200), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("declared_actor_name", sa.String(120), nullable=True),
    )
    op.create_foreign_key(
        "fk_audit_events_actor_principal",
        "audit_events",
        "security_principals",
        ["actor_principal_id"],
        ["id"],
    )
    op.create_index(
        "ix_audit_events_actor_principal_id",
        "audit_events",
        ["actor_principal_id"],
    )


def downgrade():
    op.drop_index("ix_audit_events_actor_principal_id", table_name="audit_events")
    op.drop_constraint(
        "fk_audit_events_actor_principal", "audit_events", type_="foreignkey"
    )
    op.drop_column("audit_events", "declared_actor_name")
    op.drop_column("audit_events", "actor_display_name")
    op.drop_column("audit_events", "actor_principal_id")
