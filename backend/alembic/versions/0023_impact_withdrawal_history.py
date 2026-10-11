"""Append context terminal withdrawal events without rewriting legacy judgments."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0023_impact_withdrawal_history'
down_revision = '0022_acceptance_history'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('issue_impact_assessments', sa.Column('action', sa.String(20)))
    op.add_column('issue_impact_assessments', sa.Column('context_seq', sa.BigInteger()))
    op.add_column('issue_impact_assessments', sa.Column('after_withdrawal_id', postgresql.UUID(as_uuid=True)))
    op.alter_column('issue_impact_assessments', 'decision', existing_type=sa.String(30), nullable=True)
    op.create_check_constraint('ck_impact_history_action', 'issue_impact_assessments',
        "(action IS NULL AND context_seq IS NULL AND decision IS NOT NULL AND after_withdrawal_id IS NULL) OR "
        "(action IS NOT NULL AND context_seq IS NOT NULL AND context_seq > 0 AND "
        "((action = 'ASSESS' AND decision IS NOT NULL AND supersedes_id IS NULL) OR "
        "(action = 'SUPERSEDE' AND decision IS NOT NULL AND supersedes_id IS NOT NULL AND after_withdrawal_id IS NULL) OR "
        "(action = 'WITHDRAW' AND decision IS NULL AND evidence_ref IS NULL AND supersedes_id IS NOT NULL AND after_withdrawal_id IS NULL)))")
    op.create_check_constraint('ck_impact_restore_not_self', 'issue_impact_assessments',
        'after_withdrawal_id IS NULL OR after_withdrawal_id <> id')
    op.create_unique_constraint('uq_impact_context_seq', 'issue_impact_assessments',
        ['issue_id', 'release_id', 'snapshot_id', 'context_seq'])
    op.create_foreign_key('fk_impact_after_withdrawal', 'issue_impact_assessments', 'issue_impact_assessments',
        ['after_withdrawal_id', 'issue_id', 'release_id', 'snapshot_id'], ['id', 'issue_id', 'release_id', 'snapshot_id'])
    op.create_index('ix_impact_terminal', 'issue_impact_assessments',
        ['issue_id', 'release_id', 'snapshot_id', 'context_seq', 'created_at', 'id'])
    op.execute("""CREATE FUNCTION slc_require_impact_history_action() RETURNS trigger AS $$
        BEGIN
            IF NEW.action IS NULL OR NEW.context_seq IS NULL THEN
                RAISE EXCEPTION 'New impact history requires explicit action and context_seq' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
    op.execute('CREATE TRIGGER trg_impact_history_insert BEFORE INSERT ON issue_impact_assessments FOR EACH ROW EXECUTE FUNCTION slc_require_impact_history_action()')


def downgrade():
    # Even sequenced technical judgments can change the winner when projected to
    # old timestamp ordering. Refuse before doing any DDL or touching original audit.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM issue_impact_assessments WHERE action IS NOT NULL
            OR context_seq IS NOT NULL OR after_withdrawal_id IS NOT NULL) THEN
            RAISE EXCEPTION 'Cannot downgrade while impact corrections exist or sequenced history would lose terminal semantics';
        END IF;
    END $$""")
    op.execute('DROP TRIGGER trg_impact_history_insert ON issue_impact_assessments')
    op.execute('DROP FUNCTION slc_require_impact_history_action()')
    op.drop_index('ix_impact_terminal', table_name='issue_impact_assessments')
    op.drop_constraint('fk_impact_after_withdrawal', 'issue_impact_assessments', type_='foreignkey')
    op.drop_constraint('uq_impact_context_seq', 'issue_impact_assessments', type_='unique')
    op.drop_constraint('ck_impact_restore_not_self', 'issue_impact_assessments', type_='check')
    op.drop_constraint('ck_impact_history_action', 'issue_impact_assessments', type_='check')
    op.alter_column('issue_impact_assessments', 'decision', existing_type=sa.String(30), nullable=False)
    op.drop_column('issue_impact_assessments', 'after_withdrawal_id')
    op.drop_column('issue_impact_assessments', 'context_seq')
    op.drop_column('issue_impact_assessments', 'action')
