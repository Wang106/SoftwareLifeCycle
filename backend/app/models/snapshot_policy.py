import uuid
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

def uid(): return uuid.uuid4()

class SnapshotArtifactDistributionRule(Base):
    __tablename__ = "snapshot_artifact_distribution_rules"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_artifact_id","recipient_type","purpose","recipient_code",
            name="uq_snapshot_artifact_policy"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    snapshot_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("snapshot_artifacts.id"), nullable=False, index=True)
    recipient_type: Mapped[str] = mapped_column(String(50), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    recipient_code: Mapped[str | None] = mapped_column(String(80))
