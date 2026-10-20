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
