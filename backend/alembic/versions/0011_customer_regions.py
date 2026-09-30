"""Optional customer region for the release matrix.

Revision ID: 0011_customer_regions
Revises: 0010_append_only_audit_events
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_customer_regions"
down_revision = "0010_append_only_audit_events"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('customers', sa.Column('region', sa.String(20), nullable=True))
    op.create_check_constraint('ck_customer_region', 'customers',
        "region IS NULL OR region IN ('APAC','EUROPE','AMERICAS','OTHER')")


def downgrade():
    op.drop_constraint('ck_customer_region', 'customers', type_='check')
    op.drop_column('customers', 'region')
