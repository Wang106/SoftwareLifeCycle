"""Private upload recovery metadata; no Artifact, data backfill or public writes.

Revision ID: 0030_private_upload_sessions
Revises: 0029_changeover_batch_history
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0030_private_upload_sessions'
down_revision = '0029_changeover_batch_history'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'private_upload_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('object_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('storage_scope_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('actor_principal_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('security_principals.id'), nullable=False),
        sa.Column('release_component_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('release_components.id'), nullable=False),
        sa.Column('expected_bytes', sa.BigInteger(), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('state', sa.String(32), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('request_json', sa.JSON(none_as_null=True), nullable=False),
        sa.Column('context_json', sa.JSON(none_as_null=True), nullable=False),
        sa.Column('reservation_receipt_json', sa.JSON(none_as_null=True), nullable=False),
        sa.Column('stored_receipt_json', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('object_id', name='uq_private_upload_object'),
        sa.CheckConstraint('expected_bytes >= 0', name='ck_private_upload_bytes'),
        sa.CheckConstraint('revision >= 0', name='ck_private_upload_revision'),
        sa.CheckConstraint('length(sha256) = 64', name='ck_private_upload_sha256'),
        sa.CheckConstraint("state IN ('RESERVED','RECEIVING','STAGED','PUBLISHING','STORED_PRIVATE','RECONCILIATION_REQUIRED')", name='ck_private_upload_state'),
        sa.CheckConstraint("(state = 'STORED_PRIVATE' AND stored_receipt_json IS NOT NULL AND trim(CAST(stored_receipt_json AS TEXT)) <> 'null') OR (state <> 'STORED_PRIVATE' AND stored_receipt_json IS NULL)", name='ck_private_upload_stored_receipt'),
        sa.CheckConstraint("trim(CAST(request_json AS TEXT)) <> 'null' AND trim(CAST(context_json AS TEXT)) <> 'null' AND trim(CAST(reservation_receipt_json AS TEXT)) <> 'null'", name='ck_private_upload_required_json'),
    )
    op.create_index('ix_private_upload_component_created', 'private_upload_sessions', ['release_component_id', 'created_at'])


def downgrade():
    # Never silently destroy the only retained recovery/receipt evidence.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM private_upload_sessions) THEN
            RAISE EXCEPTION 'Cannot downgrade retained private upload sessions';
        END IF;
    END $$;""")
    op.drop_index('ix_private_upload_component_created', table_name='private_upload_sessions')
    op.drop_table('private_upload_sessions')
