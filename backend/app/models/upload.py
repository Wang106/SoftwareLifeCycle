"""Private, default-unconnected upload recovery metadata, never an Artifact."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def now():
    return datetime.now(timezone.utc)


class PrivateUploadSession(Base):
    __tablename__ = 'private_upload_sessions'
    __table_args__ = (
        UniqueConstraint('object_id', name='uq_private_upload_object'),
        CheckConstraint('expected_bytes >= 0', name='ck_private_upload_bytes'),
        CheckConstraint('revision >= 0', name='ck_private_upload_revision'),
        CheckConstraint('length(sha256) = 64', name='ck_private_upload_sha256'),
        CheckConstraint("state IN ('RESERVED','RECEIVING','STAGED','PUBLISHING','STORED_PRIVATE','RECONCILIATION_REQUIRED')", name='ck_private_upload_state'),
        CheckConstraint("(state = 'STORED_PRIVATE' AND stored_receipt_json IS NOT NULL AND trim(CAST(stored_receipt_json AS TEXT)) <> 'null') OR (state <> 'STORED_PRIVATE' AND stored_receipt_json IS NULL)", name='ck_private_upload_stored_receipt'),
        CheckConstraint("trim(CAST(request_json AS TEXT)) <> 'null' AND trim(CAST(context_json AS TEXT)) <> 'null' AND trim(CAST(reservation_receipt_json AS TEXT)) <> 'null'", name='ck_private_upload_required_json'),
        Index('ix_private_upload_component_created', 'release_component_id', 'created_at'),
    )

    # Caller request ID and server-reserved object ID must be supplied explicitly.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    storage_scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_principal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('security_principals.id'), nullable=False)
    release_component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('release_components.id'), nullable=False)
    expected_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    request_json: Mapped[dict] = mapped_column(JSON(none_as_null=True), nullable=False)
    context_json: Mapped[dict] = mapped_column(JSON(none_as_null=True), nullable=False)
    reservation_receipt_json: Mapped[dict] = mapped_column(JSON(none_as_null=True), nullable=False)
    stored_receipt_json: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
