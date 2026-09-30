"""Append-only issue assessments pinned to a frozen snapshot."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0012_issue_impact_assessments'
down_revision = '0011_customer_regions'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('issue_impact_assessments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('issue_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('issues.id'), nullable=False),
        sa.Column('release_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('releases.id'), nullable=False),
        sa.Column('snapshot_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('release_snapshots.id'), nullable=False),
        sa.Column('decision', sa.String(30), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False), sa.Column('evidence_ref', sa.Text()),
        sa.Column('actor_name', sa.String(120), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint("decision IN ('AFFECTED','NOT_AFFECTED','NEEDS_REVIEW')", name='ck_impact_decision'))
    op.create_index('ix_issue_impact_assessments_issue_id', 'issue_impact_assessments', ['issue_id'])
    op.create_index('ix_impact_assessment_context', 'issue_impact_assessments', ['issue_id', 'release_id', 'snapshot_id', 'created_at'])
    op.execute("CREATE FUNCTION slc_prevent_impact_assessment_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'issue_impact_assessments are append-only'; END; $$ LANGUAGE plpgsql")
    op.execute('CREATE TRIGGER trg_impact_assessments_append_only BEFORE UPDATE OR DELETE ON issue_impact_assessments FOR EACH ROW EXECUTE FUNCTION slc_prevent_impact_assessment_mutation()')


def downgrade():
    op.drop_table('issue_impact_assessments')
    op.execute('DROP FUNCTION slc_prevent_impact_assessment_mutation()')
