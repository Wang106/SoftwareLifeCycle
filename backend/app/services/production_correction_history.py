"""Bounded public-sample history projection; not an authorization for real data.

One SQL statement captures parent binding, baseline, newest corrections and total
count from the same statement snapshot. Metadata labels are separate bounded reads;
no writes, row locks, identity columns or command request payloads are loaded.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.core import Release
from app.models.production import Deployment, ProductionBatch, SoftwareChangeover
from app.models.production_history import BatchBaseline, BatchCorrection, ChangeoverBaseline, ChangeoverCorrection
from app.models.snapshot import ReleaseSnapshot

HISTORY_LIMIT = 50


def correction_history(db: Session, deployment_no: str, kind: str, record_no: str):
    changeover = kind == 'changeover'
    model, baseline, correction, number, target = (
        (SoftwareChangeover, ChangeoverBaseline, ChangeoverCorrection, 'changeover_no', 'changeover_id')
        if changeover else (ProductionBatch, BatchBaseline, BatchCorrection, 'batch_no', 'batch_id'))
    fields = (['from_release_id', 'changed_at', 'note'] if changeover else
              ['changeover_id', 'started_at', 'ended_at', 'note'])
    fixed = ['to_release_id'] if changeover else ['release_id', 'snapshot_id']
    base_names = {field: ('recorded_' + field if field in {'changed_at', 'started_at', 'ended_at', 'note'} else field)
                  for field in fields + fixed}
    columns = [model.id.label('target_id'), model.status.label('stored_status')]
    columns += [getattr(model, f).label('physical_' + f) for f in fields + fixed]
    columns += [baseline.id.label('base_id'), baseline.source.label('base_source'),
                baseline.recorded_at.label('base_recorded_at'), baseline.baseline_event_no.label('base_event')]
    columns += [getattr(baseline, base_names[f]).label('base_' + f) for f in fields + fixed]
    columns += [correction.id.label('corr_id'), correction.revision.label('revision'),
                correction.predecessor_id.label('predecessor_id'),
                correction.correction_reason.label('correction_reason'),
                correction.recorded_at.label('recorded_at'), correction.audit_event_no.label('audit_event_no')]
    columns += [getattr(correction, f).label('corr_' + f) for f in fields]
    columns += [func.count(correction.id).over(partition_by=model.id).label('correction_count')]
    rows = db.execute(select(*columns).select_from(model)
        .join(Deployment, Deployment.id == model.deployment_id)
        .outerjoin(baseline, getattr(baseline, target) == model.id)
        .outerjoin(correction, (getattr(correction, target) == model.id) & (correction.baseline_id == baseline.id))
        .where(Deployment.deployment_no == deployment_no, getattr(model, number) == record_no)
        .order_by(correction.revision.desc()).limit(HISTORY_LIMIT)).mappings().all()
    if not rows:
        return None
    first = rows[0]
    has_baseline, has_head = first['base_id'] is not None, first['corr_id'] is not None
    raw_base = {f: first['base_' + f] for f in fields + fixed} if has_baseline else None
    raw_physical = {f: first['physical_' + f] for f in fields + fixed}
    raw_corrections = [({f: row['corr_' + f] for f in fields} |
                        {f: first['base_' + f] for f in fixed}) for row in rows if row['corr_id'] is not None]
    all_values = [raw_physical, *([raw_base] if raw_base else []), *raw_corrections]
    release_fields = ['from_release_id', 'to_release_id'] if changeover else ['release_id']
    release_ids = {v[f] for v in all_values for f in release_fields if v[f] is not None}
    releases = dict(db.execute(select(Release.id, Release.version).where(Release.id.in_(release_ids))).all()) if release_ids else {}
    snapshots, changeovers = {}, {}
    if not changeover:
        snapshot_ids = {v['snapshot_id'] for v in all_values if v['snapshot_id'] is not None}
        snapshots = dict(db.execute(select(ReleaseSnapshot.id, ReleaseSnapshot.snapshot_no).where(ReleaseSnapshot.id.in_(snapshot_ids))).all()) if snapshot_ids else {}
        changeover_ids = {v['changeover_id'] for v in all_values if v['changeover_id'] is not None}
        # Only label references belonging to this exact parent; don't disclose a foreign child label.
        changeovers = dict(db.execute(select(SoftwareChangeover.id, SoftwareChangeover.changeover_no)
            .join(Deployment, Deployment.id == SoftwareChangeover.deployment_id)
            .where(SoftwareChangeover.id.in_(changeover_ids), Deployment.deployment_no == deployment_no)).all()) if changeover_ids else {}

    def values(raw):
        value = {f: str(v) if f.endswith('_id') and v is not None else v for f, v in raw.items()}
        if changeover:
            value.update(from_version=releases.get(raw['from_release_id']), to_version=releases.get(raw['to_release_id']))
        else:
            value.update(version=releases.get(raw['release_id']), snapshot_no=snapshots.get(raw['snapshot_id']),
                         changeover_no=changeovers.get(raw['changeover_id']))
        return value

    prefix = {'LEGACY_CURRENT': 'LEGACY', 'IMPORTED_CURRENT': 'IMPORTED', 'FIRST_RECORD': 'FIRST_RECORD'}.get(first['base_source'], 'NOT_RECORDED')
    count = int(first['correction_count'])
    return {
        'kind': kind, 'record_no': record_no, 'deployment_no': deployment_no,
        'stored_status': first['stored_status'],
        'history_state': prefix + ('_CORRECTED' if has_head else ''),
        'recorded_baseline': {'source': first['base_source'], 'recorded_at': first['base_recorded_at'],
                             'baseline_event_no': first['base_event'], 'values': values(raw_base)} if has_baseline else None,
        'effective': {'revision': first['revision'] if has_head else 0,
                      'head_id': str(first['corr_id']) if has_head else None,
                      'values': values(raw_corrections[0] if has_head else raw_base if has_baseline else raw_physical)},
        'correction_count': count, 'limit': HISTORY_LIMIT, 'truncated': count > HISTORY_LIMIT,
        'corrections': [
            {'id': str(row['corr_id']), 'revision': row['revision'],
             'predecessor_id': str(row['predecessor_id']) if row['predecessor_id'] else None,
             'correction_reason': row['correction_reason'], 'recorded_at': row['recorded_at'],
             'audit_event_no': row['audit_event_no'], 'values': values(raw)}
            for row, raw in zip((r for r in rows if r['corr_id'] is not None), raw_corrections)],
    }
