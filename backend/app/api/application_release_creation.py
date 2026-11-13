"""Dedicated OIDC-only creation boundary, separate from legacy command contracts."""
import uuid
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.services.application_release_creation import ApplicationReleaseCreationService, CreateApplicationRelease

router = APIRouter(prefix='/api/v1', tags=['application release creation'])


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
