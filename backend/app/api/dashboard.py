import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.change import Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.testing import DvpItem, DvpExecution
from app.models.core import ApplicationReleaseDetail, Artifact, Customer, Project, Release, ReleaseComponent, SoftwareProduct
from app.models.snapshot import ReleaseSnapshot
from app.models.governance import PolicyException
from app.models.policy import ArtifactDistributionRule
from app.models.approval import ApprovalRequest, ApprovalStep, ApprovalAction, ReleaseDecision
from app.services.artifact_policy import ArtifactPolicyService
from app.services.traceability import TraceabilityService
from app.models.audit import AuditEvent

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


@router.get("/releases/application")
def list_application_releases(db: Session = Depends(get_db)):
    releases = db.scalars(select(Release).where(Release.release_type == "APPLICATION")
        .order_by(Release.created_at.desc(), Release.id.desc()).limit(200)).all()
    ids = [row.id for row in releases]
    if not ids:
        return []
    details = {row.release_id: row for row in db.scalars(
        select(ApplicationReleaseDetail).where(ApplicationReleaseDetail.release_id.in_(ids))
    ).all()}
    customer_ids = {row.customer_id for row in details.values()}
    project_ids = {row.project_id for row in details.values()}
    base_ids = {row.standard_base_release_id for row in details.values()}
    customers = {row.id: row for row in db.scalars(select(Customer).where(Customer.id.in_(customer_ids))).all()}
    projects = {row.id: row for row in db.scalars(select(Project).where(Project.id.in_(project_ids))).all()}
    bases = {row.id: row for row in db.scalars(select(Release).where(Release.id.in_(base_ids))).all()}
    snapshots = db.scalars(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id.in_(ids))
        .order_by(ReleaseSnapshot.release_id, ReleaseSnapshot.snapshot_number.desc())).all()
    latest = {}
    for snapshot in snapshots:
        latest.setdefault(snapshot.release_id, snapshot)
    return [{
        "id": str(release.id), "version": release.version, "status": release.status,
        "customer": customers[details[release.id].customer_id].name if release.id in details else None,
        "project": projects[details[release.id].project_id].name if release.id in details else None,
        "base_version": bases[details[release.id].standard_base_release_id].version if release.id in details else None,
        "snapshot_no": latest[release.id].snapshot_no if release.id in latest else None,
    } for release in releases]


@router.get("/releases/application/id/{release_id}")
def application_release_profile(release_id: uuid.UUID, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None or release.release_type != "APPLICATION":
        raise HTTPException(status_code=404, detail="application release not found")
    detail = db.get(ApplicationReleaseDetail, release.id)
    software = db.get(SoftwareProduct, release.software_id)
    customer = db.get(Customer, detail.customer_id) if detail else None
    project = db.get(Project, detail.project_id) if detail else None
    base = db.get(Release, detail.standard_base_release_id) if detail else None
    snapshot = db.scalars(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id == release.id)
        .order_by(ReleaseSnapshot.snapshot_number.desc()).limit(1)).first()
    coverage = TraceabilityService(db).release_coverage(release.id, snapshot.id if snapshot else None).as_dict() if snapshot else None
    return {
        "id": str(release.id), "version": release.version, "status": release.status,
        "release_notes": release.release_notes,
        "software": {"code": software.code, "name": software.name} if software else None,
        "customer": {"code": customer.code, "name": customer.name} if customer else None,
        "project": {"id": str(project.id), "code": project.project_code, "name": project.name} if project else None,
        "base_release": {"version": base.version, "status": base.status} if base else None,
        "snapshot": {"snapshot_no": snapshot.snapshot_no, "status": snapshot.status,
                     "content_hash": snapshot.content_hash} if snapshot else None,
        "coverage": coverage,
    }


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    active_changes = db.scalar(select(func.count()).select_from(SoftwareChangeRequest).where(
        SoftwareChangeRequest.status.notin_(["RELEASED", "CANCELLED", "CLOSED"])
    ))
    open_issues = db.scalar(select(func.count()).select_from(Issue).where(
        Issue.status.notin_(["CLOSED", "RESOLVED", "FIX_VERIFIED"])
    ))
    high_issues = db.scalar(select(func.count()).select_from(Issue).where(
        Issue.severity == "HIGH", Issue.status.notin_(["CLOSED", "RESOLVED", "FIX_VERIFIED"])
    ))
    ready_releases = db.scalar(select(func.count()).select_from(Release).where(
        Release.release_type == "APPLICATION", Release.status == "READY"
    ))
    current = db.scalars(select(Release).where(Release.release_type == "APPLICATION")
        .order_by(Release.created_at.desc(), Release.id.desc()).limit(1)).first()
    coverage = TraceabilityService(db).release_coverage(current.id).as_dict() if current else None
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at.desc(), AuditEvent.event_no.desc()).limit(5)).all()
    return {
        "active_changes": active_changes,
        "open_issues": open_issues,
        "high_open_issues": high_issues,
        "ready_releases": ready_releases,
        "current_release": {"id": str(current.id), "version": current.version, "status": current.status,
                            "snapshot_no": coverage["snapshot_no"],
                            "coverage": coverage["dvp_execution_coverage"] if coverage["snapshot_id"] else None} if current else None,
        "recent_activity": [{"event_no": event.event_no, "summary": event.summary,
                             "entity_ref": event.entity_ref, "occurred_at": event.occurred_at} for event in events],
    }


@router.get("/changes")
def list_changes(db: Session = Depends(get_db)):
    rows = db.scalars(select(SoftwareChangeRequest).order_by(SoftwareChangeRequest.created_at.desc())).all()
    return [
        {
            "id": str(row.id),
            "request_no": row.request_no,
            "title": row.title,
            "source": row.source,
            "scope": row.scope,
            "change_type": row.change_type,
            "status": row.status,
        }
        for row in rows
    ]


@router.get("/issues")
def list_issues(db: Session = Depends(get_db)):
    rows = db.scalars(select(Issue).order_by(Issue.issue_no)).all()
    return [
        {
            "id": str(row.id),
            "issue_no": row.issue_no,
            "title": row.title,
            "scope": row.scope,
            "severity": row.severity,
            "status": row.status,
            "description": row.description,
        }
        for row in rows
    ]


@router.get("/issues/{issue_no}")
def get_issue(issue_no: str, db: Session = Depends(get_db)):
    issue = db.scalars(select(Issue).where(Issue.issue_no == issue_no)).first()
    if not issue:
        raise HTTPException(status_code=404, detail="issue not found")

    relations = db.execute(
        select(IssueChangeRequestRelation, SoftwareChangeRequest)
        .join(SoftwareChangeRequest, SoftwareChangeRequest.id == IssueChangeRequestRelation.change_request_id)
        .where(IssueChangeRequestRelation.issue_id == issue.id)
    ).all()

    return {
        "id": str(issue.id),
        "issue_no": issue.issue_no,
        "title": issue.title,
        "scope": issue.scope,
        "severity": issue.severity,
        "status": issue.status,
        "description": issue.description,
        "change_requests": [
            {
                "request_no": scr.request_no,
                "title": scr.title,
                "status": scr.status,
                "relation_type": relation.relation_type,
            }
            for relation, scr in relations
        ],
    }


@router.get("/testing/dvp")
def list_dvp(db: Session = Depends(get_db)):
    items = db.scalars(select(DvpItem)).all()
    executions = db.scalars(select(DvpExecution)).all()
    latest = {}
    for execution in executions:
        key = str(execution.dvp_item_id)
        prev = latest.get(key)
        if prev is None or execution.execution_no > prev.execution_no:
            latest[key] = execution

    return [
        {
            "id": str(item.id),
            "item_no": item.item_no,
            "title": item.title,
            "scope": item.scope,
            "status": item.status,
            "latest_result": getattr(latest.get(str(item.id)), "result", None),
            "latest_execution_no": getattr(latest.get(str(item.id)), "execution_no", None),
            "snapshot_id": str(getattr(latest.get(str(item.id)), "snapshot_id", "")) or None,
        }
        for item in items
    ]


def _application_release(db: Session, version: str) -> Release | None:
    return db.scalars(
        select(Release).where(
            Release.release_type == "APPLICATION",
            Release.version == version,
        )
    ).first()


@router.get("/releases/application/{version}/overview")
def release_overview(version: str, db: Session = Depends(get_db)):
    release = _application_release(db, version)
    if not release:
        raise HTTPException(status_code=404, detail="release not found")

    detail = db.get(ApplicationReleaseDetail, release.id)
    software = db.get(SoftwareProduct, release.software_id)
    customer = db.get(Customer, detail.customer_id) if detail else None
    project = db.get(Project, detail.project_id) if detail else None
    base = db.get(Release, detail.standard_base_release_id) if detail else None
    snapshot = db.scalars(
        select(ReleaseSnapshot)
        .where(ReleaseSnapshot.release_id == release.id)
        .order_by(ReleaseSnapshot.snapshot_number.desc())
    ).first()
    coverage = TraceabilityService(db).release_coverage(release.id, snapshot.id if snapshot else None).as_dict()

    return {
        "id": str(release.id),
        "version": release.version,
        "status": release.status,
        "software": {"id": str(software.id), "name": software.name, "code": software.code} if software else None,
        "customer": {"id": str(customer.id), "name": customer.name, "code": customer.code} if customer else None,
        "project": {"id": str(project.id), "name": project.name, "code": project.project_code} if project else None,
        "base_release": {"id": str(base.id), "version": base.version} if base else None,
        "snapshot": {
            "id": str(snapshot.id),
            "snapshot_no": snapshot.snapshot_no,
            "status": snapshot.status,
            "content_hash": snapshot.content_hash,
        } if snapshot else None,
        "coverage": coverage,
    }


@router.get("/releases/application/{version}/verification")
def release_verification(version: str, db: Session = Depends(get_db)):
    release = _application_release(db, version)
    if not release:
        raise HTTPException(status_code=404, detail="release not found")

    snapshot = db.scalars(
        select(ReleaseSnapshot)
        .where(ReleaseSnapshot.release_id == release.id)
        .order_by(ReleaseSnapshot.snapshot_number.desc())
    ).first()
    coverage = TraceabilityService(db).release_coverage(release.id, snapshot.id if snapshot else None).as_dict()

    executions = db.scalars(
        select(DvpExecution).where(DvpExecution.release_id == release.id)
    ).all()
    item_ids = {e.dvp_item_id for e in executions}
    items = db.scalars(select(DvpItem).where(DvpItem.id.in_(list(item_ids)))).all() if item_ids else []
    item_map = {item.id: item for item in items}

    latest = {}
    for execution in executions:
        prev = latest.get(execution.dvp_item_id)
        if prev is None or execution.execution_no > prev.execution_no:
            latest[execution.dvp_item_id] = execution

    rows = []
    for item_id, execution in latest.items():
        item = item_map.get(item_id)
        if not item:
            continue
        rows.append({
            "item_no": item.item_no,
            "title": item.title,
            "scope": item.scope,
            "status": item.status,
            "execution_no": execution.execution_no,
            "result": execution.result,
            "snapshot_id": str(execution.snapshot_id),
            "is_current_snapshot": bool(snapshot and execution.snapshot_id == snapshot.id),
        })

    return {"coverage": coverage, "items": sorted(rows, key=lambda row: row["item_no"])}


@router.get("/releases/application/{version}/artifacts")
def release_artifacts(version: str, db: Session = Depends(get_db)):
    release = _application_release(db, version)
    if not release:
        raise HTTPException(status_code=404, detail="release not found")

    policy = ArtifactPolicyService(db)
    summary = policy.summarize_release(release.id).as_dict()
    artifacts = policy.release_artifacts(release.id)
    artifact_ids = [a.id for a in artifacts]
    rules = db.scalars(
        select(ArtifactDistributionRule).where(
            ArtifactDistributionRule.artifact_id.in_(artifact_ids)
        )
    ).all() if artifact_ids else []

    rules_by_artifact = {}
    for rule in rules:
        rules_by_artifact.setdefault(rule.artifact_id, []).append(rule)

    rows = []
    for artifact in artifacts:
        component = db.get(ReleaseComponent, artifact.release_component_id)
        rows.append({
            "id": str(artifact.id),
            "filename": artifact.filename,
            "artifact_type": artifact.artifact_type,
            "component_version": component.version if component else None,
            "sha256": artifact.sha256,
            "classification": artifact.classification,
            "distribution_level": artifact.distribution_level,
            "ai_access_policy": artifact.ai_access_policy,
            "policy_rules": [
                {
                    "recipient_type": rule.recipient_type,
                    "purpose": rule.purpose,
                    "recipient_code": rule.recipient_code,
                    "decision": rule.decision,
                }
                for rule in rules_by_artifact.get(artifact.id, [])
            ],
        })

    return {"summary": summary, "artifacts": rows}


@router.get("/releases/application/{version}/readiness")
def release_readiness(version: str, db: Session = Depends(get_db)):
    release = _application_release(db, version)
    if not release:
        raise HTTPException(status_code=404, detail="release not found")

    coverage = TraceabilityService(db).release_coverage(release.id).as_dict()
    artifact_summary = ArtifactPolicyService(db).summarize_release(release.id).as_dict()
    snapshot_id = uuid.UUID(coverage["snapshot_id"]) if coverage["snapshot_id"] else None
    snapshot = db.get(ReleaseSnapshot, snapshot_id) if snapshot_id else None

    approved_exceptions = db.scalars(
        select(PolicyException).where(
            PolicyException.snapshot_id == snapshot_id,
            PolicyException.status == "APPROVED",
        )
    ).all() if snapshot_id else []
    exception_by_rule = {x.rule_code: x for x in approved_exceptions}

    verification_raw = "PASS" if coverage["dvp_execution_coverage"] == 100 else "FAIL"
    verification_exception = exception_by_rule.get("VERIFICATION_CURRENT_SNAPSHOT_COMPLETE")
    verification_effective = (
        "PASS" if verification_raw == "PASS"
        else "EXCEPTION_GRANTED" if verification_exception
        else "FAIL"
    )

    sha_ok = artifact_summary["artifact_total"] > 0 and artifact_summary["sha_completeness"] == 100
    policy_ok = artifact_summary["artifact_total"] > 0 and artifact_summary["policy_completeness"] == 100
    snapshot_frozen = bool(snapshot and snapshot.status == "FROZEN")
    exception_scope_ok = all(x.snapshot_id == snapshot_id for x in approved_exceptions)

    rules = [
        {
            "group": "Change Control",
            "rule": "Required changes linked to DVP",
            "raw": "PASS" if coverage["change_coverage"] == 100 else "FAIL",
            "effective": "PASS" if coverage["change_coverage"] == 100 else "FAIL",
            "evidence": f'{coverage["change_points_covered"]} / {coverage["change_points_total"]}',
            "exception_allowed": True,
        },
        {
            "group": "Issue Control",
            "rule": "Verification-required issues linked to DVP",
            "raw": "PASS" if coverage["issue_verification_coverage"] == 100 else "FAIL",
            "effective": "PASS" if coverage["issue_verification_coverage"] == 100 else "FAIL",
            "evidence": f'{coverage["issues_covered"]} / {coverage["issues_total"]}',
            "exception_allowed": True,
        },
        {
            "group": "Verification",
            "rule": "Required DVP executed on current snapshot",
            "raw": verification_raw,
            "effective": verification_effective,
            "evidence": f'{coverage["current_snapshot_executed"]} / {coverage["required_dvp_total"]}',
            "exception_allowed": True,
        },
        {
            "group": "Software Integrity",
            "rule": "Tested snapshot equals current snapshot",
            "raw": "PASS" if coverage["snapshot_match"] else "FAIL",
            "effective": "PASS" if coverage["snapshot_match"] else "FAIL",
            "evidence": coverage["snapshot_no"] or "No snapshot",
            "exception_allowed": False,
        },
        {
            "group": "Software Integrity",
            "rule": "Current snapshot is frozen",
            "raw": "PASS" if snapshot_frozen else "FAIL",
            "effective": "PASS" if snapshot_frozen else "FAIL",
            "evidence": snapshot.status if snapshot else "No snapshot",
            "exception_allowed": False,
        },
        {
            "group": "Artifact Control",
            "rule": "SHA-256 complete for formal artifacts",
            "raw": "PASS" if sha_ok else "FAIL",
            "effective": "PASS" if sha_ok else "FAIL",
            "evidence": f'{artifact_summary["sha_complete"]} / {artifact_summary["artifact_total"]}',
            "exception_allowed": False,
        },
        {
            "group": "Distribution Control",
            "rule": "Artifact distribution policy complete",
            "raw": "PASS" if policy_ok else "FAIL",
            "effective": "PASS" if policy_ok else "FAIL",
            "evidence": f'{artifact_summary["policy_complete"]} / {artifact_summary["artifact_total"]}',
            "exception_allowed": False,
        },
        {
            "group": "Governance",
            "rule": "Approved exceptions are bound to current snapshot",
            "raw": "PASS" if exception_scope_ok else "FAIL",
            "effective": "PASS" if exception_scope_ok else "FAIL",
            "evidence": f'{len(approved_exceptions)} current-snapshot exception(s)',
            "exception_allowed": False,
        },
    ]

    hard_fail = any(r["effective"] == "FAIL" for r in rules)
    overall = "NOT_READY" if hard_fail else "READY"

    return {
        "overall": overall,
        "approval_eligible": overall == "READY",
        "coverage": coverage,
        "artifact_policy": artifact_summary,
        "rules": rules,
        "exceptions": [
            {
                "exception_no": x.exception_no,
                "status": x.status,
                "scope": x.scope,
                "reason": x.reason,
                "compensating_control": x.compensating_control,
                "snapshot_no": coverage["snapshot_no"],
                "rule_code": x.rule_code,
            }
            for x in approved_exceptions
        ],
    }


@router.get("/approvals")
def list_approvals(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
    ).all()
    return [
        {
            "id": str(row.id),
            "approval_no": row.approval_no,
            "target_type": row.target_type,
            "target_id": str(row.target_id),
            "snapshot_id": str(row.snapshot_id) if row.snapshot_id else None,
            "status": row.status,
            "submitted_by": row.submitted_by,
        }
        for row in rows
    ]


@router.get("/approvals/{approval_no}")
def get_approval(approval_no: str, db: Session = Depends(get_db)):
    approval = db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.approval_no == approval_no)
    ).first()
    if not approval:
        raise HTTPException(status_code=404, detail="approval not found")

    steps = db.scalars(
        select(ApprovalStep)
        .where(ApprovalStep.approval_request_id == approval.id)
        .order_by(ApprovalStep.step_order)
    ).all()
    actions = db.scalars(
        select(ApprovalAction)
        .where(ApprovalAction.approval_request_id == approval.id)
        .order_by(ApprovalAction.created_at)
    ).all()

    release = db.get(Release, approval.target_id) if approval.target_type == "RELEASE" else None
    snapshot = db.get(ReleaseSnapshot, approval.snapshot_id) if approval.snapshot_id else None

    return {
        "id": str(approval.id),
        "approval_no": approval.approval_no,
        "target_type": approval.target_type,
        "target": {
            "release_version": release.version if release else None,
            "snapshot_no": snapshot.snapshot_no if snapshot else None,
            "content_hash": snapshot.content_hash if snapshot else None,
        },
        "status": approval.status,
        "submitted_by": approval.submitted_by,
        "steps": [
            {
                "id": str(step.id),
                "step_order": step.step_order,
                "role_name": step.role_name,
                "approver_name": step.approver_name,
                "status": step.status,
            }
            for step in steps
        ],
        "actions": [
            {
                "id": str(action.id),
                "step_id": str(action.step_id) if action.step_id else None,
                "actor_name": action.actor_name,
                "action": action.action,
                "comment": action.comment,
            }
            for action in actions
        ],
    }


@router.get("/releases/application/{version}/decision")
def get_release_decision(version: str, db: Session = Depends(get_db)):
    release = _application_release(db, version)
    if not release:
        raise HTTPException(status_code=404, detail="release not found")
    decision = db.scalars(
        select(ReleaseDecision)
        .where(ReleaseDecision.release_id == release.id)
        .order_by(ReleaseDecision.decided_at.desc())
    ).first()
    if not decision:
        return {"decision": None}
    snapshot = db.get(ReleaseSnapshot, decision.snapshot_id)
    approval = db.get(ApprovalRequest, decision.approval_request_id)
    return {
        "decision": {
            "decision_no": decision.decision_no,
            "decision": decision.decision,
            "readiness_status": decision.readiness_status,
            "decided_by": decision.decided_by,
            "decision_notes": decision.decision_notes,
            "snapshot_no": snapshot.snapshot_no if snapshot else None,
            "approval_no": approval.approval_no if approval else None,
        }
    }


@router.get("/releases/{release_id}/coverage")
def release_coverage(release_id: uuid.UUID, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if not release:
        raise HTTPException(status_code=404, detail="release not found")
    return TraceabilityService(db).release_coverage(release.id).as_dict()
