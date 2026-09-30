"""Bounded read catalogs; structural flags never grant production permission."""
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.core import Release, Customer, Project
from app.models.snapshot import ReleaseSnapshot
from app.models.distribution import DeliveryPackage, DeliveryPackageItem, Distribution, SoftwareAuthorization
from app.models.production import Deployment, ProductionBatch

router = APIRouter(prefix='/api/v1/distribution/catalog',tags=['distribution catalogs'])


class CatalogFilters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: str | None = Field(None,max_length=30)
    purpose: str | None = Field(None,max_length=50)
    release_id: uuid.UUID | None = None
    snapshot_id: uuid.UUID | None = None
    q: str | None = Field(None,max_length=200)
    limit: int = Field(50,ge=1,le=100)
    offset: int = Field(0,ge=0,le=100000)


class DeliveryFilters(CatalogFilters):
    recipient_type: str | None = Field(None,max_length=50)
    recipient_code: str | None = Field(None,max_length=80)


class DistributionFilters(DeliveryFilters):
    delivery_package_id: uuid.UUID | None = None


class AuthorizationFilters(CatalogFilters):
    customer_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    distribution_id: uuid.UUID | None = None
    site_code: str | None = Field(None,max_length=80)
    line_code: str | None = Field(None,max_length=80)


def filter_stmt(stmt,filters,columns,search):
    for name,column in columns.items():
        value=getattr(filters,name)
        if value is not None and value != '': stmt=stmt.where(column==value)
    if filters.q and filters.q.strip():
        stmt=stmt.where(or_(*[column.contains(filters.q.strip(),autoescape=True) for column in search]))
    return stmt


def page(db,stmt,filters,order):
    filtered=stmt.subquery()
    total=db.scalar(select(func.count()).select_from(filtered))
    statuses=dict(db.execute(select(filtered.c.status,func.count()).group_by(filtered.c.status)).all())
    rows=db.execute(stmt.order_by(*order).limit(filters.limit).offset(filters.offset)).all()
    return rows,{'total':total,'status_counts':statuses,'next_offset':filters.offset+filters.limit if filters.offset+filters.limit<total else None}


def counts(db,model,column,ids):
    if not ids: return {}
    return dict(db.execute(select(column,func.count()).where(column.in_(ids)).group_by(column)).all())


def context(release,snapshot):
    return bool(release and snapshot and snapshot.release_id==release.id and snapshot.status=='FROZEN')


def software(release,snapshot):
    return {'release':{'id':str(release.id),'type':release.release_type,'version':release.version} if release else None,
        'snapshot':{'id':str(snapshot.id),'snapshot_no':snapshot.snapshot_no,'status':snapshot.status} if snapshot else None}


def delivery_ref(package):
    return {'id':str(package.id),'package_no':package.package_no,'revision':package.revision} if package else None


@router.get('/deliveries')
def delivery_catalog(filters: Annotated[DeliveryFilters,Query()], db: Session=Depends(get_db)):
    p=DeliveryPackage
    stmt=select(p,Release,ReleaseSnapshot).outerjoin(Release,Release.id==p.release_id).outerjoin(ReleaseSnapshot,ReleaseSnapshot.id==p.snapshot_id)
    stmt=filter_stmt(stmt,filters,{k:getattr(p,k) for k in ['status','purpose','release_id','snapshot_id','recipient_type','recipient_code']},
        [p.package_no,p.recipient_code,Release.version,ReleaseSnapshot.snapshot_no])
    rows,result=page(db,stmt,filters,[p.package_no,p.revision,p.id])
    ids=[p.id for p,_,_ in rows]
    items=counts(db,DeliveryPackageItem,DeliveryPackageItem.delivery_package_id,ids)
    distributions=counts(db,Distribution,Distribution.delivery_package_id,ids)
    return {**result,'items':[{'id':str(p.id),'package_no':p.package_no,'revision':p.revision,'recipient_type':p.recipient_type,
        'recipient_code':p.recipient_code,'purpose':p.purpose,'status':p.status,**software(r,s),'context_consistent':context(r,s),
        'artifact_count':items.get(p.id,0),'distribution_count':distributions.get(p.id,0)} for p,r,s in rows]}


@router.get('/distributions')
def distribution_catalog(filters: Annotated[DistributionFilters,Query()], db: Session=Depends(get_db)):
    d=Distribution;p=DeliveryPackage
    stmt=select(d,p,Release,ReleaseSnapshot).outerjoin(p,p.id==d.delivery_package_id).outerjoin(Release,Release.id==p.release_id).outerjoin(ReleaseSnapshot,ReleaseSnapshot.id==p.snapshot_id)
    columns={k:getattr(d,k) for k in ['status','recipient_type','recipient_code','delivery_package_id']}
    columns.update({k:getattr(p,k) for k in ['purpose','release_id','snapshot_id']})
    stmt=filter_stmt(stmt,filters,columns,[d.distribution_no,d.recipient_code,p.package_no,Release.version,ReleaseSnapshot.snapshot_no])
    rows,result=page(db,stmt,filters,[d.distribution_no,d.id])
    authorizations=counts(db,SoftwareAuthorization,SoftwareAuthorization.distribution_id,[d.id for d,_,_,_ in rows])
    return {**result,'items':[{'id':str(d.id),'distribution_no':d.distribution_no,'recipient_type':d.recipient_type,'recipient_code':d.recipient_code,
        'status':d.status,'purpose':p.purpose if p else None,'delivery':delivery_ref(p),**software(r,s),'sent_at':d.sent_at,'acknowledged_at':d.acknowledged_at,
        'authorization_count':authorizations.get(d.id,0),'context_consistent':bool(context(r,s) and p and d.recipient_type==p.recipient_type and d.recipient_code==p.recipient_code)} for d,p,r,s in rows]}


@router.get('/authorizations')
def authorization_catalog(filters: Annotated[AuthorizationFilters,Query()], db: Session=Depends(get_db)):
    a=SoftwareAuthorization;d=Distribution;p=DeliveryPackage
    stmt=select(a,Release,ReleaseSnapshot,Customer,Project,d,p).outerjoin(Release,Release.id==a.release_id).outerjoin(ReleaseSnapshot,ReleaseSnapshot.id==a.snapshot_id)\
        .outerjoin(Customer,Customer.id==a.customer_id).outerjoin(Project,Project.id==a.project_id).outerjoin(d,d.id==a.distribution_id).outerjoin(p,p.id==d.delivery_package_id)
    columns={k:getattr(a,k) for k in ['status','purpose','release_id','snapshot_id','customer_id','project_id','site_code','line_code','distribution_id']}
    stmt=filter_stmt(stmt,filters,columns,[a.authorization_no,a.site_code,a.line_code,Customer.code,Project.project_code,d.distribution_no,p.package_no,Release.version,ReleaseSnapshot.snapshot_no])
    rows,result=page(db,stmt,filters,[a.authorization_no,a.id]);ids=[a.id for a,*_ in rows]
    batches=counts(db,ProductionBatch,ProductionBatch.authorization_id,ids)
    deployments=counts(db,Deployment,Deployment.authorization_id,ids)
    items=[]
    for a,r,s,c,j,d,p in rows:
        used=batches.get(a.id,0)
        consistent=bool(context(r,s) and c and j and j.customer_id==c.id and d and p and p.release_id==a.release_id and p.snapshot_id==a.snapshot_id
            and p.recipient_type==d.recipient_type=='CUSTOMER' and p.recipient_code==d.recipient_code==c.code and p.purpose==a.purpose)
        items.append({'id':str(a.id),'authorization_no':a.authorization_no,'status':a.status,'purpose':a.purpose,**software(r,s),
            'customer':{'id':str(c.id),'code':c.code} if c else None,'project':{'id':str(j.id),'code':j.project_code} if j else None,
            'distribution':{'id':str(d.id),'distribution_no':d.distribution_no} if d else None,'delivery':delivery_ref(p),
            'site_code':a.site_code,'line_code':a.line_code,'batch_limit':a.batch_limit,'registered_batches':used,
            'remaining_batches':max(a.batch_limit-used,0) if a.batch_limit is not None else None,
            'at_or_over_limit':a.batch_limit is not None and used>=a.batch_limit,'deployment_count':deployments.get(a.id,0),'context_consistent':consistent})
    return {**result,'items':items,'notice':'Registered batch counts include all statuses. Remaining capacity and structural consistency are observations, not permission to deploy or create batches.'}
