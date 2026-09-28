from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalAction, ApprovalRequest, ApprovalStep, ReleaseDecision
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot


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

    def act(self, approval_no: str, actor: str, action: str, comment: str | None = None):
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
        if step.status == "WAITING":
            step.status = "PENDING"

        if action not in ("APPROVED", "RETURNED", "REJECTED"):
            raise ApprovalError("Unsupported approval action")

        step.status = action
        step.approver_name = actor
        self.db.add(
            ApprovalAction(
                approval_request_id=approval.id,
                step_id=step.id,
                actor_name=actor,
                action=action,
                comment=comment,
            )
        )

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

        self.db.commit()
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
    ):
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
            decided_by=decided_by,
            decision_notes=notes,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
