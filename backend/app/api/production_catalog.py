"""Bounded production history; observations do not authorize production actions."""
import uuid
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.core import Release,Customer,Project
from app.models.snapshot import ReleaseSnapshot
from app.models.production import Deployment,SoftwareChangeover,ProductionBatch,ProductionLine,ManufacturingSite
from app.models.distribution import SoftwareAuthorization

router=APIRouter(prefix='/api/v1/production/catalog',tags=['production catalogs'])


class ProductionFilters(BaseModel):
    model_config=ConfigDict(extra='forbid')
    status: str | None=Field(None,max_length=30)
    q: str | None=Field(None,max_length=200)
    release_id: uuid.UUID | None=None
    snapshot_id: uuid.UUID | None=None
    authorization_id: uuid.UUID | None=None
    deployment_id: uuid.UUID | None=None
    customer_id: uuid.UUID | None=None
    project_id: uuid.UUID | None=None
    site_code: str | None=Field(None,max_length=80)
    line_code: str | None=Field(None,max_length=80)
    limit: int=Field(50,ge=1,le=100)
    offset: int=Field(0,ge=0,le=100000)


def objects(db,model,ids):
    ids={i for i in ids if i is not None}
    return {r.id:r for r in db.scalars(select(model).where(model.id.in_(ids))).all()} if ids else {}


def software(releases,snapshots,release_id,snapshot_id=None):
    r=releases.get(release_id);s=snapshots.get(snapshot_id)
    return {'release_id':str(release_id) if release_id else None,'snapshot_id':str(snapshot_id) if snapshot_id else None,
        'version':r.version if r else None,'type':r.release_type if r else None,'snapshot_no':s.snapshot_no if s else None}


def observed(deployment):
    if not deployment: return 'DEPLOYMENT_MISSING'
    if not deployment.actual_release_id and not deployment.actual_snapshot_id: return 'NOT_RECORDED'
    if not deployment.actual_release_id or not deployment.actual_snapshot_id: return 'PARTIAL'
    return 'MATCH' if (deployment.actual_release_id, deployment.actual_snapshot_id)==(deployment.expected_release_id,deployment.expected_snapshot_id) else 'MISMATCH'


@router.get('/{kind}')
def production_catalog(kind: Literal['deployments','changeovers','batches'], filters: Annotated[ProductionFilters,Query()], db: Session=Depends(get_db)):
    model={'deployments':Deployment,'changeovers':SoftwareChangeover,'batches':ProductionBatch}[kind]
    number={'deployments':'deployment_no','changeovers':'changeover_no','batches':'batch_no'}[kind]
    d=Deployment;a=SoftwareAuthorization;l=ProductionLine;s=ManufacturingSite
    stmt=select(model)
    if model is not d: stmt=stmt.outerjoin(d,d.id==model.deployment_id)
    stmt=stmt.outerjoin(a,a.id==d.authorization_id).outerjoin(l,l.id==d.production_line_id).outerjoin(s,s.id==l.site_id)
    release_column=d.expected_release_id if kind=='deployments' else model.to_release_id if kind=='changeovers' else model.release_id
    snapshot_column=model.snapshot_id if kind=='batches' else d.expected_snapshot_id
    stmt=stmt.outerjoin(Release,Release.id==release_column).outerjoin(ReleaseSnapshot,ReleaseSnapshot.id==snapshot_column)
    columns={'status':model.status,'authorization_id':model.authorization_id,'deployment_id':d.id,'release_id':release_column,
        'snapshot_id':snapshot_column,'customer_id':s.customer_id,'project_id':s.project_id,'site_code':s.site_code,'line_code':l.line_code}
    for name,column in columns.items():
        value=getattr(filters,name)
        if value is not None and value!='':stmt=stmt.where(column==value)
    if filters.q and filters.q.strip():
        stmt=stmt.where(or_(*[c.contains(filters.q.strip(),autoescape=True) for c in [getattr(model,number),a.authorization_no,d.deployment_no,s.site_code,l.line_code,Release.version,ReleaseSnapshot.snapshot_no]]))
    sub=stmt.subquery();total=db.scalar(select(func.count()).select_from(sub))
    status_counts=dict(db.execute(select(sub.c.status,func.count()).group_by(sub.c.status)).all())
    rows=db.scalars(stmt.order_by(getattr(model,number),model.id).limit(filters.limit).offset(filters.offset)).all()
    deployments={r.id:r for r in rows} if kind=='deployments' else objects(db,d,[r.deployment_id for r in rows])
    auth_ids=[r.authorization_id for r in rows]+[r.authorization_id for r in deployments.values()]
    auths=objects(db,a,auth_ids);lines=objects(db,l,[r.production_line_id for r in deployments.values()])
    sites=objects(db,s,[r.site_id for r in lines.values()]);customers=objects(db,Customer,[r.customer_id for r in sites.values()])
    projects=objects(db,Project,[r.project_id for r in sites.values()])
    release_ids=[i for r in deployments.values() for i in [r.expected_release_id,r.actual_release_id]]+[r.release_id for r in auths.values()]
    snapshot_ids=[i for r in deployments.values() for i in [r.expected_snapshot_id,r.actual_snapshot_id]]+[r.snapshot_id for r in auths.values()]
    if kind=='batches':release_ids.extend(r.release_id for r in rows);snapshot_ids.extend(r.snapshot_id for r in rows)
    if kind=='changeovers':release_ids.extend(i for r in rows for i in [r.from_release_id,r.to_release_id])
    releases=objects(db,Release,release_ids);snapshots=objects(db,ReleaseSnapshot,snapshot_ids)
    changeovers=objects(db,SoftwareChangeover,[r.changeover_id for r in rows]) if kind=='batches' else {}
    counts={}
    if kind=='deployments' and rows:
        for child in [SoftwareChangeover,ProductionBatch]:
            counts[child]=dict(db.execute(select(child.deployment_id,func.count()).where(child.deployment_id.in_(deployments)).group_by(child.deployment_id)).all())
    items=[]
    for row in rows:
        dep=deployments.get(row.id if kind=='deployments' else row.deployment_id)
        auth=auths.get(row.authorization_id);line=lines.get(dep.production_line_id) if dep else None
        site=sites.get(line.site_id) if line else None;customer=customers.get(site.customer_id) if site else None;project=projects.get(site.project_id) if site else None
        flags=[]
        def check(ok,label):
            if not ok:flags.append(label)
        check(dep is not None,'deployment_missing');check(auth is not None,'authorization_missing');check(bool(line and site and customer and project),'location_missing')
        if dep and auth:
            check(dep.authorization_id==auth.id,'authorization_binding')
            check((dep.expected_release_id,dep.expected_snapshot_id)==(auth.release_id,auth.snapshot_id),'expected_authorization_binding')
            snap=snapshots.get(dep.expected_snapshot_id)
            check(bool(releases.get(dep.expected_release_id) and snap and snap.release_id==dep.expected_release_id and snap.status=='FROZEN'),'expected_snapshot_binding')
        if auth and site and line and project:
            check((site.customer_id,site.project_id,site.site_code,line.line_code)==(auth.customer_id,auth.project_id,auth.site_code,auth.line_code) and project.customer_id==site.customer_id,'authorized_location_binding')
        co=row if kind=='changeovers' else changeovers.get(row.changeover_id) if kind=='batches' and row.changeover_id else None
        if kind=='changeovers':check(bool(releases.get(row.from_release_id)),'from_release_missing')
        if co:
            check(bool(dep and co.deployment_id==dep.id and co.authorization_id==row.authorization_id and co.to_release_id==dep.expected_release_id and co.to_release_id==dep.actual_release_id),'changeover_binding')
        if kind=='batches':
            check(bool(auth and (row.release_id,row.snapshot_id)==(auth.release_id,auth.snapshot_id)),'batch_authorization_binding')
            check(bool(dep and (row.release_id,row.snapshot_id)==(dep.actual_release_id,dep.actual_snapshot_id)),'batch_actual_binding')
            snap=snapshots.get(row.snapshot_id)
            check(bool(releases.get(row.release_id) and snap and snap.release_id==row.release_id and snap.status=='FROZEN'),'batch_snapshot_binding')
            if row.changeover_id:check(co is not None,'changeover_missing')
        items.append({'id':str(row.id),'record_no':getattr(row,number),'status':row.status,'binding_flags':flags,'context_consistent':not flags,
            'deployment':{'id':str(dep.id),'deployment_no':dep.deployment_no,'status':dep.status} if dep else None,
            'authorization':{'id':str(auth.id),'authorization_no':auth.authorization_no,'status':auth.status} if auth else None,
            'customer':{'id':str(customer.id),'code':customer.code} if customer else None,'project':{'id':str(project.id),'code':project.project_code} if project else None,
            'site':{'site_code':site.site_code} if site else None,'line':{'line_code':line.line_code} if line else None,
            'expected':software(releases,snapshots,dep.expected_release_id,dep.expected_snapshot_id) if dep else None,
            'actual':software(releases,snapshots,dep.actual_release_id,dep.actual_snapshot_id) if dep and (dep.actual_release_id or dep.actual_snapshot_id) else None,'software_observation':observed(dep),
            'recorded':software(releases,snapshots,row.release_id,row.snapshot_id) if kind=='batches' else software(releases,snapshots,row.to_release_id) if kind=='changeovers' else None,
            'from_release':software(releases,snapshots,row.from_release_id) if kind=='changeovers' else None,
            'changeover':{'changeover_no':co.changeover_no,'status':co.status} if co else None,
            'changeover_linked':bool(row.changeover_id) if kind=='batches' else None,
            'changeover_count':counts.get(SoftwareChangeover,{}).get(row.id,0) if kind=='deployments' else None,
            'batch_count':counts.get(ProductionBatch,{}).get(row.id,0) if kind=='deployments' else None,
            'recorded_at':row.deployed_at if kind=='deployments' else row.changed_at if kind=='changeovers' else row.started_at})
    return {'total':total,'status_counts':status_counts,'next_offset':filters.offset+filters.limit if filters.offset+filters.limit<total else None,
        'items':items,'notice':'Binding checks and actual-software observations do not grant production permission. Changeovers have no stored snapshot; their snapshot filter scopes the deployment expected snapshot.'}
