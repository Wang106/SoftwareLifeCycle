"""Test-only version browsing; no production permission is implied."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.core import Release, SoftwareProduct
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.testing import DvpExecution, DvpItem, TestRelease
from app.api.dvp_catalog import serialize_executions
from app.services.testing_release import TestReleaseError, TestReleaseInput, create_test_draft

router = APIRouter(prefix='/api/v1/testing/releases', tags=['test releases'])


def basic(row):
    return {'id': str(row.id), 'test_release_no': row.test_release_no, 'release_id': str(row.release_id),
        'snapshot_id': str(row.snapshot_id), 'purpose_scope': row.purpose_scope, 'status': row.status}


def find_test(db, test_release_no):
    row = db.scalars(select(TestRelease).where(TestRelease.test_release_no == test_release_no)).first()
    if not row:
        raise HTTPException(404, 'test release not found')
    return row


@router.get('')
def test_catalog(status: str | None = Query(None, max_length=30), scope: str | None = Query(None, max_length=30),
    release_id: uuid.UUID | None = None, q: str | None = Query(None, max_length=200),
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=100000), db: Session = Depends(get_db)):
    stmt = select(TestRelease, Release, ReleaseSnapshot, SoftwareProduct).join(Release, Release.id == TestRelease.release_id)
    stmt = stmt.join(ReleaseSnapshot, ReleaseSnapshot.id == TestRelease.snapshot_id).join(SoftwareProduct, SoftwareProduct.id == Release.software_id)
    for value, column in [(status, TestRelease.status), (scope, TestRelease.purpose_scope), (release_id, TestRelease.release_id)]:
        if value is not None and value != '':
            stmt = stmt.where(column == value)
    if q and q.strip():
        stmt = stmt.where(or_(*[c.contains(q.strip(), autoescape=True) for c in
            (TestRelease.test_release_no, Release.version, ReleaseSnapshot.snapshot_no, SoftwareProduct.code, SoftwareProduct.name)]))
    filtered = stmt.subquery()
    total = db.scalar(select(func.count()).select_from(filtered))
    statuses = dict(db.execute(select(filtered.c.status, func.count()).group_by(filtered.c.status)).all())
    page = db.execute(stmt.order_by(TestRelease.test_release_no, TestRelease.id).limit(limit).offset(offset)).all()
    return {'total': total, 'status_counts': statuses, 'items': [{**basic(t),
        'release': {'id': str(r.id), 'type': r.release_type, 'version': r.version},
        'software': {'code': p.code, 'name': p.name}, 'snapshot_no': s.snapshot_no,
        'context_consistent': s.release_id == r.id and s.status == 'FROZEN'} for t, r, s, p in page],
        'next_offset': offset + limit if offset + limit < total else None}


@router.get('/{test_release_no}')
def test_detail(test_release_no: str, db: Session = Depends(get_db)):
    row = find_test(db, test_release_no)
    release = db.get(Release, row.release_id)
    snapshot = db.get(ReleaseSnapshot, row.snapshot_id)
    latest_snapshot = db.scalars(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id == row.release_id,
        ReleaseSnapshot.status == 'FROZEN').order_by(ReleaseSnapshot.snapshot_number.desc())).first()
    artifacts = db.scalars(select(SnapshotArtifact).where(SnapshotArtifact.snapshot_id == row.snapshot_id)
        .order_by(SnapshotArtifact.component_code, SnapshotArtifact.filename)).all()
    stmt = select(DvpExecution).where(DvpExecution.test_release_id == row.id)
    records = db.scalar(select(func.count()).select_from(stmt.subquery()))
    match = stmt.where(DvpExecution.release_id == row.release_id, DvpExecution.snapshot_id == row.snapshot_id)
    matching_records = db.scalar(select(func.count()).select_from(match.subquery()))
    latest = select(DvpExecution.dvp_item_id.label('item_id'), func.max(DvpExecution.execution_no).label('number'))\
        .where(DvpExecution.test_release_id == row.id, DvpExecution.release_id == row.release_id,
               DvpExecution.snapshot_id == row.snapshot_id).group_by(DvpExecution.dvp_item_id).subquery()
    outcomes = dict(db.execute(select(DvpExecution.result, func.count()).join(latest,
        (DvpExecution.dvp_item_id == latest.c.item_id) & (DvpExecution.execution_no == latest.c.number))
        .group_by(DvpExecution.result)).all())
    return {**basic(row), 'release': {'id': str(release.id), 'type': release.release_type, 'version': release.version} if release else None,
        'snapshot': {'id': str(snapshot.id), 'snapshot_no': snapshot.snapshot_no, 'status': snapshot.status,
            'content_hash': snapshot.content_hash, 'number': snapshot.snapshot_number} if snapshot else None,
        'is_latest_frozen_snapshot': bool(latest_snapshot and latest_snapshot.id == row.snapshot_id),
        'context_consistent': bool(release and snapshot and snapshot.release_id == row.release_id and snapshot.status == 'FROZEN'),
        'artifacts': [{'id': str(a.id), 'component_code': a.component_code, 'component_version': a.component_version, 'filename': a.filename,
            'artifact_type': a.artifact_type, 'sha256': a.sha256, 'classification': a.classification,
            'distribution_level': a.distribution_level, 'ai_access_policy': a.ai_access_policy} for a in artifacts],
        'execution_summary': {'records': records, 'matching_records': matching_records,
            'mismatched_records': records - matching_records, 'executed_items': sum(outcomes.values()),
            'latest_result_counts': outcomes},
        'notice': 'Purpose-limited test record. Status and test results do not grant production release, distribution or deployment permission.'}


@router.get('/{test_release_no}/executions')
def test_executions(test_release_no: str, limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100000), db: Session = Depends(get_db)):
    test = find_test(db, test_release_no)
    stmt = select(DvpExecution, DvpItem).join(DvpItem, DvpItem.id == DvpExecution.dvp_item_id)
    stmt = stmt.where(DvpExecution.test_release_id == test.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(DvpExecution.executed_at.desc(), DvpExecution.id.desc()).limit(limit).offset(offset)).all()
    evidence = serialize_executions(db, [e for e, _ in rows])
    return {'total': total, 'items': [{**data, 'id': str(e.id), 'dvp_item_id': str(item.id), 'item_no': item.item_no,
        'title': item.title, 'matches_test_context': e.release_id == test.release_id and e.snapshot_id == test.snapshot_id}
        for (e, item), data in zip(rows, evidence)], 'next_offset': offset + limit if offset + limit < total else None}


@router.post('', status_code=201)
def create_test_release(data: TestReleaseInput, response: Response, db: Session = Depends(get_db)):
    try:
        row, created = create_test_draft(db, data)
        db.commit(); db.refresh(row)
        response.status_code = 201 if created else 200
        return basic(row)
    except TestReleaseError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'test release request conflict') from exc
    except Exception:
        db.rollback()
        raise
