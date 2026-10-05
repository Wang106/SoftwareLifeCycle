"""Revocable browser sessions; bearer values are never stored."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0019_browser_sessions'
down_revision = '0018_asr_evidence_index'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('browser_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('principal_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('security_principals.id'), nullable=False),
        sa.Column('token_digest', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint('expires_at > created_at', name='ck_browser_session_expiry'))
    op.create_index('ix_browser_sessions_principal_expiry', 'browser_sessions', ['principal_id', 'expires_at'])


def downgrade():
    op.drop_index('ix_browser_sessions_principal_expiry', table_name='browser_sessions')
    op.drop_table('browser_sessions')
