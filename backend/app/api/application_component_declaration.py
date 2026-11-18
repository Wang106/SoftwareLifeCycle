"""Independently gated private component declaration and original receipts."""
import uuid
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.services.application_component_declaration import ApplicationComponentDeclarationService, DeclareApplicationComponent

router = APIRouter(prefix='/api/v1', tags=['application component declaration'])

class DeclarationContextQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    release_id: uuid.UUID
    component_definition_id: uuid.UUID
    base_component_id: uuid.UUID | None = None

    @field_validator('release_id', 'component_definition_id', 'base_component_id', mode='before')
    @classmethod
    def canonical_uuid(cls, value, info):
        return DeclareApplicationComponent.canonical_uuid(value, info)


@router.get('/application-component-declaration/context')
def declaration_context(request: Request, db: Session = Depends(get_db)):
    try:
        pairs = list(request.query_params.multi_items())
        if len(pairs) != len(dict(pairs)):
            raise ValueError('duplicate query fields')
        query = DeclarationContextQuery.model_validate(dict(pairs))
    except (ValueError, ValidationError):
        raise HTTPException(422, 'invalid_asrc_context_query')
    return ApplicationComponentDeclarationService(db).context(
        query.release_id, query.component_definition_id, query.base_component_id, request)

@router.post('/application-component-declarations', status_code=201)
def declare_component(body: DeclareApplicationComponent, request: Request, response: Response, db: Session = Depends(get_db)):
    result, created = ApplicationComponentDeclarationService(db).create(request=request, **body.model_dump())
    response.status_code = 201 if created else 200
    return result

@router.get('/application-component-declaration/receipts/{request_id}')
def declaration_receipt(request_id: str, request: Request, db: Session = Depends(get_db)):
    from app.services.application_release_creation import CreateApplicationRelease
    try:
        key = uuid.UUID(str(CreateApplicationRelease.canonical_uuid(request_id)))
    except (TypeError, ValueError):
        raise HTTPException(422, 'invalid_asrc_receipt_id')
    return ApplicationComponentDeclarationService(db).receipt(key,request)


@router.get('/application-component-declaration/baseline-options')
def baseline_options(request: Request, db: Session = Depends(get_db)):
    from app.services.application_release_creation import CreateApplicationRelease
    try:
        pairs = list(request.query_params.multi_items())
        values = dict(pairs)
        if len(pairs) != len(values) or set(values) - {'release_id','limit','after'}:
            raise ValueError('unexpected query fields')
        release_id = uuid.UUID(str(CreateApplicationRelease.canonical_uuid(values.get('release_id'))))
        raw_limit = values.get('limit','25')
        if not raw_limit.isascii() or not raw_limit.isdecimal() or str(int(raw_limit)) != raw_limit:
            raise ValueError('invalid limit')
        limit = int(raw_limit)
        if not 1 <= limit <= 50: raise ValueError('limit out of bounds')
        after = values.get('after')
        if after is not None: CreateApplicationRelease.canonical_uuid(after)
    except (TypeError, ValueError, ValidationError):
        raise HTTPException(422, 'invalid_asrc_options_query')
    return ApplicationComponentDeclarationService(db).baseline_options(release_id,request,limit=limit,after=after)
