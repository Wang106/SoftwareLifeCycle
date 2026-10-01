import uuid

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.core import Customer, Project, Release
from app.models.distribution import DeliveryPackage, DeliveryPackageItem, Distribution, SoftwareAuthorization
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.production import Deployment, ProductionBatch
from app.services.distribution import DistributionError, DistributionService
from app.authorization import (
    authorize_delivery_package,
    authorize_distribution,
    authorize_project,
    authorize_release,
)
from app.actor import resolve_actor

router = APIRouter(prefix="/api/v1", tags=["distribution"])


class DeliveryCreate(BaseModel):
    release_id: uuid.UUID
    package_no: str
    revision: int = 1
    recipient_type: str
    recipient_code: str
    purpose: str
    snapshot_artifact_ids: list[uuid.UUID]
    created_by: str | None = None


class DistributionCreate(BaseModel):
    delivery_package_id: uuid.UUID
    distribution_no: str
    recipient_type: str
    recipient_code: str


class AuthorizationCreate(BaseModel):
    release_id: uuid.UUID
    distribution_id: uuid.UUID
    authorization_no: str
    customer_id: uuid.UUID
    project_id: uuid.UUID
    site_code: str
    line_code: str
    purpose: str = "PRODUCTION"
    batch_limit: int | None = Field(default=None, ge=1)
    restriction_note: str | None = None


def _delivery_detail(db: Session, package: DeliveryPackage):
    release = db.get(Release, package.release_id)
    snapshot = db.get(ReleaseSnapshot, package.snapshot_id)
    customer = db.scalars(
        select(Customer).where(Customer.code == package.recipient_code)
    ).first() if package.recipient_type == "CUSTOMER" else None
    items = db.execute(
        select(DeliveryPackageItem, SnapshotArtifact)
        .join(SnapshotArtifact, SnapshotArtifact.id == DeliveryPackageItem.snapshot_artifact_id)
        .where(DeliveryPackageItem.delivery_package_id == package.id)
        .order_by(SnapshotArtifact.filename)
    ).all()
    distributions = db.scalars(
        select(Distribution)
        .where(Distribution.delivery_package_id == package.id)
        .order_by(Distribution.distribution_no)
    ).all()
    return {
        "id": str(package.id),
        "package_no": package.package_no,
        "revision": package.revision,
        "status": package.status,
        "release": {
            "id": str(release.id),
            "version": release.version,
            "type": release.release_type,
        } if release else None,
        "snapshot": {
            "id": str(snapshot.id),
            "snapshot_no": snapshot.snapshot_no,
            "content_hash": snapshot.content_hash,
            "status": snapshot.status,
        } if snapshot else None,
        "recipient": {
            "type": package.recipient_type,
            "code": package.recipient_code,
            "name": customer.name if customer else package.recipient_code,
        },
        "purpose": package.purpose,
        "created_by": package.created_by,
        "items": [
            {
                "snapshot_artifact_id": str(item.snapshot_artifact_id),
                "filename": artifact.filename,
                "artifact_type": artifact.artifact_type,
                "sha256": artifact.sha256,
                "distribution_level": artifact.distribution_level,
                "policy_decision": item.policy_decision,
                "control_reference": item.exception_reference,
            }
            for item, artifact in items
        ],
        "distributions": [
            {
                "id": str(row.id),
                "distribution_no": row.distribution_no,
                "status": row.status,
                "sent_at": row.sent_at,
                "acknowledged_at": row.acknowledged_at,
            }
            for row in distributions
        ],
    }


def _distribution_detail(db: Session, row: Distribution):
    package = db.get(DeliveryPackage, row.delivery_package_id)
    snapshot = db.get(ReleaseSnapshot, package.snapshot_id) if package else None
    release = db.get(Release, package.release_id) if package else None
    authorizations = db.scalars(
        select(SoftwareAuthorization)
        .where(SoftwareAuthorization.distribution_id == row.id)
        .order_by(SoftwareAuthorization.authorization_no)
    ).all()
    return {
        "id": str(row.id),
        "distribution_no": row.distribution_no,
        "status": row.status,
        "recipient_type": row.recipient_type,
        "recipient_code": row.recipient_code,
        "sent_at": row.sent_at,
        "acknowledged_at": row.acknowledged_at,
        "note": row.note,
        "delivery": {
            "id": str(package.id),
            "package_no": package.package_no,
            "revision": package.revision,
            "purpose": package.purpose,
        } if package else None,
        "release_version": release.version if release else None,
        "snapshot_no": snapshot.snapshot_no if snapshot else None,
        "authorizations": [{
            "authorization_no": authorization.authorization_no,
            "status": authorization.status,
            "site_code": authorization.site_code,
            "line_code": authorization.line_code,
        } for authorization in authorizations],
    }


def _authorization_detail(db: Session, row: SoftwareAuthorization):
    release = db.get(Release, row.release_id)
    snapshot = db.get(ReleaseSnapshot, row.snapshot_id)
    customer = db.get(Customer, row.customer_id)
    project = db.get(Project, row.project_id)
    distribution = db.get(Distribution, row.distribution_id) if row.distribution_id else None
    package = db.get(DeliveryPackage, distribution.delivery_package_id) if distribution else None
    deployments = db.scalars(
        select(Deployment).where(Deployment.authorization_id == row.id)
        .order_by(Deployment.created_at, Deployment.deployment_no)
    ).all()
    batches = db.scalars(
        select(ProductionBatch).where(ProductionBatch.authorization_id == row.id)
        .order_by(ProductionBatch.batch_no)
    ).all()
    return {
        "id": str(row.id),
        "authorization_no": row.authorization_no,
        "status": row.status,
        "release": {
            "id": str(release.id),
            "version": release.version,
            "type": release.release_type,
        } if release else None,
        "snapshot": {
            "id": str(snapshot.id),
            "snapshot_no": snapshot.snapshot_no,
            "content_hash": snapshot.content_hash,
        } if snapshot else None,
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
        "distribution": {
            "id": str(distribution.id),
            "distribution_no": distribution.distribution_no,
            "status": distribution.status,
            "package_no": package.package_no if package else None,
            "package_revision": package.revision if package else None,
        } if distribution else None,
        "site_code": row.site_code,
        "line_code": row.line_code,
        "purpose": row.purpose,
        "batch_limit": row.batch_limit,
        "restriction_note": row.restriction_note,
        "approved_at": row.approved_at,
        "deployments": [{
            "deployment_no": deployment.deployment_no,
            "status": deployment.status,
            "actual_release_matches": deployment.actual_release_id == row.release_id
            if deployment.actual_release_id else None,
            "actual_snapshot_matches": deployment.actual_snapshot_id == row.snapshot_id
            if deployment.actual_snapshot_id else None,
        } for deployment in deployments],
        "batches": [{"batch_no": batch.batch_no, "status": batch.status}
                    for batch in batches],
    }


@router.get("/deliveries")
def list_deliveries(db: Session = Depends(get_db)):
    rows = db.scalars(select(DeliveryPackage).order_by(DeliveryPackage.created_at.desc())).all()
    return [
        {
            "id": str(x.id),
            "package_no": x.package_no,
            "revision": x.revision,
            "release_id": str(x.release_id),
            "snapshot_id": str(x.snapshot_id),
            "recipient_type": x.recipient_type,
            "recipient_code": x.recipient_code,
            "purpose": x.purpose,
            "status": x.status,
        } for x in rows
    ]


@router.get("/deliveries/{package_no}")
def get_delivery(package_no: str, db: Session = Depends(get_db)):
    package = db.scalars(
        select(DeliveryPackage)
        .where(DeliveryPackage.package_no == package_no)
        .order_by(DeliveryPackage.revision.desc())
    ).first()
    if not package:
        raise HTTPException(status_code=404, detail="delivery package not found")

    return _delivery_detail(db, package)


@router.get("/deliveries/{package_no}/revisions/{revision}")
def get_delivery_revision(package_no: str, revision: int, db: Session = Depends(get_db)):
    if revision < 1:
        raise HTTPException(status_code=422, detail="revision must be positive")
    package = db.scalars(
        select(DeliveryPackage).where(
            DeliveryPackage.package_no == package_no,
            DeliveryPackage.revision == revision,
        )
    ).first()
    if package is None:
        raise HTTPException(status_code=404, detail="delivery package revision not found")
    return _delivery_detail(db, package)


@router.post("/deliveries", status_code=201)
def create_delivery(
    payload: DeliveryCreate,
    db: Session = Depends(get_db),
    request: Request = None,
):
    authorize_release(
        request,
        db,
        payload.release_id,
        project_roles=frozenset({"DISTRIBUTION_AUTHORITY"}),
    )
    actor = resolve_actor(request, payload.created_by)
    try:
        row = DistributionService(db).create_delivery(
            release_id=payload.release_id,
            package_no=payload.package_no,
            revision=payload.revision,
            recipient_type=payload.recipient_type,
            recipient_code=payload.recipient_code,
            purpose=payload.purpose,
            snapshot_artifact_ids=payload.snapshot_artifact_ids,
            created_by=payload.created_by,
            actor_context=actor,
        )
        return {"id": str(row.id), "package_no": row.package_no, "revision": row.revision, "status": row.status}
    except DistributionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/distributions")
def list_distributions(db: Session = Depends(get_db)):
    rows = db.scalars(select(Distribution).order_by(Distribution.distribution_no)).all()
    return [
        {
            "id": str(x.id),
            "distribution_no": x.distribution_no,
            "delivery_package_id": str(x.delivery_package_id),
            "recipient_type": x.recipient_type,
            "recipient_code": x.recipient_code,
            "status": x.status,
        } for x in rows
    ]


@router.get("/distributions/{distribution_no}")
def get_distribution(distribution_no: str, db: Session = Depends(get_db)):
    row = db.scalars(
        select(Distribution).where(Distribution.distribution_no == distribution_no)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="distribution not found")
    return _distribution_detail(db, row)


@router.post("/distributions", status_code=201)
def create_distribution(
    payload: DistributionCreate,
    db: Session = Depends(get_db),
    request: Request = None,
):
    authorize_delivery_package(
        request, db, payload.delivery_package_id, "DISTRIBUTION_AUTHORITY"
    )
    actor = resolve_actor(request)
    try:
        row = DistributionService(db).create_distribution(
            delivery_package_id=payload.delivery_package_id,
            distribution_no=payload.distribution_no,
            recipient_type=payload.recipient_type,
            recipient_code=payload.recipient_code,
            actor_context=actor,
        )
        return {"id": str(row.id), "distribution_no": row.distribution_no, "status": row.status}
    except DistributionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/authorizations")
def list_authorizations(db: Session = Depends(get_db)):
    rows = db.scalars(select(SoftwareAuthorization).order_by(SoftwareAuthorization.authorization_no)).all()
    return [
        {
            "id": str(x.id),
            "authorization_no": x.authorization_no,
            "distribution_id": str(x.distribution_id) if x.distribution_id else None,
            "release_id": str(x.release_id),
            "snapshot_id": str(x.snapshot_id),
            "customer_id": str(x.customer_id),
            "project_id": str(x.project_id),
            "site_code": x.site_code,
            "line_code": x.line_code,
            "purpose": x.purpose,
            "status": x.status,
            "batch_limit": x.batch_limit,
            "restriction_note": x.restriction_note,
        } for x in rows
    ]


@router.get("/authorizations/{authorization_no}")
def get_authorization(authorization_no: str, db: Session = Depends(get_db)):
    row = db.scalars(
        select(SoftwareAuthorization).where(
            SoftwareAuthorization.authorization_no == authorization_no
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="authorization not found")
    return _authorization_detail(db, row)


@router.post("/authorizations", status_code=201)
def create_authorization(
    payload: AuthorizationCreate,
    db: Session = Depends(get_db),
    request: Request = None,
):
    # The service verifies that this project matches the stored application release
    # and distribution chain before committing the authorization.
    authorize_project(request, db, payload.project_id, "PRODUCTION_AUTHORITY")
    authorize_distribution(
        request, db, payload.distribution_id, "PRODUCTION_AUTHORITY"
    )
    actor = resolve_actor(request)
    try:
        row = DistributionService(db).create_authorization(
            release_id=payload.release_id,
            distribution_id=payload.distribution_id,
            authorization_no=payload.authorization_no,
            customer_id=payload.customer_id,
            project_id=payload.project_id,
            site_code=payload.site_code,
            line_code=payload.line_code,
            purpose=payload.purpose,
            batch_limit=payload.batch_limit,
            restriction_note=payload.restriction_note,
            actor_context=actor,
        )
        return {"id": str(row.id), "authorization_no": row.authorization_no, "status": row.status}
    except DistributionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
