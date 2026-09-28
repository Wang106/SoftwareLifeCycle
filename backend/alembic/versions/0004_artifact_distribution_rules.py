"""artifact distribution rules"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_artifact_distribution_rules"
down_revision = "0003_policy_exception"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "artifact_distribution_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifacts.id"), nullable=False),
        sa.Column("recipient_type", sa.String(50), nullable=False),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("recipient_code", sa.String(80)),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint(
            "artifact_id", "recipient_type", "purpose", "recipient_code",
            name="uq_artifact_recipient_purpose_code"
        ),
    )
    op.create_index("ix_artifact_distribution_rules_artifact_id", "artifact_distribution_rules", ["artifact_id"])

def downgrade():
    op.drop_index("ix_artifact_distribution_rules_artifact_id", table_name="artifact_distribution_rules")
    op.drop_table("artifact_distribution_rules")
