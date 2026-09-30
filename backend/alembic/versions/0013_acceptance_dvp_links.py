"""Explicit append-only acceptance criterion assignments."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0013_acceptance_dvp_links'
down_revision = '0012_issue_impact_assessments'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('acceptance_dvp_links',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('criterion_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('acceptance_criteria.id'), nullable=False),
        sa.Column('dvp_item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dvp_items.id'), nullable=False),
        sa.Column('actor_name', sa.String(120), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('criterion_id', 'dvp_item_id', name='uq_acceptance_dvp_pair'))
    op.create_index('ix_acceptance_dvp_links_criterion_id', 'acceptance_dvp_links', ['criterion_id'])
    op.execute("CREATE FUNCTION slc_prevent_acceptance_link_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'acceptance_dvp_links are append-only'; END; $$ LANGUAGE plpgsql")
    op.execute('CREATE TRIGGER trg_acceptance_links_append_only BEFORE UPDATE OR DELETE ON acceptance_dvp_links FOR EACH ROW EXECUTE FUNCTION slc_prevent_acceptance_link_mutation()')


def downgrade():
    op.drop_table('acceptance_dvp_links')
    op.execute('DROP FUNCTION slc_prevent_acceptance_link_mutation()')
