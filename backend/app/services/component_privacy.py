"""Hide strict declarations from historical public sample projections.

Creation must atomically persist the row and reserved audit evidence. Audit evidence
must remain append-only and retained: removing every marker would remove this
classification. This is not a general artifact authorization/publication policy.
Malformed receipts remain private; strict receipt validation is a separate concern.
"""
from sqlalchemy import func, or_, select
from app.models.audit import AuditEvent


def private_component_clause(component_id):
    return select(AuditEvent.id).where(
        AuditEvent.entity_id == component_id,
        or_(AuditEvent.event_type == 'APPLICATION_COMPONENT_DECLARED',
            func.upper(AuditEvent.event_no).like('EVT-ASRC-%')),
    ).exists()


def public_component_clause(component_id):
    return ~private_component_clause(component_id)
