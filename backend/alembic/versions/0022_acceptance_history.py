"""Preserve assignments and explicitly append replacement/withdrawal history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0022_acceptance_history'
down_revision = '0021_impact_supersession'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('acceptance_dvp_links', sa.Column('action', sa.String(20), nullable=False, server_default='ASSIGN'))
    op.add_column('acceptance_dvp_links', sa.Column('supersedes_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_unique_constraint('uq_acceptance_identity_criterion', 'acceptance_dvp_links', ['id', 'criterion_id'])
    op.create_foreign_key('fk_acceptance_supersedes', 'acceptance_dvp_links', 'acceptance_dvp_links',
        ['supersedes_id', 'criterion_id'], ['id', 'criterion_id'])
    op.create_unique_constraint('uq_acceptance_supersedes', 'acceptance_dvp_links', ['supersedes_id'])
    op.create_check_constraint('ck_acceptance_action', 'acceptance_dvp_links',
        "(action = 'ASSIGN' AND supersedes_id IS NULL) OR "
        "(action IN ('SUPERSEDE','WITHDRAW') AND supersedes_id IS NOT NULL)")
    op.create_check_constraint('ck_acceptance_not_self', 'acceptance_dvp_links', 'supersedes_id IS NULL OR supersedes_id <> id')
    # All commands lock their SCR through commit; duplicate effective pairs are
    # checked under that lock. A permanent pair unique would forbid reassignment.
    op.drop_constraint('uq_acceptance_dvp_pair', 'acceptance_dvp_links', type_='unique')


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM acceptance_dvp_links WHERE action <> 'ASSIGN') THEN
            RAISE EXCEPTION 'Cannot downgrade while acceptance corrections exist';
        END IF;
    END $$""")
    op.create_unique_constraint('uq_acceptance_dvp_pair', 'acceptance_dvp_links', ['criterion_id', 'dvp_item_id'])
    op.drop_constraint('ck_acceptance_not_self', 'acceptance_dvp_links', type_='check')
    op.drop_constraint('ck_acceptance_action', 'acceptance_dvp_links', type_='check')
    op.drop_constraint('uq_acceptance_supersedes', 'acceptance_dvp_links', type_='unique')
    op.drop_constraint('fk_acceptance_supersedes', 'acceptance_dvp_links', type_='foreignkey')
    op.drop_constraint('uq_acceptance_identity_criterion', 'acceptance_dvp_links', type_='unique')
    op.drop_column('acceptance_dvp_links', 'supersedes_id')
    op.drop_column('acceptance_dvp_links', 'action')
