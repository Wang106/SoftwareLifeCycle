"""Bounded read-only release evidence summary for any standard or application release.

One exact release answers one evidence summary: its current frozen Snapshot, its
Readiness gates, its bound Approval and its effective Release Decision (resolving
the supersession chain). The summary is a read-only projection; it never performs
approval or decision state transitions and never infers a formal release from
record status, version strings or stage counts.

Every binding check compares the approval/decision's stored ``snapshot_id`` against
the *current* snapshot derived from Readiness coverage. A mismatch is reported as an
explicit ``*_bound`` false, never silently treated as consistent.
"""
import uuid

from sqlalchemy.orm import Session

from app.api.dashboard import _readiness_for_release
from app.models.approval import ApprovalRequest, ReleaseDecision
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot
from app.services.release_decision import effective_release_decision


def release_evidence_summary(db: Session, release: Release) -> dict:
    """Return the current evidence summary for a single Release row.

    ``release`` must be a loaded ``Release``; the caller is responsible for its
    existence and for confirming it is a STANDARD or APPLICATION release. This
    function stays read-only and raises no write side effects.
    """
    ready = _readiness_for_release(release, db, bounded=True)
    snapshot_id = ready["coverage"]["snapshot_id"]
    snapshot = db.get(ReleaseSnapshot, uuid.UUID(snapshot_id)) if snapshot_id else None

    decision = effective_release_decision(db, release.id)
    approval = (
        db.get(ApprovalRequest, decision.approval_request_id)
        if decision is not None and decision.approval_request_id
        else None
    )

    # Approval is bound to the current snapshot only when it targets this exact
    # release and its stored snapshot equals the current Readiness snapshot.
    approval_bound = bool(
        approval
        and approval.target_type == "RELEASE"
        and approval.target_id == release.id
        and snapshot
        and approval.snapshot_id == snapshot.id
    )

    # A decision is bound only when it references the current snapshot and its
    # approval is itself bound to the current snapshot.
    decision_bound = bool(
        decision and snapshot and decision.snapshot_id == snapshot.id and approval_bound
    )

    confirmed = bool(
        decision_bound
        and approval.status == "APPROVED"
        and decision.decision == "RELEASE"
        and decision.readiness_status == "READY"
        and ready["overall"] == "READY"
    )

    return {
        "release": {
            "id": str(release.id),
            "version": release.version,
            "release_type": release.release_type,
            "record_status": release.status,
        },
        "snapshot": {
            "id": str(snapshot.id),
            "snapshot_no": snapshot.snapshot_no,
            "status": snapshot.status,
            "content_hash": snapshot.content_hash,
        }
        if snapshot
        else None,
        "readiness": ready,
        "approval": {
            "approval_no": approval.approval_no,
            "status": approval.status,
            "current_snapshot_bound": approval_bound,
        }
        if approval
        else None,
        "decision": {
            "decision_no": decision.decision_no,
            "decision": decision.decision,
            "readiness_status": decision.readiness_status,
            "snapshot_id": str(decision.snapshot_id),
            "current_evidence_bound": decision_bound,
        }
        if decision
        else None,
        "current_release_confirmed": confirmed,
    }
