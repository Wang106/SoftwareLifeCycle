import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.change import AcceptanceCriterion, ChangePoint, Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.testing import ChangePointDvpItem, DvpItem, DvpExecution, DvpPlan, TestRelease
from app.models.core import ApplicationReleaseDetail, Artifact, ComponentDefinition, Customer, Project, Release, ReleaseComponent, SoftwareProduct
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.governance import PolicyException
from app.models.policy import ArtifactDistributionRule
from app.models.snapshot_policy import SnapshotArtifactDistributionRule
from app.models.approval import ApprovalRequest, ApprovalStep, ApprovalAction, ReleaseDecision
from app.services.artifact_policy import ArtifactPolicyService
from app.services.traceability import TraceabilityService
from app.models.audit import AuditEvent
from app.models.distribution import DeliveryPackage, Distribution, SoftwareAuthorization
from app.models.production import Deployment, ProductionBatch, SoftwareChangeover

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


@router.get("/releases/application/id/{release_id}/decision")
def application_release_decision(release_id: uuid.UUID, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None or release.release_type != "APPLICATION":
        raise HTTPException(status_code=404, detail="application release not found")
    current_snapshot = db.scalars(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id == release.id)
        .order_by(ReleaseSnapshot.snapshot_number.desc()).limit(1)).first()
    decision = db.scalars(select(ReleaseDecision).where(ReleaseDecision.release_id == release.id)
        .order_by(ReleaseDecision.decided_at.desc(), ReleaseDecision.decision_no.desc()).limit(1)).first()
    if decision is None:
        return {
            "release_id": str(release.id),
            "current_snapshot_no": current_snapshot.snapshot_no if current_snapshot else None,
            "decision": None,
        }
    snapshot = db.get(ReleaseSnapshot, decision.snapshot_id)
    approval = db.get(ApprovalRequest, decision.approval_request_id)
    return {
        "release_id": str(release.id),
        "current_snapshot_no": current_snapshot.snapshot_no if current_snapshot else None,
        "decision": {
            "decision_no": decision.decision_no,
            "decision": decision.decision,
            "readiness_status": decision.readiness_status,
            "decided_by": decision.decided_by,
            "decision_notes": decision.decision_notes,
            "decided_at": decision.decided_at,
            "snapshot_id": str(decision.snapshot_id),
            "snapshot_no": snapshot.snapshot_no if snapshot else None,
            "is_current_snapshot": bool(current_snapshot and decision.snapshot_id == current_snapshot.id),
            "approval_no": approval.approval_no if approval else None,
            "approval_status": approval.status if approval else None,
        },
    }


@router.get("/releases/application/id/{release_id}/decisions")
def application_release_decisions(release_id: uuid.UUID, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None or release.release_type != "APPLICATION":
        raise HTTPException(status_code=404, detail="application release not found")
    current_snapshot = db.scalars(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id == release.id)
        .order_by(ReleaseSnapshot.snapshot_number.desc()).limit(1)).first()
    decisions = db.scalars(select(ReleaseDecision).where(ReleaseDecision.release_id == release.id)
        .order_by(ReleaseDecision.decided_at.desc(), ReleaseDecision.decision_no.desc())).all()
    rows = []
    for decision in decisions:
        snapshot = db.get(ReleaseSnapshot, decision.snapshot_id)
        approval = db.get(ApprovalRequest, decision.approval_request_id)
        rows.append({
            "decision_no": decision.decision_no,
            "decision": decision.decision,
            "readiness_status": decision.readiness_status,
            "decided_by": decision.decided_by,
            "decision_notes": decision.decision_notes,
            "decided_at": decision.decided_at,
            "snapshot_id": str(decision.snapshot_id),
            "snapshot_no": snapshot.snapshot_no if snapshot else None,
            "snapshot_content_hash": snapshot.content_hash if snapshot else None,
            "is_current_snapshot": bool(current_snapshot and decision.snapshot_id == current_snapshot.id),
            "approval_no": approval.approval_no if approval else None,
            "approval_status": approval.status if approval else None,
        })
    return {
        "release_id": str(release.id),
        "current_snapshot_no": current_snapshot.snapshot_no if current_snapshot else None,
        "decisions": rows,
    }


@router.get("/releases/application/id/{release_id}/components")
def application_release_components(release_id: uuid.UUID, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None or release.release_type != "APPLICATION":
        raise HTTPException(status_code=404, detail="application release not found")
    detail = db.get(ApplicationReleaseDetail, release.id)
    base = db.get(Release, detail.standard_base_release_id) if detail else None
    asr_components = db.scalars(select(ReleaseComponent).where(ReleaseComponent.release_id == release.id)
        .order_by(ReleaseComponent.id)).all()
    base_components = db.scalars(select(ReleaseComponent).where(ReleaseComponent.release_id == base.id)
        .order_by(ReleaseComponent.id)).all() if base else []
    definitions = {row.id: row for row in db.scalars(select(ComponentDefinition).where(
        ComponentDefinition.id.in_({row.component_definition_id for row in asr_components + base_components})
    )).all()} if asr_components or base_components else {}
    base_by_id = {row.id: row for row in base_components}
    linked_base_ids = set()
    rows = []
    for component in asr_components:
        linked = base_by_id.get(component.base_component_id)
        valid = bool(linked and linked.component_definition_id == component.component_definition_id)
        if valid:
            linked_base_ids.add(linked.id)
        definition = definitions.get(component.component_definition_id)
        rows.append({
            "id": str(component.id), "code": definition.code if definition else None,
            "name": definition.name if definition else None, "asr_version": component.version,
            "declared_delta_type": component.delta_type,
            "base_component_version": linked.version if valid else None,
            "base_link_status": "VALID" if valid else "INVALID" if component.base_component_id else "NOT_RECORDED",
        })
    return {
        "release_id": str(release.id), "version": release.version,
        "base_release": {"id": str(base.id), "version": base.version} if base else None,
        "components": rows,
        "unlinked_base_components": [{"id": str(row.id),
            "code": definitions[row.component_definition_id].code if row.component_definition_id in definitions else None,
            "name": definitions[row.component_definition_id].name if row.component_definition_id in definitions else None,
            "version": row.version} for row in base_components if row.id not in linked_base_ids],
    }


@router.get("/releases/application/id/{release_id}/evidence")
def application_release_evidence(release_id: uuid.UUID, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None or release.release_type != "APPLICATION":
        raise HTTPException(status_code=404, detail="application release not found")
    snapshot = db.scalars(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id == release.id)
        .order_by(ReleaseSnapshot.snapshot_number.desc()).limit(1)).first()
    if snapshot is None:
        return {"snapshot_no": None, "artifacts": [], "executions": [], "other_snapshot_executions": 0}

    artifacts = db.scalars(select(SnapshotArtifact).where(SnapshotArtifact.snapshot_id == snapshot.id)
        .order_by(SnapshotArtifact.component_code, SnapshotArtifact.filename)).all()
    executions = db.scalars(select(DvpExecution).where(DvpExecution.release_id == release.id)
        .order_by(DvpExecution.execution_no.desc(), DvpExecution.executed_at.desc())).all()
    latest = {}
    other_snapshot_executions = 0
    for execution in executions:
        if execution.snapshot_id == snapshot.id:
            latest.setdefault(execution.dvp_item_id, execution)
        else:
            other_snapshot_executions += 1
    items = {item.id: item for item in db.scalars(select(DvpItem).where(DvpItem.id.in_(list(latest)))).all()} if latest else {}
    return {
        "snapshot_no": snapshot.snapshot_no,
        "artifacts": [{"id": str(row.id), "component_code": row.component_code, "component_version": row.component_version,
                       "filename": row.filename, "artifact_type": row.artifact_type,
                       "sha256": row.sha256, "classification": row.classification,
                       "distribution_level": row.distribution_level, "ai_access_policy": row.ai_access_policy}
                      for row in artifacts],
        "executions": sorted([{"item_no": items[item_id].item_no, "title": items[item_id].title,
                               "execution_no": execution.execution_no, "result": execution.result,
                               "executed_at": execution.executed_at}
                              for item_id, execution in latest.items() if item_id in items], key=lambda row: row["item_no"]),
        "other_snapshot_executions": other_snapshot_executions,
    }


@router.get("/releases/application/id/{release_id}/snapshot-policy")
def application_snapshot_policy(release_id: uuid.UUID, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None or release.release_type != "APPLICATION":
        raise HTTPException(status_code=404, detail="application release not found")
    snapshot = db.scalars(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id == release.id)
        .order_by(ReleaseSnapshot.snapshot_number.desc()).limit(1)).first()
    if snapshot is None:
        return {"snapshot": None, "artifacts": []}
    artifacts = db.scalars(select(SnapshotArtifact).where(SnapshotArtifact.snapshot_id == snapshot.id)
        .order_by(SnapshotArtifact.component_code, SnapshotArtifact.filename)).all()
    ids = [artifact.id for artifact in artifacts]
    rules = db.scalars(select(SnapshotArtifactDistributionRule).where(
        SnapshotArtifactDistributionRule.snapshot_artifact_id.in_(ids)
    )).all() if ids else []
    by_artifact = {}
    for rule in rules:
        by_artifact.setdefault(rule.snapshot_artifact_id, []).append(rule)
    return {
        "snapshot": {"snapshot_no": snapshot.snapshot_no, "status": snapshot.status,
                     "content_hash": snapshot.content_hash},
        "artifacts": [{
            "id": str(artifact.id), "component_code": artifact.component_code,
            "component_version": artifact.component_version, "filename": artifact.filename,
            "artifact_type": artifact.artifact_type, "sha256": artifact.sha256,
            "classification": artifact.classification,
            "distribution_level": artifact.distribution_level,
            "ai_access_policy": artifact.ai_access_policy,
            "policy_rules": [{"recipient_type": rule.recipient_type, "purpose": rule.purpose,
                              "recipient_code": rule.recipient_code, "decision": rule.decision}
                             for rule in sorted(by_artifact.get(artifact.id, []),
                                                key=lambda row: (row.recipient_type, row.purpose,
                                                                 row.recipient_code or "", row.decision))],
        } for artifact in artifacts],
    }


@router.get("/releases/application/id/{release_id}/downstream")
def application_release_downstream(release_id: uuid.UUID, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None or release.release_type != "APPLICATION":
        raise HTTPException(status_code=404, detail="application release not found")

    packages = db.scalars(select(DeliveryPackage).where(DeliveryPackage.release_id == release_id)
        .order_by(DeliveryPackage.created_at, DeliveryPackage.package_no, DeliveryPackage.revision)).all()
    package_ids = [row.id for row in packages]
    distributions = db.scalars(select(Distribution).where(Distribution.delivery_package_id.in_(package_ids))
        .order_by(Distribution.distribution_no)).all() if package_ids else []
    authorizations = db.scalars(select(SoftwareAuthorization).where(SoftwareAuthorization.release_id == release_id)
        .order_by(SoftwareAuthorization.authorization_no)).all()
    authorization_ids = [row.id for row in authorizations]
    deployments = db.scalars(select(Deployment).where(Deployment.authorization_id.in_(authorization_ids))
        .order_by(Deployment.created_at, Deployment.deployment_no)).all() if authorization_ids else []
    deployment_ids = [row.id for row in deployments]
    changeovers = db.scalars(select(SoftwareChangeover).where(SoftwareChangeover.deployment_id.in_(deployment_ids))
        .order_by(SoftwareChangeover.changeover_no)).all() if deployment_ids else []
    batches = db.scalars(select(ProductionBatch).where(ProductionBatch.deployment_id.in_(deployment_ids))
        .order_by(ProductionBatch.batch_no)).all() if deployment_ids else []

    # Each row retains its direct parent and snapshot reference; related records are not
    # treated as proof of a matching actual deployment or production batch.
    snapshot_ids = {row.snapshot_id for row in packages + authorizations + batches}
    snapshot_ids.update(row.expected_snapshot_id for row in deployments)
    snapshot_ids.update(row.actual_snapshot_id for row in deployments if row.actual_snapshot_id)
    snapshots = {row.id: row.snapshot_no for row in db.scalars(
        select(ReleaseSnapshot).where(ReleaseSnapshot.id.in_(snapshot_ids))
    ).all()} if snapshot_ids else {}
    package_by_id = {row.id: row for row in packages}
    distribution_by_id = {row.id: row for row in distributions}
    return {
        "deliveries": [{"id": str(row.id), "package_no": row.package_no, "revision": row.revision,
                        "status": row.status, "snapshot_no": snapshots.get(row.snapshot_id),
                        "recipient_code": row.recipient_code} for row in packages],
        "distributions": [{"id": str(row.id), "distribution_no": row.distribution_no, "status": row.status,
                           "package_no": package_by_id[row.delivery_package_id].package_no,
                           "package_revision": package_by_id[row.delivery_package_id].revision,
                           "recipient_code": row.recipient_code} for row in distributions],
        "authorizations": [{"id": str(row.id), "authorization_no": row.authorization_no, "status": row.status,
                            "snapshot_no": snapshots.get(row.snapshot_id),
                            "distribution_no": distribution_by_id[row.distribution_id].distribution_no
                            if row.distribution_id in distribution_by_id else None,
                            "site_code": row.site_code, "line_code": row.line_code,
                            "batch_limit": row.batch_limit} for row in authorizations],
        "deployments": [{"id": str(row.id), "deployment_no": row.deployment_no, "status": row.status,
                         "authorization_no": next(auth.authorization_no for auth in authorizations if auth.id == row.authorization_id),
                         "expected_snapshot_no": snapshots.get(row.expected_snapshot_id),
                         "actual_snapshot_no": snapshots.get(row.actual_snapshot_id),
                         "actual_release_matches": row.actual_release_id == release_id if row.actual_release_id else None}
                        for row in deployments],
        "changeovers": [{"id": str(row.id), "changeover_no": row.changeover_no, "status": row.status,
                         "deployment_no": next(dep.deployment_no for dep in deployments if dep.id == row.deployment_id)}
                        for row in changeovers],
        "batches": [{"id": str(row.id), "batch_no": row.batch_no, "status": row.status,
                     "deployment_no": next(dep.deployment_no for dep in deployments if dep.id == row.deployment_id),
                     "snapshot_no": snapshots.get(row.snapshot_id), "release_matches": row.release_id == release_id}
                    for row in batches],
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


@router.get("/changes/{request_no}")
def change_detail(request_no: str, db: Session = Depends(get_db)):
    change = db.scalars(select(SoftwareChangeRequest).where(
        SoftwareChangeRequest.request_no == request_no
    )).first()
    if change is None:
        raise HTTPException(status_code=404, detail="change request not found")
    software = db.get(SoftwareProduct, change.software_id)
    customer = db.get(Customer, change.customer_id) if change.customer_id else None
    project = db.get(Project, change.project_id) if change.project_id else None
    criteria = db.scalars(select(AcceptanceCriterion).where(
        AcceptanceCriterion.change_request_id == change.id
    ).order_by(AcceptanceCriterion.criterion_no)).all()
    points = db.scalars(select(ChangePoint).where(
        ChangePoint.change_request_id == change.id
    ).order_by(ChangePoint.change_no)).all()
    issue_links = db.execute(select(IssueChangeRequestRelation, Issue)
        .join(Issue, Issue.id == IssueChangeRequestRelation.issue_id)
        .where(IssueChangeRequestRelation.change_request_id == change.id)).all()
    plans = db.scalars(select(DvpPlan).where(DvpPlan.change_request_id == change.id)
        .order_by(DvpPlan.plan_no)).all()
    items = db.scalars(select(DvpItem).where(DvpItem.plan_id.in_(
        [plan.id for plan in plans]
    )).order_by(DvpItem.item_no)).all() if plans else []
    item_by_id = {item.id: item for item in items}
    point_links = db.scalars(select(ChangePointDvpItem).where(
        ChangePointDvpItem.change_point_id.in_([point.id for point in points])
    )).all() if points else []
    missing_item_ids = {link.dvp_item_id for link in point_links} - item_by_id.keys()
    if missing_item_ids:
        item_by_id.update({item.id: item for item in db.scalars(select(DvpItem).where(
            DvpItem.id.in_(missing_item_ids)
        )).all()})
    linked_items = {}
    for link in point_links:
        if link.dvp_item_id in item_by_id:
            linked_items.setdefault(link.change_point_id, []).append(item_by_id[link.dvp_item_id])
    return {
        "id": str(change.id), "request_no": change.request_no, "title": change.title,
        "source": change.source, "scope": change.scope, "change_type": change.change_type,
        "status": change.status, "background": change.background,
        "requirement": change.requirement, "created_at": change.created_at,
        "software": {"code": software.code, "name": software.name} if software else None,
        "customer": {"code": customer.code, "name": customer.name} if customer else None,
        "project": {"id": str(project.id), "code": project.project_code,
                    "name": project.name} if project else None,
        "acceptance_criteria": [{"criterion_no": row.criterion_no, "description": row.description}
                                for row in criteria],
        "issues": [{"issue_no": issue.issue_no, "title": issue.title,
                    "relation_type": link.relation_type, "status": issue.status}
                   for link, issue in issue_links],
        "change_points": [{"change_no": point.change_no, "title": point.title,
                           "description": point.description, "status": point.status,
                           "dvp_items": [{"id": str(item.id), "item_no": item.item_no}
                                         for item in linked_items.get(point.id, [])]}
                          for point in points],
        "dvp_plans": [{"plan_no": plan.plan_no, "title": plan.title, "status": plan.status,
                       "items": [{"id": str(item.id), "item_no": item.item_no,
                                  "title": item.title, "status": item.status}
                                 for item in items if item.plan_id == plan.id]}
                      for plan in plans],
    }


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
            "snapshot_id": str(latest[str(item.id)].snapshot_id) if str(item.id) in latest else None,
        }
        for item in items
    ]


@router.get("/testing/dvp/id/{item_id}")
def dvp_item_detail(item_id: uuid.UUID, db: Session = Depends(get_db)):
    item = db.get(DvpItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="DVP item not found")
    plan = db.get(DvpPlan, item.plan_id)
    change = db.get(SoftwareChangeRequest, plan.change_request_id) if plan else None
    executions = db.scalars(
        select(DvpExecution).where(DvpExecution.dvp_item_id == item.id)
        .order_by(DvpExecution.execution_no)
    ).all()
    history = []
    for execution in executions:
        release = db.get(Release, execution.release_id)
        snapshot = db.get(ReleaseSnapshot, execution.snapshot_id)
        test_release = db.get(TestRelease, execution.test_release_id) if execution.test_release_id else None
        history.append({
            "execution_no": execution.execution_no,
            "result": execution.result,
            "actual_result": execution.actual_result,
            "executed_at": execution.executed_at,
            "release_id": str(execution.release_id),
            "release_version": release.version if release else None,
            "release_type": release.release_type if release else None,
            "snapshot_id": str(execution.snapshot_id),
            "snapshot_no": snapshot.snapshot_no if snapshot else None,
            "test_release_no": test_release.test_release_no if test_release else None,
        })
    return {
        "id": str(item.id), "item_no": item.item_no, "title": item.title,
        "scope": item.scope, "status": item.status,
        "plan": {"plan_no": plan.plan_no, "title": plan.title,
                 "change_request_no": change.request_no if change else None} if plan else None,
        "executions": history,
    }


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
    return _readiness_for_release(release, db)


@router.get("/releases/application/id/{release_id}/readiness")
def application_release_readiness(release_id: uuid.UUID, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if release is None or release.release_type != "APPLICATION":
        raise HTTPException(status_code=404, detail="application release not found")
    return _readiness_for_release(release, db)


def _readiness_for_release(release: Release, db: Session):

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
        "target_id": str(approval.target_id),
        "target": {
            "release_type": release.release_type if release else None,
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
