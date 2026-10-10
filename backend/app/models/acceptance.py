"""Explicit acceptance-to-test assignments, preserved as formal history."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class AcceptanceDvpLink(Base):
    __tablename__ = 'acceptance_dvp_links'
    __table_args__ = (
        UniqueConstraint('id', 'criterion_id', name='uq_acceptance_identity_criterion'),
        UniqueConstraint('supersedes_id', name='uq_acceptance_supersedes'),
        ForeignKeyConstraint(['supersedes_id', 'criterion_id'],
            ['acceptance_dvp_links.id', 'acceptance_dvp_links.criterion_id'], name='fk_acceptance_supersedes'),
        CheckConstraint("(action = 'ASSIGN' AND supersedes_id IS NULL) OR "
            "(action IN ('SUPERSEDE','WITHDRAW') AND supersedes_id IS NOT NULL)", name='ck_acceptance_action'),
        CheckConstraint('supersedes_id IS NULL OR supersedes_id <> id', name='ck_acceptance_not_self'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    criterion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('acceptance_criteria.id'), nullable=False, index=True)
    dvp_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('dvp_items.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False, default='ASSIGN', server_default='ASSIGN')
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
