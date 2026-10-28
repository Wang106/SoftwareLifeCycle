"""Private exact-target evidence preparation, never a global catalogue."""
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.services.private_evidence_selection import PrivateEvidenceSelection

router = APIRouter(prefix='/api/v1/evidence-selection-context',tags=['private evidence selection'])
class Page(BaseModel):
    model_config = ConfigDict(extra='forbid')
    limit:int = Field(20,ge=1,le=50)
    offset:int = Field(0,ge=0,le=100000)

@router.get('/approvals/{approval_no}/current-step')
def approval(approval_no:str,request:Request,db:Session=Depends(get_db)):
    return PrivateEvidenceSelection(db).approval(request,approval_no)
@router.get('/changes/{request_no}/criteria')
def criteria(request_no:str,query:Annotated[Page,Query()],request:Request,db:Session=Depends(get_db)):
    return PrivateEvidenceSelection(db).changes(request,request_no,'criteria',**query.model_dump())
@router.get('/changes/{request_no}/dvp-items')
def dvp(request_no:str,query:Annotated[Page,Query()],request:Request,db:Session=Depends(get_db)):
    return PrivateEvidenceSelection(db).changes(request,request_no,'dvp',**query.model_dump())
@router.get('/issues/{issue_no}/releases/{release_id}/snapshots')
def snapshots(issue_no:str,release_id:uuid.UUID,query:Annotated[Page,Query()],request:Request,db:Session=Depends(get_db)):
    return PrivateEvidenceSelection(db).snapshots(request,issue_no,release_id,**query.model_dump())
@router.get('/resources/{entity_type}/{entity_id}')
def resource(entity_type:str,entity_id:uuid.UUID,request:Request,db:Session=Depends(get_db)):
    return PrivateEvidenceSelection(db).resource(request,entity_type,entity_id)
