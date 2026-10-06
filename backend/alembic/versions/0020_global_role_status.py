"""Preserve existing global grants while adding audited lifecycle status."""
from alembic import op
import sqlalchemy as sa

revision = '0020_global_role_status'
down_revision = '0019_browser_sessions'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('global_role_assignments', sa.Column('status', sa.String(20), nullable=False, server_default='ACTIVE'))
    op.create_check_constraint('ck_global_role_status', 'global_role_assignments', "status IN ('ACTIVE','SUSPENDED')")


def downgrade():
    # Never turn a suspended grant into an effective grant by dropping its status.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM global_role_assignments WHERE status = 'SUSPENDED') THEN
            RAISE EXCEPTION 'Cannot downgrade while suspended global grants exist';
        END IF;
    END $$""")
    op.drop_constraint('ck_global_role_status', 'global_role_assignments', type_='check')
    op.drop_column('global_role_assignments', 'status')
