"""Append-only resource references, independent of artifact distribution permissions."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class ResourceLink(Base):
    __tablename__ = 'resource_links'
    __table_args__ = (Index('ix_resource_links_entity', 'entity_type', 'entity_id'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity_ref: Mapped[str] = mapped_column(String(240), nullable=False)
    entity_href: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    location_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    location: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
