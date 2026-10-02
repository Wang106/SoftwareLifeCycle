"""Index exact release/snapshot execution evidence without changing history."""
from alembic import op

revision = '0018_asr_evidence_index'
down_revision = '0017_deployment_actual_version'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_dvp_executions_release_snapshot_item', 'dvp_executions',
        ['release_id', 'snapshot_id', 'dvp_item_id', 'execution_no'])


def downgrade():
    op.drop_index('ix_dvp_executions_release_snapshot_item', table_name='dvp_executions')
