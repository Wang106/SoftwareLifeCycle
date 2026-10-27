"""Private exact-context selectors; never a global catalog or submission permission."""
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.services.private_distribution_selection import PrivateDistributionSelection

router=APIRouter(prefix='/api/v1/selection-context',tags=['private distribution selection'])
class Pins(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_snapshot_id:uuid.UUID|None=None
    expected_decision_id:uuid.UUID|None=None
    @model_validator(mode='after')
    def paired(self):
        if (self.expected_snapshot_id is None)!=(self.expected_decision_id is None):raise ValueError('Both context pins are required')
        return self
class Page(Pins):
    limit:int=Field(20,ge=1,le=50)
    offset:int=Field(0,ge=0,le=100000)
    @model_validator(mode='after')
    def pinned_page(self):
        if self.offset and self.expected_snapshot_id is None:raise ValueError('Later pages require context pins')
        return self
class Artifacts(Page):
    recipient_type:str=Field(min_length=1,max_length=50,pattern=r'^[^\x00-\x20\x7f]+$')
    recipient_code:str=Field(min_length=1,max_length=80,pattern=r'^[^\x00-\x1f\x7f]+$')
    purpose:str=Field(min_length=1,max_length=50,pattern=r'^[^\x00-\x20\x7f]+$')

@router.get('/releases/{release_id}/delivery-artifacts')
def artifacts(release_id:uuid.UUID,query:Annotated[Artifacts,Query()],request:Request,db:Session=Depends(get_db)):
    return PrivateDistributionSelection(db).artifacts(request,release_id,**query.model_dump())
@router.get('/deliveries/{package_id}')
def package(package_id:uuid.UUID,request:Request,db:Session=Depends(get_db)):
    return PrivateDistributionSelection(db).package(request,package_id)
@router.get('/distributions/{distribution_id}/authorization-scope')
def scope(distribution_id:uuid.UUID,query:Annotated[Page,Query()],request:Request,db:Session=Depends(get_db)):
    return PrivateDistributionSelection(db).scope(request,distribution_id,**query.model_dump())
