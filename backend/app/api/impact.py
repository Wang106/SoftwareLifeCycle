"""Read-only candidate release trace for an issue.

A shared software product is a review lead, not proof of release impact.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.change import Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release, SoftwareProduct
from app.models.production import Deployment, ProductionBatch

router = APIRouter(prefix="/api/v1/issues", tags=["impact"])


@router.get("/{issue_no}/impact")
def issue_impact(issue_no: str, db: Session = Depends(get_db)):
    issue = db.scalars(select(Issue).where(Issue.issue_no == issue_no)).first()
    if issue is None:
        raise HTTPException(status_code=404, detail="issue not found")

    linked = db.execute(select(IssueChangeRequestRelation, SoftwareChangeRequest)
        .join(SoftwareChangeRequest, SoftwareChangeRequest.id == IssueChangeRequestRelation.change_request_id)
        .where(IssueChangeRequestRelation.issue_id == issue.id)).all()
    changes = [scr for _, scr in linked]
    software_ids = {scr.software_id for scr in changes}
    if not software_ids:
        return {"issue_no": issue.issue_no, "linked_changes": [], "candidate_releases": [],
                "truncated": False, "basis": "No linked SCR; release impact cannot be inferred."}

    products = {p.id: p for p in db.scalars(select(SoftwareProduct).where(SoftwareProduct.id.in_(software_ids))).all()}
    releases = db.scalars(select(Release).where(Release.software_id.in_(software_ids))
        .order_by(Release.created_at.desc(), Release.id.desc()).limit(201)).all()
    truncated = len(releases) > 200
    releases = releases[:200]
    release_ids = [release.id for release in releases]
    details = {d.release_id: d for d in db.scalars(select(ApplicationReleaseDetail)
        .where(ApplicationReleaseDetail.release_id.in_(release_ids))).all()} if release_ids else {}
    customer_ids = {d.customer_id for d in details.values()}
    project_ids = {d.project_id for d in details.values()}
    customers = {c.id: c for c in db.scalars(select(Customer).where(Customer.id.in_(customer_ids))).all()} if customer_ids else {}
    projects = {p.id: p for p in db.scalars(select(Project).where(Project.id.in_(project_ids))).all()} if project_ids else {}
    deployments = db.scalars(select(Deployment).where(Deployment.actual_release_id.in_(release_ids))).all() if release_ids else []
    batches = db.scalars(select(ProductionBatch).where(ProductionBatch.release_id.in_(release_ids))).all() if release_ids else []
    deployment_count = {}
    batch_count = {}
    for deployment in deployments:
        deployment_count[deployment.actual_release_id] = deployment_count.get(deployment.actual_release_id, 0) + 1
    for batch in batches:
        batch_count[batch.release_id] = batch_count.get(batch.release_id, 0) + 1

    return {
        "issue_no": issue.issue_no,
        "linked_changes": [{"request_no": scr.request_no, "title": scr.title,
                            "relation_type": relation.relation_type, "status": scr.status}
                           for relation, scr in linked],
        "candidate_releases": [{
            "id": str(release.id), "release_type": release.release_type,
            "version": release.version, "status": release.status,
            "software": {"code": products[release.software_id].code,
                         "name": products[release.software_id].name},
            "customer": customers[details[release.id].customer_id].name if release.id in details else None,
            "project": projects[details[release.id].project_id].name if release.id in details else None,
            "deployment_count": deployment_count.get(release.id, 0),
            "batch_count": batch_count.get(release.id, 0),
        } for release in releases if release.software_id in products],
        "truncated": truncated,
        "basis": "Candidate releases share a software product with a linked SCR. Actual issue impact requires review.",
    }
