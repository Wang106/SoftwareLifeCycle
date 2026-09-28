import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

def uid(): return uuid.uuid4()
def now(): return datetime.utcnow()

class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    approval_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("release_snapshots.id"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    submitted_by: Mapped[str | None] = mapped_column(String(120))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ApprovalStep(Base):
    __tablename__ = "approval_steps"
    __table_args__ = (UniqueConstraint("approval_request_id","step_order", name="uq_approval_step_order"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    approval_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approval_requests.id"), nullable=False, index=True)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    role_name: Mapped[str] = mapped_column(String(120), nullable=False)
    approver_name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="WAITING")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class ApprovalAction(Base):
    __tablename__ = "approval_actions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    approval_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approval_requests.id"), nullable=False, index=True)
    step_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("approval_steps.id"))
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ReleaseDecision(Base):
    __tablename__ = "release_decisions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    decision_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"), nullable=False, index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("release_snapshots.id"), nullable=False)
    approval_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approval_requests.id"), nullable=False)
    readiness_status: Mapped[str] = mapped_column(String(30), nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(120), nullable=False)
    decision_notes: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
