"""Append-only production trace history for Deployment actual software.

The legacy ``deployments.actual_*`` physical columns hold the *first recorded
value* (the "recorded baseline"). Corrections are appended to a dedicated
ledger and never overwrite the baseline. The effective/current value is derived
by projection (see ``app.services.production_history``), never by mutating the
baseline. Changeover and Batch correction ledgers are intentionally out of
scope here and are delivered in a later package.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def uid():
    return uuid.uuid4()


def now():
    return datetime.now(timezone.utc)


class DeploymentActualBaseline(Base):
    """One immutable baseline per already-reported Deployment.

    Captures the legacy physical columns exactly as they were at migration or
    first-report time. The source distinguishes a legacy current value
    (``LEGACY_CURRENT``), an imported sample value (``IMPORTED_CURRENT``) and a
    genuine first report under the new protocol (``FIRST_REPORT``).
    """

    __tablename__ = "deployment_actual_baselines"
    __table_args__ = (
        UniqueConstraint("deployment_id", name="uq_deployment_actual_baseline_target"),
        CheckConstraint(
            "source IN ('LEGACY_CURRENT','IMPORTED_CURRENT','FIRST_REPORT')",
            name="ck_deployment_actual_baseline_source",
        ),
        CheckConstraint(
            "recorded_actual_version >= 0",
            name="ck_deployment_actual_baseline_version",
        ),
        CheckConstraint(
            "(actual_release_id IS NULL) = (actual_snapshot_id IS NULL)",
            name="ck_deployment_actual_baseline_pair",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployments.id"), nullable=False
    )
    actual_release_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("releases.id"))
    actual_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("release_snapshots.id")
    )
    recorded_status: Mapped[str] = mapped_column(String(30), nullable=False)
    recorded_actual_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    recorded_deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )
    # The exact audit event that proves the baseline (FIRST_REPORT only).
    baseline_event_no: Mapped[str | None] = mapped_column(String(50))


class DeploymentActualCorrection(Base):
    """One append-only correction to a Deployment's actual software.

    ``id`` doubles as the command ``request_id``. ``revision`` is per-target and
    strictly sequential (root successor = predecessor + 1). A correction carries
    the *complete* replacement value set; it never patches a subset silently.
    """

    __tablename__ = "deployment_actual_corrections"
    __table_args__ = (
        UniqueConstraint("deployment_id", "revision", name="uq_deployment_actual_corr_revision"),
        UniqueConstraint("baseline_id", "revision", name="uq_deployment_actual_corr_baseline_revision"),
        # Referenced by the composite predecessor FK (deployment_id, id).
        UniqueConstraint("deployment_id", "id", name="uq_deployment_actual_corr_target_id"),
        Index("ix_deployment_actual_corr_target_revision", "deployment_id", "revision"),
        CheckConstraint("revision >= 1", name="ck_deployment_actual_corr_revision_positive"),
        CheckConstraint(
            "(actual_release_id IS NULL) = (actual_snapshot_id IS NULL)",
            name="ck_deployment_actual_corr_pair",
        ),
        CheckConstraint(
            "length(trim(correction_reason)) BETWEEN 1 AND 2000",
            name="ck_deployment_actual_corr_reason",
        ),
        ForeignKeyConstraint(
            ["deployment_id", "predecessor_id"],
            ["deployment_actual_corrections.deployment_id",
             "deployment_actual_corrections.id"],
            name="fk_deployment_actual_corr_predecessor",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployments.id"), nullable=False
    )
    baseline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployment_actual_baselines.id"), nullable=False
    )
    predecessor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_release_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("releases.id"))
    actual_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("release_snapshots.id")
    )
    correction_reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_principal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    request_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    audit_event_no: Mapped[str] = mapped_column(String(50), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )


class ChangeoverBaseline(Base):
    """One immutable baseline per already-existing SoftwareChangeover.

    Mirrors :class:`DeploymentActualBaseline` for Changeover: the physical
    columns are the *recorded* value captured at migration or import time, and
    the source distinguishes a legacy current value, an imported sample value
    and (in a future correction protocol) a genuine first record. Corrections
    are appended to a dedicated ledger and never overwrite this baseline.
    """

    __tablename__ = "changeover_baselines"
    __table_args__ = (
        UniqueConstraint("changeover_id", name="uq_changeover_baseline_target"),
        CheckConstraint(
            "source IN ('LEGACY_CURRENT','IMPORTED_CURRENT','FIRST_RECORD')",
            name="ck_changeover_baseline_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    changeover_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("software_changeovers.id"), nullable=False
    )
    from_release_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("releases.id"), nullable=False
    )
    to_release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"), nullable=False)
    recorded_status: Mapped[str] = mapped_column(String(30), nullable=False)
    recorded_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )
    baseline_event_no: Mapped[str | None] = mapped_column(String(50))


class ChangeoverCorrection(Base):
    """One append-only correction to a SoftwareChangeover's recorded facts."""

    __tablename__ = "changeover_corrections"
    __table_args__ = (
        UniqueConstraint("changeover_id", "revision", name="uq_changeover_corr_revision"),
        UniqueConstraint("baseline_id", "revision", name="uq_changeover_corr_baseline_revision"),
        UniqueConstraint("changeover_id", "id", name="uq_changeover_corr_target_id"),
        Index("ix_changeover_corr_target_revision", "changeover_id", "revision"),
        CheckConstraint("revision >= 1", name="ck_changeover_corr_revision_positive"),
        CheckConstraint(
            "length(trim(correction_reason)) BETWEEN 1 AND 2000",
            name="ck_changeover_corr_reason",
        ),
        ForeignKeyConstraint(
            ["changeover_id", "predecessor_id"],
            ["changeover_corrections.changeover_id", "changeover_corrections.id"],
            name="fk_changeover_corr_predecessor",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    changeover_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("software_changeovers.id"), nullable=False
    )
    baseline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("changeover_baselines.id"), nullable=False
    )
    predecessor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    from_release_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("releases.id"), nullable=False
    )
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    correction_reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_principal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    request_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    audit_event_no: Mapped[str] = mapped_column(String(50), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )


class BatchBaseline(Base):
    """One immutable baseline per already-existing ProductionBatch."""

    __tablename__ = "batch_baselines"
    __table_args__ = (
        UniqueConstraint("batch_id", name="uq_batch_baseline_target"),
        CheckConstraint(
            "source IN ('LEGACY_CURRENT','IMPORTED_CURRENT','FIRST_RECORD')",
            name="ck_batch_baseline_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_batches.id"), nullable=False
    )
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"), nullable=False)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("release_snapshots.id"), nullable=False
    )
    changeover_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("software_changeovers.id")
    )
    recorded_status: Mapped[str] = mapped_column(String(30), nullable=False)
    recorded_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )
    baseline_event_no: Mapped[str | None] = mapped_column(String(50))


class BatchCorrection(Base):
    """One append-only correction to a ProductionBatch's recorded facts."""

    __tablename__ = "batch_corrections"
    __table_args__ = (
        UniqueConstraint("batch_id", "revision", name="uq_batch_corr_revision"),
        UniqueConstraint("baseline_id", "revision", name="uq_batch_corr_baseline_revision"),
        UniqueConstraint("batch_id", "id", name="uq_batch_corr_target_id"),
        Index("ix_batch_corr_target_revision", "batch_id", "revision"),
        CheckConstraint("revision >= 1", name="ck_batch_corr_revision_positive"),
        CheckConstraint(
            "length(trim(correction_reason)) BETWEEN 1 AND 2000",
            name="ck_batch_corr_reason",
        ),
        CheckConstraint(
            "(ended_at IS NULL) OR (started_at IS NULL) OR (ended_at >= started_at)",
            name="ck_batch_corr_ended_after_started",
        ),
        ForeignKeyConstraint(
            ["batch_id", "predecessor_id"],
            ["batch_corrections.batch_id", "batch_corrections.id"],
            name="fk_batch_corr_predecessor",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_batches.id"), nullable=False
    )
    baseline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("batch_baselines.id"), nullable=False
    )
    predecessor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    changeover_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("software_changeovers.id")
    )
    note: Mapped[str | None] = mapped_column(Text)
    correction_reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_principal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    request_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    audit_event_no: Mapped[str] = mapped_column(String(50), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )
