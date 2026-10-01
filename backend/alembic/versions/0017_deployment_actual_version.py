"""Version actual deployment reports without inventing historical report counts."""
from alembic import op
import sqlalchemy as sa

revision = "0017_deployment_actual_version"
down_revision = "0016_authenticated_audit_actors"
branch_labels = None
depends_on = None


def upgrade():
    # Existing deployments start at version zero, regardless of legacy audit history.
    op.add_column("deployments", sa.Column("actual_version", sa.Integer(),
        nullable=False, server_default=sa.text("0")))
    op.create_check_constraint("ck_deployment_actual_version", "deployments", "actual_version >= 0")


def downgrade():
    op.drop_constraint("ck_deployment_actual_version", "deployments", type_="check")
    op.drop_column("deployments", "actual_version")
