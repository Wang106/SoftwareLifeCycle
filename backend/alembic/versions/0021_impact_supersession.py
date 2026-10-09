"""Keep original judgments immutable; corrections explicitly reference a predecessor."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0021_impact_supersession'
down_revision = '0020_global_role_status'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('issue_impact_assessments', sa.Column('supersedes_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('issue_impact_assessments', sa.Column('correction_reason', sa.Text(), nullable=True))
    op.create_unique_constraint('uq_impact_identity_context', 'issue_impact_assessments', ['id', 'issue_id', 'release_id', 'snapshot_id'])
    op.create_foreign_key('fk_impact_supersedes', 'issue_impact_assessments', 'issue_impact_assessments',
        ['supersedes_id', 'issue_id', 'release_id', 'snapshot_id'], ['id', 'issue_id', 'release_id', 'snapshot_id'])
    op.create_unique_constraint('uq_impact_supersedes', 'issue_impact_assessments', ['supersedes_id'])
    op.create_check_constraint('ck_impact_correction_pair', 'issue_impact_assessments',
        "(supersedes_id IS NULL AND correction_reason IS NULL) OR "
        "(supersedes_id IS NOT NULL AND correction_reason IS NOT NULL AND "
        "length(trim(correction_reason)) BETWEEN 1 AND 4000)")
    op.create_check_constraint('ck_impact_not_self', 'issue_impact_assessments', 'supersedes_id IS NULL OR supersedes_id <> id')


def downgrade():
    # Losing predecessor metadata could resurrect a superseded judgment.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM issue_impact_assessments WHERE supersedes_id IS NOT NULL) THEN
            RAISE EXCEPTION 'Cannot downgrade while impact corrections exist';
        END IF;
    END $$""")
    op.drop_constraint('ck_impact_not_self', 'issue_impact_assessments', type_='check')
    op.drop_constraint('ck_impact_correction_pair', 'issue_impact_assessments', type_='check')
    op.drop_constraint('uq_impact_supersedes', 'issue_impact_assessments', type_='unique')
    op.drop_constraint('fk_impact_supersedes', 'issue_impact_assessments', type_='foreignkey')
    op.drop_constraint('uq_impact_identity_context', 'issue_impact_assessments', type_='unique')
    op.drop_column('issue_impact_assessments', 'correction_reason')
    op.drop_column('issue_impact_assessments', 'supersedes_id')
