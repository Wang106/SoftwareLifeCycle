import uuid
from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class IssueImpactAssessment(Base):
    __tablename__ = 'issue_impact_assessments'
    __table_args__ = (
        CheckConstraint("decision IN ('AFFECTED','NOT_AFFECTED','NEEDS_REVIEW')", name='ck_impact_decision'),
        Index('ix_impact_assessment_context', 'issue_id', 'release_id', 'snapshot_id', 'created_at'),
        UniqueConstraint('supersedes_id', name='uq_impact_supersedes'),
        UniqueConstraint('id', 'issue_id', 'release_id', 'snapshot_id', name='uq_impact_identity_context'),
        ForeignKeyConstraint(['supersedes_id', 'issue_id', 'release_id', 'snapshot_id'],
            ['issue_impact_assessments.id', 'issue_impact_assessments.issue_id',
             'issue_impact_assessments.release_id', 'issue_impact_assessments.snapshot_id'], name='fk_impact_supersedes'),
        CheckConstraint("(supersedes_id IS NULL AND correction_reason IS NULL) OR "
            "(supersedes_id IS NOT NULL AND correction_reason IS NOT NULL AND "
            "length(trim(correction_reason)) BETWEEN 1 AND 4000)", name='ck_impact_correction_pair'),
        CheckConstraint('supersedes_id IS NULL OR supersedes_id <> id', name='ck_impact_not_self'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('issues.id'), nullable=False, index=True)
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('releases.id'), nullable=False)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('release_snapshots.id'), nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ref: Mapped[str | None] = mapped_column(Text)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    correction_reason: Mapped[str | None] = mapped_column(Text)
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
