import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.actor import resolve_actor
from app.authorization import (authorize_authorization, authorize_delivery_package,
                               authorize_distribution, authorize_release)
from app.core.db import get_db
from app.services.revocation import (RevocationError, RevocationReviewContext,
                                    RevocationService, governance_state)


router = APIRouter(prefix="/api/v1", tags=["release-chain-revocation"])


class RevocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=4000)
    expected_context: RevocationReviewContext | None = None

    @model_validator(mode="after")
    def omitted_or_versioned_context(self):
        if "expected_context" in self.model_fields_set and self.expected_context is None:
            raise ValueError("expected_context must be omitted for legacy requests or contain version 1")
        return self


def _run(kind, target_id, payload, db, actor):
    try:
        row = RevocationService(db).revoke(kind, target_id, payload.reason,
                                           actor_context=actor, request_id=payload.request_id,
                                           expected_context=payload.expected_context)
        return {"id": str(row.id), "revocation_no": row.revocation_no,
                "target_kind": row.target_kind, "governance": governance_state(db, kind, target_id)}
    except RevocationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/releases/{target_id}/revocations", status_code=201)
def revoke_release(target_id: uuid.UUID, payload: RevocationCreate, db: Session = Depends(get_db), request: Request = None):
    authorize_release(request, db, target_id, project_roles=frozenset({"DISTRIBUTION_AUTHORITY"}))
    return _run("RELEASE", target_id, payload, db, resolve_actor(request))


@router.post("/deliveries/{target_id}/revocations", status_code=201)
def revoke_delivery(target_id: uuid.UUID, payload: RevocationCreate, db: Session = Depends(get_db), request: Request = None):
    authorize_delivery_package(request, db, target_id, "DISTRIBUTION_AUTHORITY")
    return _run("DELIVERY_PACKAGE", target_id, payload, db, resolve_actor(request))


@router.post("/distributions/{target_id}/revocations", status_code=201)
def revoke_distribution(target_id: uuid.UUID, payload: RevocationCreate, db: Session = Depends(get_db), request: Request = None):
    authorize_distribution(request, db, target_id, "PRODUCTION_AUTHORITY")
    return _run("DISTRIBUTION", target_id, payload, db, resolve_actor(request))


@router.post("/authorizations/{target_id}/revocations", status_code=201)
def revoke_authorization(target_id: uuid.UUID, payload: RevocationCreate, db: Session = Depends(get_db), request: Request = None):
    authorize_authorization(request, db, target_id, "PRODUCTION_AUTHORITY")
    return _run("AUTHORIZATION", target_id, payload, db, resolve_actor(request))


@router.get("/governance/{kind}/{target_id}")
def read_governance(kind: str, target_id: uuid.UUID, db: Session = Depends(get_db)):
    normalized = kind.upper()
    if normalized not in {"RELEASE", "DELIVERY_PACKAGE", "DISTRIBUTION", "AUTHORIZATION"}:
        raise HTTPException(status_code=404, detail="unsupported governance target")
    try:
        return governance_state(db, normalized, target_id, include_review=True)
    except RevocationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
