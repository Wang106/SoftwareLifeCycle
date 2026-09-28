"""policy exceptions bound to snapshots"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_policy_exception"
down_revision = "0002_change_testing"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "policy_exceptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exception_no", sa.String(50), nullable=False, unique=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("release_snapshots.id"), nullable=False),
        sa.Column("rule_code", sa.String(100), nullable=False),
        sa.Column("scope", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("compensating_control", sa.Text()),
        sa.Column("approved_by", sa.String(120)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_policy_exceptions_snapshot_id", "policy_exceptions", ["snapshot_id"])

def downgrade():
    op.drop_index("ix_policy_exceptions_snapshot_id", table_name="policy_exceptions")
    op.drop_table("policy_exceptions")
