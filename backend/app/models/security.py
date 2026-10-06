"""Identity references and scoped role grants; credentials are intentionally absent."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def uid():
    return uuid.uuid4()


def now():
    return datetime.now(timezone.utc)


class SecurityPrincipal(Base):
    __tablename__ = "security_principals"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_security_principal_subject"),
        CheckConstraint("principal_type IN ('USER','SERVICE')", name="ck_security_principal_type"),
        CheckConstraint("status IN ('ACTIVE','DISABLED')", name="ck_security_principal_status"),
        Index("ix_security_principals_email", "email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    principal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)


class BrowserSession(Base):
    __tablename__ = 'browser_sessions'
    __table_args__ = (
        CheckConstraint('expires_at > created_at', name='ck_browser_session_expiry'),
        Index('ix_browser_sessions_principal_expiry', 'principal_id', 'expires_at'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    principal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('security_principals.id'), nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GlobalRoleAssignment(Base):
    __tablename__ = "global_role_assignments"
    __table_args__ = (
        UniqueConstraint("principal_id", "role", name="uq_global_role_assignment"),
        CheckConstraint("role IN ('PLATFORM_ADMIN','AUDITOR')", name="ck_global_role"),
        CheckConstraint("status IN ('ACTIVE','SUSPENDED')", name="ck_global_role_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("security_principals.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)


class SoftwareMembership(Base):
    __tablename__ = "software_memberships"
    __table_args__ = (
        UniqueConstraint("principal_id", "software_id", "role", name="uq_software_membership"),
        CheckConstraint(
            "role IN ('SOFTWARE_VIEWER','SOFTWARE_MAINTAINER')", name="ck_software_membership_role"
        ),
        CheckConstraint("status IN ('ACTIVE','SUSPENDED')", name="ck_software_membership_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("security_principals.id"), nullable=False, index=True
    )
    software_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("software_products.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)


class ProjectMembership(Base):
    __tablename__ = "project_memberships"
    __table_args__ = (
        UniqueConstraint("principal_id", "project_id", "role", name="uq_project_membership"),
        CheckConstraint(
            "role IN ('PROJECT_VIEWER','CONTRIBUTOR','REVIEWER','RELEASE_AUTHORITY',"
            "'DISTRIBUTION_AUTHORITY','PRODUCTION_AUTHORITY','PRODUCTION_OPERATOR')",
            name="ck_project_membership_role",
        ),
        CheckConstraint("status IN ('ACTIVE','SUSPENDED')", name="ck_project_membership_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("security_principals.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
