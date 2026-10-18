import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def uid():
    return uuid.uuid4()


def now():
    return datetime.now(timezone.utc)


class ReleaseChainRevocation(Base):
    __tablename__ = "release_chain_revocations"
    __table_args__ = (
        UniqueConstraint("release_id", name="uq_revoked_release_model"),
        UniqueConstraint("delivery_package_id", name="uq_revoked_delivery_model"),
        UniqueConstraint("distribution_id", name="uq_revoked_distribution_model"),
        UniqueConstraint("authorization_id", name="uq_revoked_authorization_model"),
        CheckConstraint(
            "(release_id IS NOT NULL) + (delivery_package_id IS NOT NULL) + "
            "(distribution_id IS NOT NULL) + (authorization_id IS NOT NULL) = 1",
            name="ck_release_chain_revocation_one_target",
        ),
        CheckConstraint(
            "target_kind IN ('RELEASE','DELIVERY_PACKAGE','DISTRIBUTION','AUTHORIZATION')",
            name="ck_release_chain_revocation_kind",
        ),
        CheckConstraint(
            "length(trim(reason)) BETWEEN 1 AND 4000",
            name="ck_release_chain_revocation_reason",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    revocation_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    target_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    release_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("releases.id"))
    delivery_package_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("delivery_packages.id"))
    distribution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("distributions.id"))
    authorization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("software_authorizations.id"))
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("release_snapshots.id"), nullable=False)
    release_decision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("release_decisions.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    revoked_by: Mapped[str] = mapped_column(String(120), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
