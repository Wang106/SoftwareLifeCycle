import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.core import Customer, Project, Release
from app.models.distribution import DeliveryPackage, Distribution, SoftwareAuthorization
from app.models.approval import ApprovalRequest, ReleaseDecision
from app.models.production import (
    Deployment,
    ManufacturingSite,
    ProductionBatch,
    ProductionLine,
    SoftwareChangeover,
)
from app.models.snapshot import ReleaseSnapshot
from app.services.production import ProductionError, ProductionService


router = APIRouter(prefix="/api/v1", tags=["production"])


class DeploymentCreate(BaseModel):
    deployment_no: str
    authorization_id: uuid.UUID
    production_line_id: uuid.UUID


class ActualSoftwareReport(BaseModel):
    actual_release_id: uuid.UUID
    actual_snapshot_id: uuid.UUID
    deployed_at: datetime | None = None


class ChangeoverCreate(BaseModel):
    changeover_no: str
    from_release_id: uuid.UUID
    changed_at: datetime | None = None
    note: str | None = None


class BatchCreate(BaseModel):
    batch_no: str
    changeover_id: uuid.UUID | None = None
    started_at: datetime | None = None
    note: str | None = None


def _release_ref(db: Session, release_id, snapshot_id):
    release = db.get(Release, release_id) if release_id else None
    snapshot = db.get(ReleaseSnapshot, snapshot_id) if snapshot_id else None
    return {
        "release_id": str(release.id) if release else None,
        "version": release.version if release else None,
        "snapshot_id": str(snapshot.id) if snapshot else None,
        "snapshot_no": snapshot.snapshot_no if snapshot else None,
    }


def _deployment_detail(db: Session, deployment: Deployment):
    authorization = db.get(SoftwareAuthorization, deployment.authorization_id)
    line = db.get(ProductionLine, deployment.production_line_id)
    site = db.get(ManufacturingSite, line.site_id) if line else None
    project = db.get(Project, site.project_id) if site else None
    customer = db.get(Customer, site.customer_id) if site else None
    changeovers = db.scalars(
        select(SoftwareChangeover)
        .where(SoftwareChangeover.deployment_id == deployment.id)
        .order_by(SoftwareChangeover.changed_at)
    ).all()
    batches = db.scalars(
        select(ProductionBatch)
        .where(ProductionBatch.deployment_id == deployment.id)
        .order_by(ProductionBatch.started_at)
    ).all()
    return {
        "id": str(deployment.id),
        "deployment_no": deployment.deployment_no,
        "status": deployment.status,
        "authorization": {
            "id": str(authorization.id),
            "authorization_no": authorization.authorization_no,
            "status": authorization.status,
        } if authorization else None,
        "customer": {
            "id": str(customer.id),
            "code": customer.code,
            "name": customer.name,
        } if customer else None,
        "project": {
            "id": str(project.id),
            "code": project.project_code,
            "name": project.name,
        } if project else None,
        "site": {
            "id": str(site.id),
            "site_code": site.site_code,
            "name": site.name,
        } if site else None,
        "line": {
            "id": str(line.id),
            "line_code": line.line_code,
            "name": line.name,
        } if line else None,
        "expected": _release_ref(
            db, deployment.expected_release_id, deployment.expected_snapshot_id
        ),
        "actual": _release_ref(
            db, deployment.actual_release_id, deployment.actual_snapshot_id
        ) if deployment.actual_release_id and deployment.actual_snapshot_id else None,
        "deployed_at": deployment.deployed_at,
        "changeovers": [
            {
                "id": str(row.id),
                "changeover_no": row.changeover_no,
                "from_version": db.get(Release, row.from_release_id).version,
                "to_version": db.get(Release, row.to_release_id).version,
                "status": row.status,
                "changed_at": row.changed_at,
                "note": row.note,
            }
            for row in changeovers
        ],
        "batches": [
            {
                "id": str(row.id),
                "batch_no": row.batch_no,
                "status": row.status,
                "release_version": db.get(Release, row.release_id).version,
                "snapshot_no": db.get(ReleaseSnapshot, row.snapshot_id).snapshot_no,
                "started_at": row.started_at,
                "ended_at": row.ended_at,
                "note": row.note,
            }
            for row in batches
        ],
    }


@router.get("/manufacturing/sites")
def list_sites(db: Session = Depends(get_db)):
    sites = db.scalars(select(ManufacturingSite).order_by(ManufacturingSite.name)).all()
    return [
        {
            "id": str(site.id),
            "site_code": site.site_code,
            "name": site.name,
            "region": site.region,
            "status": site.status,
            "line_count": len(db.scalars(
                select(ProductionLine).where(ProductionLine.site_id == site.id)
            ).all()),
        }
        for site in sites
    ]


@router.get("/manufacturing/sites/{site_code}")
def get_site(site_code: str, db: Session = Depends(get_db)):
    site = db.scalars(
        select(ManufacturingSite).where(ManufacturingSite.site_code == site_code)
    ).first()
    if not site:
        raise HTTPException(status_code=404, detail="manufacturing site not found")
    customer = db.get(Customer, site.customer_id)
    project = db.get(Project, site.project_id)
    lines = db.scalars(
        select(ProductionLine)
        .where(ProductionLine.site_id == site.id)
        .order_by(ProductionLine.name)
    ).all()
    line_rows = []
    for line in lines:
        deployment = db.scalars(
            select(Deployment)
            .where(Deployment.production_line_id == line.id)
            .order_by(Deployment.created_at.desc())
        ).first()
        line_rows.append({
            "id": str(line.id),
            "line_code": line.line_code,
            "name": line.name,
            "status": line.status,
            "deployment": _deployment_detail(db, deployment) if deployment else None,
        })
    return {
        "id": str(site.id),
        "site_code": site.site_code,
        "name": site.name,
        "region": site.region,
        "status": site.status,
        "customer": {"code": customer.code, "name": customer.name} if customer else None,
        "project": {"code": project.project_code, "name": project.name} if project else None,
        "lines": line_rows,
    }


@router.get("/deployments")
def list_deployments(db: Session = Depends(get_db)):
    rows = db.scalars(select(Deployment).order_by(Deployment.created_at.desc())).all()
    return [_deployment_detail(db, row) for row in rows]


@router.get("/deployments/{deployment_no}")
def get_deployment(deployment_no: str, db: Session = Depends(get_db)):
    row = db.scalars(
        select(Deployment).where(Deployment.deployment_no == deployment_no)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="deployment not found")
    return _deployment_detail(db, row)


@router.get("/deployments/{deployment_no}/provenance")
def get_deployment_provenance(deployment_no: str, db: Session = Depends(get_db)):
    deployment = db.scalars(select(Deployment).where(Deployment.deployment_no == deployment_no)).first()
    if deployment is None:
        raise HTTPException(status_code=404, detail="deployment not found")
    authorization = db.get(SoftwareAuthorization, deployment.authorization_id)
    distribution = db.get(Distribution, authorization.distribution_id) if authorization and authorization.distribution_id else None
    package = db.get(DeliveryPackage, distribution.delivery_package_id) if distribution else None
    decisions = db.scalars(select(ReleaseDecision).where(
        ReleaseDecision.release_id == package.release_id,
        ReleaseDecision.snapshot_id == package.snapshot_id,
    ).order_by(ReleaseDecision.decided_at, ReleaseDecision.decision_no)).all() if package else []
    approvals = {row.id: row for row in (
        db.get(ApprovalRequest, decision.approval_request_id) for decision in decisions
    ) if row is not None}
    return {
        "authorization": {"authorization_no": authorization.authorization_no, "status": authorization.status}
            if authorization else None,
        "distribution": {"distribution_no": distribution.distribution_no, "status": distribution.status}
            if distribution else None,
        "delivery": {"package_no": package.package_no, "revision": package.revision,
                     "status": package.status, "release_id": str(package.release_id),
                     "snapshot_id": str(package.snapshot_id)} if package else None,
        "release_decisions": [{"decision_no": decision.decision_no, "decision": decision.decision,
                               "approval_no": approvals[decision.approval_request_id].approval_no
                               if decision.approval_request_id in approvals else None}
                              for decision in decisions],
    }


@router.post("/deployments", status_code=201)
def create_deployment(payload: DeploymentCreate, db: Session = Depends(get_db)):
    try:
        row = ProductionService(db).create_deployment(**payload.model_dump())
        return {"id": str(row.id), "deployment_no": row.deployment_no, "status": row.status}
    except ProductionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/deployments/{deployment_no}/actual")
def report_actual(deployment_no: str, payload: ActualSoftwareReport, db: Session = Depends(get_db)):
    try:
        row = ProductionService(db).report_actual(deployment_no, **payload.model_dump())
        return {"deployment_no": row.deployment_no, "status": row.status}
    except ProductionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/deployments/{deployment_no}/changeovers", status_code=201)
def create_changeover(deployment_no: str, payload: ChangeoverCreate, db: Session = Depends(get_db)):
    try:
        row = ProductionService(db).create_changeover(deployment_no, **payload.model_dump())
        return {"id": str(row.id), "changeover_no": row.changeover_no, "status": row.status}
    except ProductionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/deployments/{deployment_no}/batches", status_code=201)
def create_batch(deployment_no: str, payload: BatchCreate, db: Session = Depends(get_db)):
    try:
        row = ProductionService(db).create_batch(deployment_no, **payload.model_dump())
        return {"id": str(row.id), "batch_no": row.batch_no, "status": row.status}
    except ProductionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
