import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

def uid(): return uuid.uuid4()
def now(): return datetime.utcnow()

class DeliveryPackage(Base):
    __tablename__ = "delivery_packages"
    __table_args__ = (UniqueConstraint("package_no","revision",name="uq_delivery_package_revision"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    package_no: Mapped[str] = mapped_column(String(50), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"), nullable=False, index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("release_snapshots.id"), nullable=False)
    recipient_type: Mapped[str] = mapped_column(String(50), nullable=False)
    recipient_code: Mapped[str] = mapped_column(String(80), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    created_by: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class DeliveryPackageItem(Base):
    __tablename__ = "delivery_package_items"
    __table_args__ = (UniqueConstraint("delivery_package_id","snapshot_artifact_id",name="uq_delivery_package_item"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    delivery_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("delivery_packages.id"), nullable=False, index=True)
    snapshot_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("snapshot_artifacts.id"), nullable=False)
    policy_decision: Mapped[str] = mapped_column(String(30), nullable=False)
    exception_reference: Mapped[str | None] = mapped_column(String(80))

class Distribution(Base):
    __tablename__ = "distributions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    distribution_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    delivery_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("delivery_packages.id"), nullable=False, index=True)
    recipient_type: Mapped[str] = mapped_column(String(50), nullable=False)
    recipient_code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)

class SoftwareAuthorization(Base):
    __tablename__ = "software_authorizations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    authorization_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"), nullable=False, index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("release_snapshots.id"), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    site_code: Mapped[str] = mapped_column(String(80), nullable=False)
    line_code: Mapped[str] = mapped_column(String(80), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False, default="PRODUCTION")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    restriction_note: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
