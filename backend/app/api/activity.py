from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.audit import AuditEvent


router = APIRouter(prefix="/api/v1", tags=["audit"])


def _event_detail(event: AuditEvent) -> dict:
    return {
        "id": str(event.id),
        "event_no": event.event_no,
        "event_type": event.event_type,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": str(event.entity_id) if event.entity_id else None,
        "entity_ref": event.entity_ref,
        "actor_name": event.actor_name,
        "summary": event.summary,
        "detail": event.detail,
        "payload": event.payload_json,
        "occurred_at": event.occurred_at,
        "created_at": event.created_at,
    }


@router.get("/activity")
def list_activity(
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_ref: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    statement = select(AuditEvent)
    if event_type:
        statement = statement.where(AuditEvent.event_type == event_type)
    if entity_type:
        statement = statement.where(AuditEvent.entity_type == entity_type)
    if entity_ref:
        statement = statement.where(AuditEvent.entity_ref == entity_ref)
    rows = db.scalars(
        statement.order_by(
            AuditEvent.occurred_at.desc(), AuditEvent.event_no.desc()
        ).limit(limit)
    ).all()
    return [_event_detail(row) for row in rows]


@router.get("/activity/{event_no}")
def get_activity(event_no: str, db: Session = Depends(get_db)):
    event = db.scalars(
        select(AuditEvent).where(AuditEvent.event_no == event_no)
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="audit event not found")
    return _event_detail(event)
