"""Bounded, read-only lookup of lifecycle identifiers and descriptions."""
from urllib.parse import quote
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.change import Issue, SoftwareChangeRequest
from app.models.core import Artifact, Customer, Project, Release, Supplier
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.testing import DvpItem
from app.models.production import Deployment, ProductionBatch
from app.models.approval import ApprovalRequest
from app.models.distribution import DeliveryPackage, Distribution, SoftwareAuthorization
from app.models.audit import AuditEvent

router = APIRouter(prefix="/api/v1", tags=["search"])


def _pattern(query: str) -> str:
    return "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search_records(db: Session, query: str, limit: int) -> list[dict]:
    pattern = _pattern(query.strip())
    results: list[dict] = []

    def add(model, fields, kind, label, subtitle, href):
        remaining = limit - len(results)
        if remaining <= 0:
            return
        rows = db.scalars(
            select(model).where(or_(*(field.ilike(pattern, escape="\\") for field in fields)))
            .order_by(model.id).limit(min(remaining, 10))
        ).all()
        for row in rows:
            results.append({"type": kind, "label": label(row), "description": subtitle(row), "href": href(row)})

    add(SoftwareChangeRequest, [SoftwareChangeRequest.request_no, SoftwareChangeRequest.title], "SCR", lambda r: r.request_no, lambda r: r.title, lambda r: f"/changes/{r.request_no}")
    add(Issue, [Issue.issue_no, Issue.title], "Issue", lambda r: f"#{r.issue_no}", lambda r: r.title, lambda r: f"/issues/{r.issue_no}")
    add(DvpItem, [DvpItem.item_no, DvpItem.title], "DVP", lambda r: r.item_no, lambda r: r.title, lambda r: "/testing/dvp")
    add(ReleaseSnapshot, [ReleaseSnapshot.snapshot_no, ReleaseSnapshot.content_hash], "Snapshot", lambda r: r.snapshot_no, lambda r: r.status, lambda r: f"/releases/application/{r.release_id}")
    add(Release, [Release.version], "Release", lambda r: f"{r.release_type} {r.version}", lambda r: r.status, lambda r: f"/releases/application/{r.id}" if r.release_type == "APPLICATION" else "/releases/application")
    add(SnapshotArtifact, [SnapshotArtifact.filename, SnapshotArtifact.sha256], "Frozen artifact", lambda r: r.filename, lambda r: f"SHA-256 {r.sha256[:12]}…", lambda r: "/releases/application")
    add(Artifact, [Artifact.filename, Artifact.sha256], "Artifact", lambda r: r.filename, lambda r: r.artifact_type, lambda r: "/releases/application")
    add(Customer, [Customer.code, Customer.name], "Customer", lambda r: r.name, lambda r: r.code, lambda r: f"/customers/{r.code}")
    add(Project, [Project.project_code, Project.name], "Project", lambda r: r.name, lambda r: r.project_code, lambda r: f"/projects/{r.id}")
    add(Supplier, [Supplier.code, Supplier.name], "Supplier", lambda r: r.name, lambda r: r.code, lambda r: f"/suppliers/{r.code}")
    add(ApprovalRequest, [ApprovalRequest.approval_no], "Approval", lambda r: r.approval_no, lambda r: r.status, lambda r: f"/approvals/{r.approval_no}")
    add(DeliveryPackage, [DeliveryPackage.package_no], "Delivery", lambda r: f"{r.package_no} Rev{r.revision}", lambda r: r.status, lambda r: f"/distribution/deliveries/{quote(r.package_no, safe='')}/{r.revision}")
    add(Distribution, [Distribution.distribution_no], "Distribution", lambda r: r.distribution_no, lambda r: r.status, lambda r: "/distribution/deliveries/new")
    add(SoftwareAuthorization, [SoftwareAuthorization.authorization_no], "Authorization", lambda r: r.authorization_no, lambda r: r.status, lambda r: "/distribution/authorizations/new")
    add(Deployment, [Deployment.deployment_no], "Deployment", lambda r: r.deployment_no, lambda r: r.status, lambda r: f"/deployments/{r.deployment_no}")
    add(ProductionBatch, [ProductionBatch.batch_no], "Batch", lambda r: r.batch_no, lambda r: r.status, lambda r: f"/deployments/{db.get(Deployment, r.deployment_id).deployment_no}")
    add(AuditEvent, [AuditEvent.event_no, AuditEvent.entity_ref], "Activity", lambda r: r.event_no, lambda r: r.summary, lambda r: f"/activity/{r.event_no}")
    return results


@router.get("/search")
def global_search(q: str = Query(min_length=1, max_length=100), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db)):
    if not q.strip():
        return {"query": q, "results": []}
    return {"query": q.strip(), "results": search_records(db, q, limit)}
