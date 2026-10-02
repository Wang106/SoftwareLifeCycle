"""Exact same-release comparison summaries and bounded file differences."""
import uuid
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session
from app.api.snapshot_views import SummarySelection, exact_snapshot
from app.core.db import get_db
from app.services.snapshot_comparison_reads import KINDS, comparison_rows, duplicate_identity, public_file

router = APIRouter(prefix='/api/v1/snapshots', tags=['snapshot comparison pages'])

class ComparisonPage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: uuid.UUID
    target_id: uuid.UUID
    show: Literal['changes', 'all'] = 'changes'
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100000)


def pair(db, source_no, target_no, source_id=None, target_id=None):
    source = exact_snapshot(db, source_no, source_id)
    target = source if source_no == target_no and (target_id is None or target_id == source.id) else exact_snapshot(db, target_no, target_id)
    if source.release_id != target.release_id:
        raise HTTPException(409, 'snapshots must belong to the same release')
    for sid in dict.fromkeys([source.id, target.id]):
        duplicate = db.execute(duplicate_identity(sid)).first()
        if duplicate is not None:
            raise HTTPException(409, f'Ambiguous frozen file identity: {duplicate.component_code} / {duplicate.filename}')
    return source, target


def context(source, target):
    def identity(snapshot):
        return {'id': str(snapshot.id), 'snapshot_no': snapshot.snapshot_no,
            'snapshot_number': snapshot.snapshot_number, 'content_hash': snapshot.content_hash,
            'created_at': snapshot.created_at, 'status': snapshot.status}
    return {'release_id': str(source.release_id), 'source': identity(source), 'target': identity(target)}


@router.get('/{source_no}/comparison/{target_no}/summary')
def comparison_summary(source_no: str, target_no: str, filters: Annotated[SummarySelection, Query()], db: Session = Depends(get_db)):
    source, target = pair(db, source_no, target_no)
    rows = comparison_rows(source.id, target.id)
    counts = db.execute(select(*(func.coalesce(func.sum(case((rows.c.change_type == kind, 1), else_=0)), 0).label(kind)
        for kind in KINDS))).mappings().one()
    old, new = source.release_metadata_json or {}, target.release_metadata_json or {}
    return context(source, target) | {'content_hash_matches': source.content_hash == target.content_hash,
        'metadata_changes': [{'field': field, 'before': old.get(field), 'after': new.get(field)}
            for field in ('version','release_type') if old.get(field) != new.get(field)],
        'summary': dict(counts)}


@router.get('/{source_no}/comparison/{target_no}/files')
def comparison_files(source_no: str, target_no: str, filters: Annotated[ComparisonPage, Query()], db: Session = Depends(get_db)):
    source, target = pair(db, source_no, target_no, filters.source_id, filters.target_id)
    rows = comparison_rows(source.id, target.id)
    stmt = select(rows)
    if filters.show == 'changes':
        stmt = stmt.where(rows.c.change_type != 'unchanged')
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.execute(stmt.order_by(rows.c.component_code, rows.c.filename)
        .limit(filters.limit).offset(filters.offset)).mappings()
    return context(source, target) | {'show': filters.show, 'total': total, 'limit': filters.limit,
        'offset': filters.offset, 'next_offset': filters.offset + filters.limit if filters.offset + filters.limit < total else None,
        'items': [public_file(row) for row in items]}
