"""approval workflow and release decision"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_approval_release_decision"
down_revision = "0005_snapshot_artifact_policies"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("approval_no", sa.String(50), nullable=False, unique=True),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("release_snapshots.id")),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("submitted_by", sa.String(120)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "approval_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("approval_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("approval_requests.id"), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("role_name", sa.String(120), nullable=False),
        sa.Column("approver_name", sa.String(120)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("approval_request_id","step_order",name="uq_approval_step_order"),
    )
    op.create_index("ix_approval_steps_request_id","approval_steps",["approval_request_id"])
    op.create_table(
        "approval_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("approval_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("approval_requests.id"), nullable=False),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("approval_steps.id")),
        sa.Column("actor_name", sa.String(120), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_approval_actions_request_id","approval_actions",["approval_request_id"])
    op.create_table(
        "release_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("decision_no", sa.String(50), nullable=False, unique=True),
        sa.Column("release_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("releases.id"), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("release_snapshots.id"), nullable=False),
        sa.Column("approval_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("approval_requests.id"), nullable=False),
        sa.Column("readiness_status", sa.String(30), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("decided_by", sa.String(120), nullable=False),
        sa.Column("decision_notes", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_release_decisions_release_id","release_decisions",["release_id"])

def downgrade():
    op.drop_index("ix_release_decisions_release_id", table_name="release_decisions")
    op.drop_table("release_decisions")
    op.drop_index("ix_approval_actions_request_id", table_name="approval_actions")
    op.drop_table("approval_actions")
    op.drop_index("ix_approval_steps_request_id", table_name="approval_steps")
    op.drop_table("approval_steps")
    op.drop_table("approval_requests")
