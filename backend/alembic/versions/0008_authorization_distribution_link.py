"""link software authorizations to distributions

Revision ID: 0008_authorization_distribution_link
Revises: 0007_distribution_authorization
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_authorization_distribution_link"
down_revision = "0007_distribution_authorization"
branch_labels = None
depends_on = None


def upgrade():
    # Nullable keeps the migration safe for databases that already contain
    # authorizations created before distributions were linked explicitly.
    op.add_column(
        "software_authorizations",
        sa.Column(
            "distribution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("distributions.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_software_authorizations_distribution_id",
        "software_authorizations",
        ["distribution_id"],
    )


def downgrade():
    op.drop_index(
        "ix_software_authorizations_distribution_id",
        table_name="software_authorizations",
    )
    op.drop_column("software_authorizations", "distribution_id")
