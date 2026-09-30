"""Append-only references to external evidence and organization materials."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0014_resource_links'
down_revision = '0013_acceptance_dvp_links'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('resource_links',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_type', sa.String(30), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_ref', sa.String(240), nullable=False),
        sa.Column('entity_href', sa.String(500), nullable=False),
        sa.Column('title', sa.String(240), nullable=False),
        sa.Column('location_kind', sa.String(30), nullable=False),
        sa.Column('location', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('actor_name', sa.String(120), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')))
    op.create_index('ix_resource_links_entity', 'resource_links', ['entity_type', 'entity_id'])
    op.execute("CREATE FUNCTION slc_prevent_resource_link_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'resource_links are append-only'; END; $$ LANGUAGE plpgsql")
    op.execute('CREATE TRIGGER trg_resource_links_append_only BEFORE UPDATE OR DELETE ON resource_links FOR EACH ROW EXECUTE FUNCTION slc_prevent_resource_link_mutation()')


def downgrade():
    op.drop_table('resource_links')
    op.execute('DROP FUNCTION slc_prevent_resource_link_mutation()')
