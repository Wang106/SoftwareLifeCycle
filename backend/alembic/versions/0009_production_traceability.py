"""production site deployment changeover and batch traceability

Revision ID: 0009_production_traceability
Revises: 0008_authorization_distribution_link
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009_production_traceability"
down_revision = "0008_authorization_distribution_link"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("software_authorizations", sa.Column("batch_limit", sa.Integer()))

    op.create_table(
        "manufacturing_sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("site_code", sa.String(80), nullable=False, unique=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("region", sa.String(100)),
        sa.Column("status", sa.String(30), nullable=False),
    )
    op.create_index("ix_manufacturing_sites_customer_id", "manufacturing_sites", ["customer_id"])
    op.create_index("ix_manufacturing_sites_project_id", "manufacturing_sites", ["project_id"])

    op.create_table(
        "production_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("manufacturing_sites.id"), nullable=False),
        sa.Column("line_code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.UniqueConstraint("site_id", "line_code", name="uq_production_line_site_code"),
    )
    op.create_index("ix_production_lines_site_id", "production_lines", ["site_id"])

    op.create_table(
        "deployments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("deployment_no", sa.String(50), nullable=False, unique=True),
        sa.Column("authorization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("software_authorizations.id"), nullable=False),
        sa.Column("production_line_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("production_lines.id"), nullable=False),
        sa.Column("expected_release_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("releases.id"), nullable=False),
        sa.Column("expected_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("release_snapshots.id"), nullable=False),
        sa.Column("actual_release_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("releases.id")),
        sa.Column("actual_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("release_snapshots.id")),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("deployed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_deployments_authorization_id", "deployments", ["authorization_id"])
    op.create_index("ix_deployments_production_line_id", "deployments", ["production_line_id"])

    op.create_table(
        "software_changeovers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("changeover_no", sa.String(50), nullable=False, unique=True),
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("deployments.id"), nullable=False),
        sa.Column("authorization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("software_authorizations.id"), nullable=False),
        sa.Column("from_release_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("releases.id"), nullable=False),
        sa.Column("to_release_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("releases.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text()),
    )
    op.create_index("ix_software_changeovers_deployment_id", "software_changeovers", ["deployment_id"])

    op.create_table(
        "production_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_no", sa.String(80), nullable=False, unique=True),
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("deployments.id"), nullable=False),
        sa.Column("changeover_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("software_changeovers.id")),
        sa.Column("authorization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("software_authorizations.id"), nullable=False),
        sa.Column("release_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("releases.id"), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("release_snapshots.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text()),
    )
    op.create_index("ix_production_batches_deployment_id", "production_batches", ["deployment_id"])


def downgrade():
    op.drop_index("ix_production_batches_deployment_id", table_name="production_batches")
    op.drop_table("production_batches")
    op.drop_index("ix_software_changeovers_deployment_id", table_name="software_changeovers")
    op.drop_table("software_changeovers")
    op.drop_index("ix_deployments_production_line_id", table_name="deployments")
    op.drop_index("ix_deployments_authorization_id", table_name="deployments")
    op.drop_table("deployments")
    op.drop_index("ix_production_lines_site_id", table_name="production_lines")
    op.drop_table("production_lines")
    op.drop_index("ix_manufacturing_sites_project_id", table_name="manufacturing_sites")
    op.drop_index("ix_manufacturing_sites_customer_id", table_name="manufacturing_sites")
    op.drop_table("manufacturing_sites")
    op.drop_column("software_authorizations", "batch_limit")
