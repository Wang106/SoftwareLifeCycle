import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

def uid(): return uuid.uuid4()
def now(): return datetime.utcnow()

class ReleaseSnapshot(Base):
    __tablename__ = "release_snapshots"
    __table_args__ = (UniqueConstraint("release_id", "snapshot_number"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    snapshot_no: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"), nullable=False)
    snapshot_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="FROZEN")
    release_metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SnapshotArtifact(Base):
    __tablename__ = "snapshot_artifacts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("release_snapshots.id"), nullable=False, index=True)
    source_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifacts.id"), nullable=False)
    component_code: Mapped[str] = mapped_column(String(80), nullable=False)
    component_version: Mapped[str | None] = mapped_column(String(100))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(80), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    classification: Mapped[str] = mapped_column(String(40), nullable=False)
    distribution_level: Mapped[str] = mapped_column(String(40), nullable=False)
    ai_access_policy: Mapped[str] = mapped_column(String(40), nullable=False)
    storage_reference: Mapped[str] = mapped_column(Text, nullable=False)
