import uuid
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

def uid(): return uuid.uuid4()
def now(): return datetime.utcnow()

class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")

class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("customer_id", "project_code"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), nullable=False)
    project_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    vehicle_platform: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")

class SoftwareProduct(Base):
    __tablename__ = "software_products"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    software_type: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")

class Release(Base):
    __tablename__ = "releases"
    __table_args__ = (UniqueConstraint("software_id", "release_type", "version"), CheckConstraint("release_type IN ('STANDARD','APPLICATION')", name="ck_release_type"))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    software_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("software_products.id"), nullable=False)
    release_type: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    release_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class StandardReleaseDetail(Base):
    __tablename__ = "standard_release_details"
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    previous_release_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("releases.id"))
    git_repository: Mapped[str | None] = mapped_column(Text)
    git_branch: Mapped[str | None] = mapped_column(Text)
    git_commit: Mapped[str | None] = mapped_column(String(100))

class ApplicationReleaseDetail(Base):
    __tablename__ = "application_release_details"
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    standard_base_release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"), nullable=False)
    previous_application_release_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("releases.id"))

class ComponentDefinition(Base):
    __tablename__ = "component_definitions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class ReleaseComponent(Base):
    __tablename__ = "release_components"
    __table_args__ = (CheckConstraint("delta_type IN ('UNCHANGED','MODIFIED','ADDED','REMOVED')", name="ck_delta_type"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"), nullable=False)
    component_definition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("component_definitions.id"), nullable=False)
    version: Mapped[str | None] = mapped_column(String(100))
    base_component_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("release_components.id"))
    delta_type: Mapped[str] = mapped_column(String(20), default="MODIFIED")

class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint("classification IN ('PUBLIC','INTERNAL','CONFIDENTIAL','STRICTLY_CONFIDENTIAL')", name="ck_artifact_classification"),
        CheckConstraint("distribution_level IN ('INTERNAL_ONLY','CONTROLLED_EXTERNAL','EXTERNAL')", name="ck_distribution_level"),
        CheckConstraint("ai_access_policy IN ('DENY','LOCAL_ONLY','PRIVATE_AI','EXTERNAL_AI_ALLOWED')", name="ck_ai_policy"),
        CheckConstraint("controlled = false OR (sha256 IS NOT NULL AND distribution_level IS NOT NULL)", name="ck_controlled_artifact_integrity"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    release_component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("release_components.id"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(80), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_reference: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int | None]
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    controlled: Mapped[bool] = mapped_column(Boolean, default=True)
    classification: Mapped[str] = mapped_column(String(40), default="INTERNAL")
    distribution_level: Mapped[str | None] = mapped_column(String(40))
    ai_access_policy: Mapped[str] = mapped_column(String(40), default="DENY")
