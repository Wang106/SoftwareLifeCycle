import uuid
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

def uid(): return uuid.uuid4()

class ArtifactDistributionRule(Base):
    __tablename__ = "artifact_distribution_rules"
    __table_args__ = (
        UniqueConstraint("artifact_id", "recipient_type", "purpose", name="uq_artifact_recipient_purpose"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifacts.id"), nullable=False, index=True)
    recipient_type: Mapped[str] = mapped_column(String(50), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    recipient_code: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
