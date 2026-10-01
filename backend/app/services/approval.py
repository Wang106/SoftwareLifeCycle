from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalAction, ApprovalRequest, ApprovalStep, ReleaseDecision
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot
from app.actor import ActorContext
from app.services.audit import commit_with_audit


class ApprovalError(ValueError):
    pass


class ApprovalService:
    def __init__(self, db: Session):
        self.db = db

    def current_step(self, approval: ApprovalRequest):
        return self.db.scalars(
            select(ApprovalStep)
            .where(
                ApprovalStep.approval_request_id == approval.id,
                ApprovalStep.status.in_(["PENDING", "WAITING"]),
            )
            .order_by(ApprovalStep.step_order)
        ).first()

    def act(
        self,
        approval_no: str,
        actor: str,
        action: str,
        comment: str | None = None,
        actor_context: ActorContext | None = None,
    ):
        resolved_actor = actor_context or ActorContext.legacy(actor)
        approval = self.db.scalars(
            select(ApprovalRequest).where(ApprovalRequest.approval_no == approval_no)
        ).first()
        if not approval:
            raise ApprovalError("Approval request not found")
        if approval.status in ("APPROVED", "REJECTED", "RETURNED", "CANCELLED"):
            raise ApprovalError("Approval request is already closed")

        step = self.current_step(approval)
        if not step:
            raise ApprovalError("No active approval step")
        if action not in ("APPROVED", "RETURNED", "REJECTED"):
            raise ApprovalError("Unsupported approval action")

        before_status = approval.status
        before_step_status = step.status
        step.status = action
        step.decided_at = datetime.now(timezone.utc)
        step.approver_name = resolved_actor.name
        history = ApprovalAction(
            approval_request_id=approval.id, step_id=step.id,
            actor_name=resolved_actor.name, action=action, comment=comment,
            created_at=step.decided_at,
        )
        self.db.add(history)

        if action in ("RETURNED", "REJECTED"):
            approval.status = action
        else:
            next_step = self.db.scalars(
                select(ApprovalStep)
                .where(
                    ApprovalStep.approval_request_id == approval.id,
                    ApprovalStep.step_order > step.step_order,
                )
                .order_by(ApprovalStep.step_order)
            ).first()
            if next_step:
                next_step.status = "PENDING"
                approval.status = "PENDING"
            else:
                approval.status = "APPROVED"

        commit_with_audit(self.db, lambda: dict(
            event_no=f"EVT-AP-{history.id.hex}", event_type="APPROVAL", action=action,
            entity_type="APPROVAL_REQUEST", entity_id=approval.id, entity_ref=approval.approval_no,
            **resolved_actor.audit_fields(),
            summary=f"Approval {action.lower()}", detail=comment,
            occurred_at=history.created_at,
            payload={"approval_action_id": str(history.id), "step_id": str(step.id),
                "step_order": step.step_order, "role_name": step.role_name,
                "target_type": approval.target_type, "target_id": str(approval.target_id),
                "snapshot_id": str(approval.snapshot_id) if approval.snapshot_id else None,
                "before_status": before_status, "after_status": approval.status,
                "before_step_status": before_step_status, "after_step_status": step.status,
                "actor_source": resolved_actor.source},
        ))
        self.db.refresh(approval)
        return approval

    def create_release_decision(
        self,
        approval_no: str,
        decision_no: str,
        decided_by: str,
        readiness_status: str,
        decision: str,
        notes: str | None = None,
        actor_context: ActorContext | None = None,
    ):
        resolved_actor = actor_context or ActorContext.legacy(decided_by)
        approval = self.db.scalars(
            select(ApprovalRequest).where(ApprovalRequest.approval_no == approval_no)
        ).first()
        if not approval:
            raise ApprovalError("Approval request not found")
        if approval.target_type != "RELEASE":
            raise ApprovalError("Approval target is not a release")
        if approval.status != "APPROVED":
            raise ApprovalError("Release decision requires an approved request")
        if not approval.snapshot_id:
            raise ApprovalError("Release approval must be bound to a snapshot")

        release = self.db.get(Release, approval.target_id)
        snapshot = self.db.get(ReleaseSnapshot, approval.snapshot_id)
        if not release or not snapshot or snapshot.release_id != release.id:
            raise ApprovalError("Approval target snapshot does not match release")

        existing = self.db.scalars(
            select(ReleaseDecision).where(ReleaseDecision.decision_no == decision_no)
        ).first()
        if existing:
            raise ApprovalError("Decision number already exists")

        row = ReleaseDecision(
            decision_no=decision_no,
            release_id=release.id,
            snapshot_id=snapshot.id,
            approval_request_id=approval.id,
            readiness_status=readiness_status,
            decision=decision,
            decided_by=resolved_actor.name,
            decision_notes=notes,
            decided_at=datetime.now(timezone.utc),
        )
        self.db.add(row)
        commit_with_audit(self.db, lambda: dict(
            event_no=f"EVT-RD-{row.id.hex}", event_type="RELEASE", action="DECISION_RECORDED",
            entity_type="RELEASE_DECISION", entity_id=row.id, entity_ref=row.decision_no,
            **resolved_actor.audit_fields(),
            summary="Release decision recorded", detail=notes,
            occurred_at=row.decided_at,
            payload={"decision": row.decision, "readiness_status": row.readiness_status,
                "release_id": str(row.release_id), "snapshot_id": str(row.snapshot_id),
                "snapshot_no": snapshot.snapshot_no, "content_hash": snapshot.content_hash,
                "approval_id": str(approval.id), "approval_no": approval.approval_no,
                "actor_source": resolved_actor.source},
        ))
        self.db.refresh(row)
        return row
