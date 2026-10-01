import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.resource import ResourceLink
from app.services.resource_links import ResourceInput, ResourceError, EntityType, LocationKind, register_link
from app.authorization import authorize_resource

router = APIRouter(prefix='/api/v1/resources',tags=['resource references'])


def serialize(row):
    return {key: str(getattr(row,key)) if key in {'id','entity_id','created_at'} else getattr(row,key)
        for key in ('id','entity_type','entity_id','entity_ref','entity_href','title','location_kind','location','description','actor_name','reason','created_at')}


@router.get('')
def resource_catalog(entity_type: EntityType | None = None, entity_id: uuid.UUID | None = None,
    location_kind: LocationKind | None = None, q: str | None = Query(None,max_length=200),
    limit: int = Query(50,ge=1,le=100), offset: int = Query(0,ge=0,le=100000), db: Session = Depends(get_db)):
    stmt = select(ResourceLink)
    for value,column in [(entity_type,ResourceLink.entity_type),(entity_id,ResourceLink.entity_id),(location_kind,ResourceLink.location_kind)]:
        if value is not None: stmt = stmt.where(column == value)
    if q and q.strip():
        stmt = stmt.where(or_(*[c.contains(q.strip(),autoescape=True) for c in (ResourceLink.title,ResourceLink.description,ResourceLink.entity_ref)]))
    filtered = stmt.subquery()
    total = db.scalar(select(func.count()).select_from(filtered))
    kinds = dict(db.execute(select(filtered.c.location_kind,func.count()).group_by(filtered.c.location_kind)).all())
    rows = db.scalars(stmt.order_by(ResourceLink.created_at.desc(),ResourceLink.id.desc()).limit(limit).offset(offset)).all()
    return {'total':total,'kind_counts':kinds,'items':[serialize(r) for r in rows],
        'next_offset':offset+limit if offset+limit<total else None}


@router.get('/{resource_id}')
def resource_detail(resource_id: uuid.UUID, db: Session = Depends(get_db)):
    row = db.get(ResourceLink,resource_id)
    if not row: raise HTTPException(404,'resource reference not found')
    return serialize(row)


@router.post('',status_code=201)
def create_resource(
    data: ResourceInput,
    response: Response,
    db: Session = Depends(get_db),
    request: Request = None,
):
    authorize_resource(request, db, data.entity_type, data.entity_id)
    try:
        row,created = register_link(db,data)
        db.commit(); db.refresh(row)
        response.status_code = 201 if created else 200
        return serialize(row)
    except ResourceError as exc:
        db.rollback(); raise HTTPException(exc.status_code,str(exc)) from exc
    except IntegrityError as exc:
        db.rollback(); raise HTTPException(409,'resource request conflict') from exc
    except Exception:
        db.rollback(); raise
