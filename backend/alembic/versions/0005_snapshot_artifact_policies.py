"""snapshot artifact distribution policies"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_snapshot_artifact_policies"
down_revision = "0004_artifact_distribution_rules"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "snapshot_artifact_distribution_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snapshot_artifacts.id"), nullable=False),
        sa.Column("recipient_type", sa.String(50), nullable=False),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("recipient_code", sa.String(80)),
        sa.UniqueConstraint("snapshot_artifact_id","recipient_type","purpose","recipient_code",name="uq_snapshot_artifact_policy"),
    )
    op.create_index("ix_snapshot_artifact_distribution_rules_snapshot_artifact_id","snapshot_artifact_distribution_rules",["snapshot_artifact_id"])

def downgrade():
    op.drop_index("ix_snapshot_artifact_distribution_rules_snapshot_artifact_id",table_name="snapshot_artifact_distribution_rules")
    op.drop_table("snapshot_artifact_distribution_rules")
