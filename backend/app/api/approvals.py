from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.approval import ApprovalError, ApprovalService
from app.authorization import authorize_approval
from app.actor import resolve_actor

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


class ApprovalActionRequest(BaseModel):
    actor: str
    action: str
    comment: str | None = None


class ReleaseDecisionRequest(BaseModel):
    decision_no: str
    decided_by: str
    readiness_status: str
    decision: str
    notes: str | None = None


@router.post("/{approval_no}/actions")
def approval_action(
    approval_no: str,
    payload: ApprovalActionRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    authorize_approval(request, db, approval_no, "REVIEWER")
    actor = resolve_actor(request, payload.actor)
    try:
        approval = ApprovalService(db).act(
            approval_no=approval_no,
            actor=payload.actor,
            action=payload.action,
            comment=payload.comment,
            actor_context=actor,
        )
        return {"approval_no": approval.approval_no, "status": approval.status}
    except ApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{approval_no}/release-decision", status_code=201)
def create_release_decision(
    approval_no: str,
    payload: ReleaseDecisionRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    authorize_approval(request, db, approval_no, "RELEASE_AUTHORITY")
    actor = resolve_actor(request, payload.decided_by)
    try:
        row = ApprovalService(db).create_release_decision(
            approval_no=approval_no,
            decision_no=payload.decision_no,
            decided_by=payload.decided_by,
            readiness_status=payload.readiness_status,
            decision=payload.decision,
            notes=payload.notes,
            actor_context=actor,
        )
        return {
            "decision_no": row.decision_no,
            "decision": row.decision,
            "release_id": str(row.release_id),
            "snapshot_id": str(row.snapshot_id),
        }
    except ApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
