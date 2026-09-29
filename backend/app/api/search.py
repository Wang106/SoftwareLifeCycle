"""Bounded, read-only lookup of lifecycle identifiers and descriptions."""
from urllib.parse import quote
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.change import Issue, SoftwareChangeRequest
from app.models.core import Artifact, Customer, Project, Release, ReleaseComponent, Supplier
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.testing import DvpItem
from app.models.production import Deployment, ProductionBatch
from app.models.approval import ApprovalRequest
from app.models.distribution import DeliveryPackage, Distribution, SoftwareAuthorization
from app.models.audit import AuditEvent

router = APIRouter(prefix="/api/v1", tags=["search"])


def _pattern(query: str) -> str:
    return "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _release_path(release: Release | None, application_suffix: str = "") -> str:
    if release is None:
        return "/releases/application"
    if release.release_type == "STANDARD":
        return f"/releases/standard/{release.id}"
    return f"/releases/application/{release.id}{application_suffix}"


def _snapshot_results(db: Session, pattern: str, limit: int) -> list[dict]:
    if limit <= 0:
        return []
    rows = db.scalars(select(ReleaseSnapshot).where(or_(
        ReleaseSnapshot.snapshot_no.ilike(pattern, escape="\\"),
        ReleaseSnapshot.content_hash.ilike(pattern, escape="\\"),
    )).order_by(ReleaseSnapshot.id).limit(min(limit, 10))).all()
    releases = {row.id: row for row in db.scalars(select(Release).where(
        Release.id.in_({snapshot.release_id for snapshot in rows}))).all()} if rows else {}
    return [{"type": "Snapshot", "label": row.snapshot_no, "description": row.status,
             "href": _release_path(releases.get(row.release_id))} for row in rows]


def _frozen_artifact_results(db: Session, pattern: str, limit: int) -> list[dict]:
    if limit <= 0:
        return []
    rows = db.scalars(select(SnapshotArtifact).where(or_(
        SnapshotArtifact.filename.ilike(pattern, escape="\\"),
        SnapshotArtifact.sha256.ilike(pattern, escape="\\"),
    )).order_by(SnapshotArtifact.id).limit(min(limit, 10))).all()
    snapshots = {row.id: row for row in db.scalars(select(ReleaseSnapshot).where(
        ReleaseSnapshot.id.in_({artifact.snapshot_id for artifact in rows}))).all()} if rows else {}
    releases = {row.id: row for row in db.scalars(select(Release).where(Release.id.in_({
        snapshots[artifact.snapshot_id].release_id for artifact in rows if artifact.snapshot_id in snapshots
    }))).all()} if snapshots else {}
    return [{"type": "Frozen artifact", "label": row.filename,
             "description": f"SHA-256 {row.sha256[:12]}…",
             "href": _release_path(
                 releases.get(snapshots[row.snapshot_id].release_id) if row.snapshot_id in snapshots else None,
                 "/artifacts",
             )} for row in rows]


def _artifact_results(db: Session, pattern: str, limit: int) -> list[dict]:
    if limit <= 0:
        return []
    rows = db.scalars(select(Artifact).where(or_(
        Artifact.filename.ilike(pattern, escape="\\"),
        Artifact.sha256.ilike(pattern, escape="\\"),
    )).order_by(Artifact.id).limit(min(limit, 10))).all()
    components = {row.id: row for row in db.scalars(select(ReleaseComponent).where(
        ReleaseComponent.id.in_({artifact.release_component_id for artifact in rows}))).all()} if rows else {}
    releases = {row.id: row for row in db.scalars(select(Release).where(Release.id.in_({
        components[artifact.release_component_id].release_id for artifact in rows
        if artifact.release_component_id in components
    }))).all()} if components else {}
    return [{"type": "Artifact", "label": row.filename, "description": row.artifact_type,
             "href": _release_path(
                 releases.get(components[row.release_component_id].release_id)
                 if row.release_component_id in components else None,
                 "/artifacts",
             )} for row in rows]


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
    add(DvpItem, [DvpItem.item_no, DvpItem.title], "DVP", lambda r: r.item_no, lambda r: r.title,
        lambda r: f"/testing/dvp/{r.id}")
    results.extend(_snapshot_results(db, pattern, limit - len(results)))
    add(Release, [Release.version], "Release", lambda r: f"{r.release_type} {r.version}", lambda r: r.status,
        lambda r: f"/releases/application/{r.id}" if r.release_type == "APPLICATION"
        else f"/releases/standard/{r.id}")
    results.extend(_frozen_artifact_results(db, pattern, limit - len(results)))
    results.extend(_artifact_results(db, pattern, limit - len(results)))
    add(Customer, [Customer.code, Customer.name], "Customer", lambda r: r.name, lambda r: r.code, lambda r: f"/customers/{r.code}")
    add(Project, [Project.project_code, Project.name], "Project", lambda r: r.name, lambda r: r.project_code, lambda r: f"/projects/{r.id}")
    add(Supplier, [Supplier.code, Supplier.name], "Supplier", lambda r: r.name, lambda r: r.code, lambda r: f"/suppliers/{r.code}")
    add(ApprovalRequest, [ApprovalRequest.approval_no], "Approval", lambda r: r.approval_no, lambda r: r.status, lambda r: f"/approvals/{r.approval_no}")
    add(DeliveryPackage, [DeliveryPackage.package_no], "Delivery", lambda r: f"{r.package_no} Rev{r.revision}", lambda r: r.status, lambda r: f"/distribution/deliveries/{quote(r.package_no, safe='')}/{r.revision}")
    add(Distribution, [Distribution.distribution_no], "Distribution", lambda r: r.distribution_no, lambda r: r.status, lambda r: f"/distribution/distributions/{quote(r.distribution_no, safe='')}")
    add(SoftwareAuthorization, [SoftwareAuthorization.authorization_no], "Authorization", lambda r: r.authorization_no, lambda r: r.status, lambda r: f"/distribution/authorizations/{quote(r.authorization_no, safe='')}")
    add(Deployment, [Deployment.deployment_no], "Deployment", lambda r: r.deployment_no, lambda r: r.status, lambda r: f"/deployments/{r.deployment_no}")
    add(ProductionBatch, [ProductionBatch.batch_no], "Batch", lambda r: r.batch_no, lambda r: r.status, lambda r: f"/production/batches/{quote(r.batch_no, safe='')}")
    add(AuditEvent, [AuditEvent.event_no, AuditEvent.entity_ref], "Activity", lambda r: r.event_no, lambda r: r.summary, lambda r: f"/activity/{r.event_no}")
    return results


@router.get("/search")
def global_search(q: str = Query(min_length=1, max_length=100), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db)):
    if not q.strip():
        return {"query": q, "results": []}
    return {"query": q.strip(), "results": search_records(db, q, limit)}
