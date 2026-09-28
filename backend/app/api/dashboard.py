import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.change import Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.testing import DvpItem, DvpExecution
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release, SoftwareProduct
from app.models.snapshot import ReleaseSnapshot
from app.models.governance import PolicyException
from app.services.traceability import TraceabilityService

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


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


@router.get("/releases/application/{version}/readiness")
def release_readiness(version: str, db: Session = Depends(get_db)):
    release = _application_release(db, version)
    if not release:
        raise HTTPException(status_code=404, detail="release not found")

    coverage = TraceabilityService(db).release_coverage(release.id).as_dict()
    snapshot_id = uuid.UUID(coverage["snapshot_id"]) if coverage["snapshot_id"] else None

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

    rules = [
        {
            "group": "Change Control",
            "rule": "Required changes linked to DVP",
            "raw": "PASS" if coverage["change_coverage"] == 100 else "FAIL",
            "effective": "PASS" if coverage["change_coverage"] == 100 else "FAIL",
            "evidence": f'{coverage["change_points_covered"]} / {coverage["change_points_total"]}',
        },
        {
            "group": "Issue Control",
            "rule": "Verification-required issues linked to DVP",
            "raw": "PASS" if coverage["issue_verification_coverage"] == 100 else "FAIL",
            "effective": "PASS" if coverage["issue_verification_coverage"] == 100 else "FAIL",
            "evidence": f'{coverage["issues_covered"]} / {coverage["issues_total"]}',
        },
        {
            "group": "Verification",
            "rule": "Required DVP executed on current snapshot",
            "raw": verification_raw,
            "effective": verification_effective,
            "evidence": f'{coverage["current_snapshot_executed"]} / {coverage["required_dvp_total"]}',
        },
        {
            "group": "Software Integrity",
            "rule": "Tested snapshot equals current snapshot",
            "raw": "PASS" if coverage["snapshot_match"] else "FAIL",
            "effective": "PASS" if coverage["snapshot_match"] else "FAIL",
            "evidence": coverage["snapshot_no"] or "No snapshot",
        },
    ]

    hard_fail = any(r["effective"] == "FAIL" for r in rules)

    return {
        "overall": "NOT_READY" if hard_fail else "READY",
        "coverage": coverage,
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


@router.get("/releases/{release_id}/coverage")
def release_coverage(release_id: uuid.UUID, db: Session = Depends(get_db)):
    release = db.get(Release, release_id)
    if not release:
        raise HTTPException(status_code=404, detail="release not found")
    return TraceabilityService(db).release_coverage(release.id).as_dict()
