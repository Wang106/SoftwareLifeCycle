"""Private preparation context: one coherent, read-only Changeover/head projection.

Authorization is established by the route, not by public history or this projection.
The observed revision is not a reservation: every correction command revalidates it.
"""
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.production import Deployment, SoftwareChangeover
from app.models.production_history import ChangeoverBaseline, ChangeoverCorrection


def changeover_correction_context(db: Session, deployment_no: str, changeover_no: str):
    changeover, baseline, correction = SoftwareChangeover, ChangeoverBaseline, ChangeoverCorrection
    fields = ['from_release_id', 'to_release_id', 'changed_at', 'note']
    corrected = ['from_release_id', 'changed_at', 'note']
    columns = [changeover.id.label('changeover_id'), baseline.id.label('baseline_id'),
               baseline.source.label('source'), correction.id.label('head_id'), correction.revision]
    columns += [getattr(changeover, f).label('physical_' + f) for f in fields]
    columns += [getattr(baseline, 'recorded_' + f if f in {'changed_at', 'note'} else f).label('base_' + f) for f in fields]
    columns += [getattr(correction, f).label('head_' + f) for f in corrected]
    row = db.execute(select(*columns).select_from(changeover)
        .join(Deployment, Deployment.id == changeover.deployment_id)
        .outerjoin(baseline, baseline.changeover_id == changeover.id)
        .outerjoin(correction, (correction.changeover_id == changeover.id) & (correction.baseline_id == baseline.id))
        .where(Deployment.deployment_no == deployment_no, changeover.changeover_no == changeover_no)
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
    return {'deployment_no': deployment_no, 'changeover_no': changeover_no, 'changeover_id': str(row['changeover_id']),
            'history_state': state + ('_CORRECTED' if has_head else ''),
            'expected_revision': row['revision'] if has_head else 0,
            'predecessor_id': str(row['head_id']) if has_head else None, **values}
