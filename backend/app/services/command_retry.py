"""Retry evidence for commands using request_id as the domain UUID.

No separate commit or request ledger: evidence lives in the command's atomic audit.
"""
from contextlib import contextmanager
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.actor import audit_actor_matches
from app.models.audit import AuditEvent


def retry_result(db, model, request_id, event_prefix, request_content, actor, error):
    if request_id is None:
        return None
    existing = db.get(model, request_id)
    if existing is None:
        return None
    event = db.scalar(select(AuditEvent).where(
        AuditEvent.event_no == f"{event_prefix}{request_id.hex}",
        AuditEvent.entity_id == existing.id,
    ))
    if (event is None or not audit_actor_matches(event, actor)
            or event.payload_json.get("request") != request_content):
        raise error("request_id already used for different or legacy content")
    return existing


def timestamp_content(value):
    # Omitted timestamps remain null, rather than comparing a generated server time.
    if value is None:
        return None
    return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()


@contextmanager
def atomic_command(db, error):
    """Release locks and discard all pending domain/audit changes on any failure."""
    try:
        yield
    except IntegrityError as exc:
        db.rollback()
        raise error("request_id or business number already exists") from exc
    except Exception:
        db.rollback()
        raise
