import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.audit import AuditEvent
from app.models.approval import ReleaseDecision
from app.models.distribution import DeliveryPackage
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
        "delivery_revision": event.payload_json.get("revision") if event.entity_type == "DELIVERY_PACKAGE" else None,
        "actor_name": event.actor_name,
        "actor_principal_id": str(event.actor_principal_id) if event.actor_principal_id else None,
        "actor_display_name": event.actor_display_name,
        "declared_actor_name": event.declared_actor_name,
        "summary": event.summary,
        "detail": event.detail,
        "payload": event.payload_json,
        "occurred_at": event.occurred_at,
        "created_at": event.created_at,
    }


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


class AuditFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: str | None = Field(None, max_length=50)
    entity_type: str | None = Field(None, max_length=80)
    entity_ref: str | None = Field(None, max_length=120)
    entity_id: uuid.UUID | None = None
    action: str | None = Field(None, max_length=80)
    actor_name: str | None = Field(None, max_length=120)
    actor_principal_id: uuid.UUID | None = None
    q: str | None = Field(None, max_length=200)
    occurred_from: datetime | None = None
    occurred_before: datetime | None = None
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0, le=100000)

    @model_validator(mode="after")
    def validate_range(self):
        for name in ("occurred_from", "occurred_before"):
            value = getattr(self, name)
            if value is not None:
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError("timestamps require a timezone")
                setattr(self, name, value.astimezone(timezone.utc))
        if self.occurred_from and self.occurred_before and self.occurred_from >= self.occurred_before:
            raise ValueError("occurred_from must precede occurred_before")
        return self


@router.get("/audit/events")
def audit_catalog(filters: Annotated[AuditFilters, Query()], db: Session = Depends(get_db)):
    """Read-only summaries; payload and long detail remain on exact event profiles."""
    stmt = select(AuditEvent)
    for name in ("event_type", "entity_type", "entity_ref", "entity_id", "action", "actor_name", "actor_principal_id"):
        value = getattr(filters, name)
        if value is not None and value != "":
            stmt = stmt.where(getattr(AuditEvent, name) == value)
    if filters.q and filters.q.strip():
        stmt = stmt.where(or_(*[column.contains(filters.q.strip(), autoescape=True)
            for column in (AuditEvent.event_no, AuditEvent.entity_ref, AuditEvent.actor_name,
                           AuditEvent.actor_display_name, AuditEvent.declared_actor_name,
                           AuditEvent.summary, AuditEvent.event_type, AuditEvent.action)]))
    if filters.occurred_from:
        stmt = stmt.where(AuditEvent.occurred_at >= filters.occurred_from)
    if filters.occurred_before:
        stmt = stmt.where(AuditEvent.occurred_at < filters.occurred_before)
    filtered = stmt.with_only_columns(AuditEvent.event_type).subquery()
    total = db.scalar(select(func.count()).select_from(filtered))
    counts = dict(db.execute(select(filtered.c.event_type, func.count())
        .group_by(filtered.c.event_type).order_by(filtered.c.event_type)).all())
    # Avoid loading unbounded JSON/text into directory rows.
    columns = [getattr(AuditEvent, name) for name in ("id", "event_no", "event_type", "action",
        "entity_type", "entity_id", "entity_ref", "actor_name", "actor_principal_id",
        "actor_display_name", "declared_actor_name", "summary", "occurred_at", "created_at")]
    delivery_revision = select(DeliveryPackage.revision).where(
        DeliveryPackage.id == AuditEvent.entity_id, AuditEvent.entity_type == "DELIVERY_PACKAGE"
    ).correlate(AuditEvent).scalar_subquery().label("delivery_revision")
    rows = db.execute(stmt.with_only_columns(*columns, delivery_revision).order_by(
        AuditEvent.occurred_at.desc(), AuditEvent.event_no.desc(), AuditEvent.id.desc()
    ).limit(filters.limit).offset(filters.offset)).mappings().all()
    items = [{**dict(row), "id": str(row["id"]),
        "entity_id": str(row["entity_id"]) if row["entity_id"] else None,
        "actor_principal_id": str(row["actor_principal_id"])
        if row["actor_principal_id"] else None} for row in rows]
    next_offset = filters.offset + filters.limit
    return {"items": items, "total": total, "event_type_counts": counts,
        "limit": filters.limit, "offset": filters.offset,
        "next_offset": next_offset if next_offset < total else None}
