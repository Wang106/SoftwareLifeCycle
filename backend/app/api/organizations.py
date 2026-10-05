"""Internal legacy comparison helpers; HTTP reads retired in compatibility_reads."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.core import (
    ApplicationReleaseDetail, Customer, Project, Release, SoftwareProduct, Supplier,
)
from app.models.production import ManufacturingSite

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


def _suppliers(db: Session, rows: list[Supplier]) -> list[dict]:
    ids = [row.id for row in rows]
    products = db.scalars(select(SoftwareProduct).where(SoftwareProduct.supplier_id.in_(ids))).all() if ids else []
    versions = db.scalars(select(Release).where(Release.software_id.in_([p.id for p in products]), Release.release_type == "STANDARD")
        .order_by(Release.created_at.desc(), Release.id.desc())).all() if products else []
    latest = {}
    for release in versions:
        latest.setdefault(release.software_id, release.version)
    return [{"id": str(row.id), "code": row.code, "name": row.name, "country": row.country, "website": row.website,
             "description": row.description, "status": row.status,
             "software": [{"code": p.code, "name": p.name, "type": p.software_type,
                           "status": p.status, "standard_version": latest.get(p.id)}
                          for p in products if p.supplier_id == row.id]} for row in rows]


def _customers(db: Session, rows: list[Customer]) -> list[dict]:
    ids = [row.id for row in rows]
    projects = db.scalars(select(Project).where(Project.customer_id.in_(ids)).order_by(Project.project_code)).all() if ids else []
    details = db.scalars(select(ApplicationReleaseDetail).where(ApplicationReleaseDetail.customer_id.in_(ids))).all() if ids else []
    releases = db.scalars(select(Release).where(Release.id.in_([d.release_id for d in details]))
        .order_by(Release.created_at.desc(), Release.id.desc())).all() if details else []
    detail_by_release = {d.release_id: d for d in details}
    latest = {}
    for release in releases:
        detail = detail_by_release[release.id]
        latest.setdefault(detail.project_id, {"id": str(release.id), "version": release.version, "status": release.status})
    return [{"id": str(row.id), "code": row.code, "name": row.name, "status": row.status, "region": row.region,
             "projects": [{"id": str(p.id), "code": p.project_code, "name": p.name, "status": p.status,
                           "release": latest.get(p.id)} for p in projects if p.customer_id == row.id]}
            for row in rows]


def _projects(db: Session, rows: list[Project]) -> list[dict]:
    ids = [row.id for row in rows]
    customer_ids = {row.customer_id for row in rows}
    customers = {c.id: c for c in db.scalars(select(Customer).where(Customer.id.in_(customer_ids))).all()} if ids else {}
    details = db.scalars(select(ApplicationReleaseDetail).where(ApplicationReleaseDetail.project_id.in_(ids))).all() if ids else []
    releases = db.scalars(select(Release).where(Release.id.in_([d.release_id for d in details]))
        .order_by(Release.created_at.desc(), Release.id.desc())).all() if details else []
    detail_by_release = {d.release_id: d for d in details}
    latest = {}
    for release in releases:
        detail = detail_by_release[release.id]
        latest.setdefault(detail.project_id, {"id": str(release.id), "version": release.version, "status": release.status})
    sites = db.scalars(select(ManufacturingSite).where(ManufacturingSite.project_id.in_(ids)).order_by(ManufacturingSite.site_code)).all() if ids else []
    return [{"id": str(row.id), "code": row.project_code, "name": row.name, "status": row.status,
             "vehicle_platform": row.vehicle_platform,
             "customer": {"code": customers[row.customer_id].code, "name": customers[row.customer_id].name},
             "release": latest.get(row.id),
             "sites": [{"code": s.site_code, "name": s.name, "status": s.status} for s in sites if s.project_id == row.id]}
            for row in rows]


def list_suppliers(db: Session = Depends(get_db)):
    rows = db.scalars(select(Supplier).order_by(Supplier.code).limit(200)).all()
    return _suppliers(db, rows)


def get_supplier(code: str, db: Session = Depends(get_db)):
    row = db.scalars(select(Supplier).where(Supplier.code == code)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    return _suppliers(db, [row])[0]


def list_customers(db: Session = Depends(get_db)):
    rows = db.scalars(select(Customer).order_by(Customer.code).limit(200)).all()
    return _customers(db, rows)


def get_customer(code: str, db: Session = Depends(get_db)):
    row = db.scalars(select(Customer).where(Customer.code == code)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return _customers(db, [row])[0]


def list_projects(db: Session = Depends(get_db)):
    rows = db.scalars(select(Project).order_by(Project.project_code).limit(200)).all()
    return _projects(db, rows)


def get_project(identifier: str, db: Session = Depends(get_db)):
    try:
        project_id = uuid.UUID(identifier)
    except ValueError:
        project_id = None
    if project_id:
        row = db.get(Project, project_id)
    else:
        matches = db.scalars(select(Project).where(Project.project_code == identifier).limit(2)).all()
        if len(matches) > 1:
            raise HTTPException(status_code=409, detail="project code is ambiguous; use project ID")
        row = matches[0] if matches else None
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    return _projects(db, [row])[0]
