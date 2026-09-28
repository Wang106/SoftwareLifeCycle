import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def uid():
    return uuid.uuid4()


def now():
    return datetime.utcnow()


class ManufacturingSite(Base):
    __tablename__ = "manufacturing_sites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    site_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    region: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")


class ProductionLine(Base):
    __tablename__ = "production_lines"
    __table_args__ = (
        UniqueConstraint("site_id", "line_code", name="uq_production_line_site_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manufacturing_sites.id"), nullable=False, index=True)
    line_code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    deployment_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    authorization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("software_authorizations.id"), nullable=False, index=True
    )
    production_line_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_lines.id"), nullable=False, index=True
    )
    expected_release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"), nullable=False)
    expected_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("release_snapshots.id"), nullable=False
    )
    actual_release_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("releases.id"))
    actual_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("release_snapshots.id"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SoftwareChangeover(Base):
    __tablename__ = "software_changeovers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    changeover_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    deployment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deployments.id"), nullable=False, index=True)
    authorization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("software_authorizations.id"), nullable=False
    )
    from_release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"), nullable=False)
    to_release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PLANNED")
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)


class ProductionBatch(Base):
    __tablename__ = "production_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    batch_no: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    deployment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deployments.id"), nullable=False, index=True)
    changeover_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("software_changeovers.id"))
    authorization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("software_authorizations.id"), nullable=False
    )
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"), nullable=False)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("release_snapshots.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PLANNED")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
