"""Explicit acceptance-to-test assignments, preserved as formal history."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class AcceptanceDvpLink(Base):
    __tablename__ = 'acceptance_dvp_links'
    __table_args__ = (UniqueConstraint('criterion_id', 'dvp_item_id', name='uq_acceptance_dvp_pair'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    criterion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('acceptance_criteria.id'), nullable=False, index=True)
    dvp_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('dvp_items.id'), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
