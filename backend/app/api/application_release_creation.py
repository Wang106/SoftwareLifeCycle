"""Dedicated OIDC-only creation boundary, separate from legacy command contracts."""
import uuid
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.services.application_release_creation import ApplicationReleaseCreationService, CreateApplicationRelease

router = APIRouter(prefix='/api/v1', tags=['application release creation'])


@router.get('/application-release-creation/standard-options')
def standard_options(request: Request, db: Session = Depends(get_db)):
    try:
        pairs = list(request.query_params.multi_items())
        values = dict(pairs)
        if len(pairs) != len(values) or set(values) - {'project_id', 'limit', 'after'}:
            raise ValueError('unexpected query fields')
        project_id = uuid.UUID(str(CreateApplicationRelease.canonical_uuid(values.get('project_id'))))
        raw_limit = values.get('limit', '25')
        if not raw_limit.isascii() or not raw_limit.isdecimal() or str(int(raw_limit)) != raw_limit:
            raise ValueError('invalid limit')
        limit = int(raw_limit)
        if not 1 <= limit <= 50: raise ValueError('limit out of bounds')
        after = values.get('after')
        if after is not None: after = uuid.UUID(str(CreateApplicationRelease.canonical_uuid(after)))
    except (TypeError, ValueError):
        raise HTTPException(422, 'invalid_options_query')
    return ApplicationReleaseCreationService(db).standard_options(project_id, request, limit=limit, after=after)


@router.get('/application-release-creation/context')
def creation_context(project_id: uuid.UUID, standard_base_release_id: uuid.UUID,
                     request: Request, db: Session = Depends(get_db)):
    return ApplicationReleaseCreationService(db).context(project_id, standard_base_release_id, request)


@router.post('/releases/application', status_code=201)
def create_application_release(body: CreateApplicationRelease, request: Request,
                               response: Response, db: Session = Depends(get_db)):
    result, created = ApplicationReleaseCreationService(db).create(request=request, **body.model_dump())
    response.status_code = 201 if created else 200
    return result


@router.get('/application-release-creation/receipts/{request_id}')
def creation_receipt(request_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    return ApplicationReleaseCreationService(db).receipt(request_id, request)
