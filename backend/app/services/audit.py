from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent


class AuditEventError(ValueError):
    pass


class AuditEventService:
    """Append-only writer for formal domain and operational history."""

    def __init__(self, db: Session):
        self.db = db

    def record(
        self,
        *,
        event_no: str,
        event_type: str,
        action: str,
        entity_type: str,
        entity_ref: str,
        actor_name: str,
        summary: str,
        entity_id=None,
        detail: str | None = None,
        payload: dict | None = None,
        occurred_at: datetime | None = None,
    ) -> AuditEvent:
        existing = self.db.scalars(
            select(AuditEvent).where(AuditEvent.event_no == event_no)
        ).first()
        if existing:
            raise AuditEventError("Audit event number already exists")

        event = AuditEvent(
            event_no=event_no,
            event_type=event_type,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_ref=entity_ref,
            actor_name=actor_name,
            summary=summary,
            detail=detail,
            payload_json=payload or {},
        )
        if occurred_at is not None:
            event.occurred_at = occurred_at

        self.db.add(event)
        self.db.flush()
        self.db.refresh(event)
        return event
