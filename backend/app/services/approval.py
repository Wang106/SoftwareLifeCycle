from datetime import datetime, timezone
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalAction, ApprovalRequest, ApprovalStep, ReleaseDecision
from app.models.core import Release
from app.models.audit import AuditEvent
from app.models.snapshot import ReleaseSnapshot
from app.actor import ActorContext
from app.services.audit import commit_with_audit
from app.services.command_retry import atomic_command, retry_result
from app.services.release_decision import effective_release_decision


class ApprovalError(ValueError):
    pass


@dataclass(frozen=True)
class ApprovalOutcome:
    """Stable action response, independent of later workflow transitions."""
    id: object
    approval_no: str
    status: str


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
            .with_for_update().execution_options(populate_existing=True)
        ).first()

    def act(
        self,
        approval_no: str,
        actor: str,
        action: str,
        comment: str | None = None,
        actor_context: ActorContext | None = None,
        request_id=None,
        expected_step_id=None,
    ):
        with atomic_command(self.db, ApprovalError):
            return self._act(approval_no, actor, action, comment, actor_context,
                             request_id, expected_step_id)

    def _act(self, approval_no, actor, action, comment, actor_context,
             request_id, expected_step_id):
        resolved_actor = actor_context or ActorContext.legacy(actor)
        approval = self.db.scalars(
            select(ApprovalRequest).where(ApprovalRequest.approval_no == approval_no)
            .with_for_update().execution_options(populate_existing=True)
        ).first()
        if not approval:
            raise ApprovalError("Approval request not found")
        if request_id is not None and expected_step_id is None:
            raise ApprovalError("request_id requires expected_step_id")
        request_content = {
            "approval_no": approval_no, "actor": actor, "action": action,
            "comment": comment,
            "expected_step_id": str(expected_step_id) if expected_step_id else None,
        }
        existing = retry_result(self.db, ApprovalAction, request_id, "EVT-AP-",
            request_content, resolved_actor, ApprovalError, event_entity_id=approval.id)
        if existing is not None:
            event = self.db.scalar(select(AuditEvent).where(
                AuditEvent.event_no == f"EVT-AP-{request_id.hex}"))
            outcome = ApprovalOutcome(approval.id, approval.approval_no,
                                      event.payload_json["after_status"])
            self.db.commit()
            return outcome
        if approval.status in ("APPROVED", "REJECTED", "RETURNED", "CANCELLED"):
            raise ApprovalError("Approval request is already closed")

        step = self.current_step(approval)
        if not step:
            raise ApprovalError("No active approval step")
        if expected_step_id is not None and step.id != expected_step_id:
            raise ApprovalError("expected_step_id does not match the active approval step")
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
        if request_id is not None:
            history.id = request_id
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
                .with_for_update().execution_options(populate_existing=True)
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
                "actor_source": resolved_actor.source,
                "request": request_content if request_id is not None else None},
        ))
        return ApprovalOutcome(approval.id, approval.approval_no, approval.status)

    def create_release_decision(
        self,
        approval_no: str,
        decision_no: str,
        decided_by: str,
        readiness_status: str,
        decision: str,
        notes: str | None = None,
        actor_context: ActorContext | None = None,
        request_id=None,
        supersedes_id=None,
        correction_reason: str | None = None,
    ):
        with atomic_command(self.db, ApprovalError):
            return self._create_release_decision(approval_no, decision_no, decided_by,
                readiness_status, decision, notes, actor_context, request_id,
                supersedes_id, correction_reason)

    def _create_release_decision(self, approval_no, decision_no, decided_by,
                                 readiness_status, decision, notes, actor_context, request_id,
                                 supersedes_id, correction_reason):
        resolved_actor = actor_context or ActorContext.legacy(decided_by)
        # Release precedes ApprovalRequest: delivery/authorization latest-decision
        # checks share this lock, while actions only acquire ApprovalRequest.
        self.db.scalar(select(Release).join(
            ApprovalRequest, ApprovalRequest.target_id == Release.id
        ).where(ApprovalRequest.approval_no == approval_no,
                ApprovalRequest.target_type == "RELEASE")
          .with_for_update(of=Release).execution_options(populate_existing=True))
        approval = self.db.scalars(
            select(ApprovalRequest).where(ApprovalRequest.approval_no == approval_no)
            .with_for_update().execution_options(populate_existing=True)
        ).first()
        if not approval:
            raise ApprovalError("Approval request not found")
        request_content = {
            "approval_no": approval_no, "decision_no": decision_no, "decided_by": decided_by,
            "readiness_status": readiness_status, "decision": decision, "notes": notes,
            "supersedes_id": str(supersedes_id) if supersedes_id else None,
            "correction_reason": correction_reason,
        }
        existing = retry_result(self.db, ReleaseDecision, request_id, "EVT-RD-",
                                request_content, resolved_actor, ApprovalError)
        if existing is not None:
            self.db.commit()
            return existing
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
        if (supersedes_id is None) != (correction_reason is None):
            raise ApprovalError("supersedes_id and correction_reason must be supplied together")
        if correction_reason is not None:
            correction_reason = correction_reason.strip()
            if not correction_reason or len(correction_reason) > 4000:
                raise ApprovalError("correction_reason must contain 1 to 4000 characters")
            if request_id is not None and supersedes_id == request_id:
                raise ApprovalError("A release decision cannot supersede itself")
            current = effective_release_decision(self.db, release.id)
            if current is None or current.id != supersedes_id:
                raise ApprovalError("supersedes_id is not the current effective release decision")
            if current.snapshot_id != snapshot.id:
                raise ApprovalError("Supersession must retain the predecessor snapshot")
            if current.approval_request_id == approval.id:
                raise ApprovalError("Supersession requires a new approved request")

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
            supersedes_id=supersedes_id,
            correction_reason=correction_reason,
            decided_at=datetime.now(timezone.utc),
        )
        if request_id is not None:
            row.id = request_id
        self.db.add(row)
        commit_with_audit(self.db, lambda: dict(
            event_no=f"EVT-RD-{row.id.hex}", event_type="RELEASE",
            action="DECISION_SUPERSEDED" if row.supersedes_id else "DECISION_RECORDED",
            entity_type="RELEASE_DECISION", entity_id=row.id, entity_ref=row.decision_no,
            **resolved_actor.audit_fields(),
            summary="Release decision recorded", detail=notes,
            occurred_at=row.decided_at,
            payload={"decision": row.decision, "readiness_status": row.readiness_status,
                "release_id": str(row.release_id), "snapshot_id": str(row.snapshot_id),
                "snapshot_no": snapshot.snapshot_no, "content_hash": snapshot.content_hash,
                "approval_id": str(approval.id), "approval_no": approval.approval_no,
                "supersedes_id": str(row.supersedes_id) if row.supersedes_id else None,
                "correction_reason": row.correction_reason,
                "actor_source": resolved_actor.source,
                "request": request_content if request_id is not None else None},
        ))
        self.db.refresh(row)
        return row
