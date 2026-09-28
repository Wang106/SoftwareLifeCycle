from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.distribution import DeliveryPackage, DeliveryPackageItem, Distribution, SoftwareAuthorization
from app.models.snapshot import SnapshotArtifact
from app.services.distribution import DistributionError, DistributionService

router = APIRouter(prefix="/api/v1", tags=["distribution"])


class DeliveryCreate(BaseModel):
    release_id: str
    package_no: str
    revision: int = 1
    recipient_type: str
    recipient_code: str
    purpose: str
    snapshot_artifact_ids: list[str]
    created_by: str | None = None


class DistributionCreate(BaseModel):
    delivery_package_id: str
    distribution_no: str
    recipient_type: str
    recipient_code: str


class AuthorizationCreate(BaseModel):
    release_id: str
    authorization_no: str
    customer_id: str
    project_id: str
    site_code: str
    line_code: str
    purpose: str = "PRODUCTION"
    restriction_note: str | None = None


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

    items = db.execute(
        select(DeliveryPackageItem, SnapshotArtifact)
        .join(SnapshotArtifact, SnapshotArtifact.id == DeliveryPackageItem.snapshot_artifact_id)
        .where(DeliveryPackageItem.delivery_package_id == package.id)
    ).all()
    return {
        "id": str(package.id),
        "package_no": package.package_no,
        "revision": package.revision,
        "status": package.status,
        "recipient_type": package.recipient_type,
        "recipient_code": package.recipient_code,
        "purpose": package.purpose,
        "items": [
            {
                "snapshot_artifact_id": str(item.snapshot_artifact_id),
                "filename": artifact.filename,
                "distribution_level": artifact.distribution_level,
                "policy_decision": item.policy_decision,
                "exception_reference": item.exception_reference,
            }
            for item, artifact in items
        ],
    }


@router.post("/deliveries", status_code=201)
def create_delivery(payload: DeliveryCreate, db: Session = Depends(get_db)):
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
        )
        return {"id": str(row.id), "package_no": row.package_no, "revision": row.revision, "status": row.status}
    except DistributionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/distributions")
def list_distributions(db: Session = Depends(get_db)):
    rows = db.scalars(select(Distribution)).all()
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


@router.post("/distributions", status_code=201)
def create_distribution(payload: DistributionCreate, db: Session = Depends(get_db)):
    try:
        row = DistributionService(db).create_distribution(
            delivery_package_id=payload.delivery_package_id,
            distribution_no=payload.distribution_no,
            recipient_type=payload.recipient_type,
            recipient_code=payload.recipient_code,
        )
        return {"id": str(row.id), "distribution_no": row.distribution_no, "status": row.status}
    except DistributionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/authorizations")
def list_authorizations(db: Session = Depends(get_db)):
    rows = db.scalars(select(SoftwareAuthorization)).all()
    return [
        {
            "id": str(x.id),
            "authorization_no": x.authorization_no,
            "release_id": str(x.release_id),
            "snapshot_id": str(x.snapshot_id),
            "customer_id": str(x.customer_id),
            "project_id": str(x.project_id),
            "site_code": x.site_code,
            "line_code": x.line_code,
            "purpose": x.purpose,
            "status": x.status,
            "restriction_note": x.restriction_note,
        } for x in rows
    ]


@router.post("/authorizations", status_code=201)
def create_authorization(payload: AuthorizationCreate, db: Session = Depends(get_db)):
    try:
        row = DistributionService(db).create_authorization(
            release_id=payload.release_id,
            authorization_no=payload.authorization_no,
            customer_id=payload.customer_id,
            project_id=payload.project_id,
            site_code=payload.site_code,
            line_code=payload.line_code,
            purpose=payload.purpose,
            restriction_note=payload.restriction_note,
        )
        return {"id": str(row.id), "authorization_no": row.authorization_no, "status": row.status}
    except DistributionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
