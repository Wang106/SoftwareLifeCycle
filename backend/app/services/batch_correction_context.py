"""Private preparation context: one coherent, read-only Batch/head projection.

Authorization is established by the route, not by public history or this projection.
The observed revision is not a reservation: every correction command revalidates it.
"""
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.production import Deployment, ProductionBatch
from app.models.production_history import BatchBaseline, BatchCorrection


def batch_correction_context(db: Session, deployment_no: str, batch_no: str):
    batch, baseline, correction = ProductionBatch, BatchBaseline, BatchCorrection
    fields = ['release_id', 'snapshot_id', 'started_at', 'ended_at', 'changeover_id', 'note']
    corrected = ['started_at', 'ended_at', 'changeover_id', 'note']
    columns = [batch.id.label('batch_id'), baseline.id.label('baseline_id'),
               baseline.source.label('source'), correction.id.label('head_id'), correction.revision]
    columns += [getattr(batch, f).label('physical_' + f) for f in fields]
    columns += [getattr(baseline, 'recorded_' + f if f in {'started_at', 'ended_at', 'note'} else f).label('base_' + f) for f in fields]
    columns += [getattr(correction, f).label('head_' + f) for f in corrected]
    row = db.execute(select(*columns).select_from(batch)
        .join(Deployment, Deployment.id == batch.deployment_id)
        .outerjoin(baseline, baseline.batch_id == batch.id)
        .outerjoin(correction, (correction.batch_id == batch.id) & (correction.baseline_id == baseline.id))
        .where(Deployment.deployment_no == deployment_no, batch.batch_no == batch_no)
        .order_by(correction.revision.desc()).limit(1)).mappings().first()
    if row is None:
        return None
    has_base, has_head = row['baseline_id'] is not None, row['head_id'] is not None
    values = {}
    for field in fields:
        prefix = 'head_' if has_head and field in corrected else 'base_' if has_base else 'physical_'
        value = row[prefix + field]
        if field.endswith('_id') and value is not None:
            value = str(value)
        elif field.endswith('_at') and value is not None:
            value = value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)
        values[field] = value
    state = {'LEGACY_CURRENT': 'LEGACY', 'IMPORTED_CURRENT': 'IMPORTED',
             'FIRST_RECORD': 'FIRST_RECORD'}.get(row['source'], 'NOT_RECORDED')
    return {'deployment_no': deployment_no, 'batch_no': batch_no, 'batch_id': str(row['batch_id']),
            'history_state': state + ('_CORRECTED' if has_head else ''),
            'expected_revision': row['revision'] if has_head else 0,
            'predecessor_id': str(row['head_id']) if has_head else None, **values}
