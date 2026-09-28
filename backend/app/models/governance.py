import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

def uid(): return uuid.uuid4()
def now(): return datetime.utcnow()

class PolicyException(Base):
    __tablename__ = "policy_exceptions"
    __table_args__ = (UniqueConstraint("exception_no"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    exception_no: Mapped[str] = mapped_column(String(50), nullable=False)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("release_snapshots.id"), nullable=False, index=True)
    rule_code: Mapped[str] = mapped_column(String(100), nullable=False)
    scope: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    compensating_control: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(120))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
