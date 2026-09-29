from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.audit import AuditEvent
from app.models.approval import ReleaseDecision
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot


router = APIRouter(prefix="/api/v1", tags=["audit"])


def _release_links(db: Session, events: list[AuditEvent]) -> dict[tuple[str, object], str]:
    snapshot_ids = {event.entity_id for event in events
                    if event.entity_type == "RELEASE_SNAPSHOT" and event.entity_id}
    decision_ids = {event.entity_id for event in events
                    if event.entity_type == "RELEASE_DECISION" and event.entity_id}
    snapshots = db.scalars(select(ReleaseSnapshot).where(ReleaseSnapshot.id.in_(snapshot_ids))).all() if snapshot_ids else []
    decisions = db.scalars(select(ReleaseDecision).where(ReleaseDecision.id.in_(decision_ids))).all() if decision_ids else []
    release_ids = {row.release_id for row in snapshots + decisions}
    applications = {row.id for row in db.scalars(select(Release).where(
        Release.id.in_(release_ids), Release.release_type == "APPLICATION")).all()} if release_ids else set()
    links = {}
    for snapshot in snapshots:
        if snapshot.release_id in applications:
            links[("RELEASE_SNAPSHOT", snapshot.id)] = str(snapshot.release_id)
    for decision in decisions:
        if decision.release_id in applications:
            links[("RELEASE_DECISION", decision.id)] = str(decision.release_id)
    return links


def _event_detail(event: AuditEvent, related_release_id: str | None = None) -> dict:
    return {
        "id": str(event.id),
        "event_no": event.event_no,
        "event_type": event.event_type,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": str(event.entity_id) if event.entity_id else None,
        "entity_ref": event.entity_ref,
        "related_release_id": related_release_id,
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
    links = _release_links(db, rows)
    return [_event_detail(row, links.get((row.entity_type, row.entity_id))) for row in rows]


@router.get("/activity/{event_no}")
def get_activity(event_no: str, db: Session = Depends(get_db)):
    event = db.scalars(
        select(AuditEvent).where(AuditEvent.event_no == event_no)
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="audit event not found")
    links = _release_links(db, [event])
    return _event_detail(event, links.get((event.entity_type, event.entity_id)))
