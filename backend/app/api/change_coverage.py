import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.services.change_coverage import AssignmentInput, CoverageError, record_assignment, report_coverage

router = APIRouter(prefix='/api/v1/changes', tags=['change coverage'])


@router.get('/{request_no}/coverage')
def change_coverage(request_no: str, release_id: uuid.UUID | None = None,
                    snapshot_no: str | None = Query(None, min_length=1, max_length=80), db: Session = Depends(get_db)):
    try:
        return report_coverage(db, request_no, release_id, snapshot_no)
    except CoverageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/{request_no}/acceptance-dvp-links', status_code=201)
def assign_acceptance(request_no: str, data: AssignmentInput, response: Response, db: Session = Depends(get_db)):
    try:
        row, created = record_assignment(db, request_no, data)
        db.commit(); db.refresh(row)
        response.status_code = 201 if created else 200
        return {'id': str(row.id), 'criterion_id': str(row.criterion_id), 'dvp_item_id': str(row.dvp_item_id),
            'actor_name': row.actor_name, 'reason': row.reason, 'created_at': row.created_at}
    except CoverageError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail='assignment request conflict') from exc
    except Exception:
        db.rollback()
        raise
