"""Bounded frozen file comparison using SQL joins and counted rule multisets."""
from sqlalchemy import case, func, literal, or_, select, union
from app.models.snapshot import SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule

VALUE_FIELDS = ('artifact_type', 'component_version', 'sha256', 'classification',
                'distribution_level', 'ai_access_policy')
KINDS = ('added', 'removed', 'modified', 'unchanged')


def duplicate_identity(snapshot_id):
    a = SnapshotArtifact
    return select(a.component_code, a.filename).where(a.snapshot_id == snapshot_id)\
        .group_by(a.component_code, a.filename).having(func.count() > 1)\
        .order_by(a.component_code, a.filename).limit(1)


def comparison_rows(source_id, target_id):
    a = SnapshotArtifact.__table__
    before, after = a.alias('before_file'), a.alias('after_file')
    keys = union(select(a.c.component_code, a.c.filename).where(a.c.snapshot_id == source_id),
                 select(a.c.component_code, a.c.filename).where(a.c.snapshot_id == target_id)).subquery('file_keys')
    r = SnapshotArtifactDistributionRule.__table__
    def groups(file):
        return select(r.c.recipient_type, r.c.purpose, r.c.recipient_code, r.c.decision,
                      func.count().label('copies')).where(r.c.snapshot_artifact_id == file.c.id)\
            .group_by(r.c.recipient_type, r.c.purpose, r.c.recipient_code, r.c.decision).correlate(file)
    # EXCEPT compares NULL as a value and includes multiplicities. UUIDs and
    # insertion/order do not matter; NULL and empty recipient codes are distinct.
    old_rules, new_rules = groups(before), groups(after)
    policy_changed = or_(old_rules.except_(new_rules).exists(), new_rules.except_(old_rules).exists())
    changes = [before.c[field].is_distinct_from(after.c[field]) for field in VALUE_FIELDS] + [policy_changed]
    kind = case((before.c.id.is_(None), literal('added')), (after.c.id.is_(None), literal('removed')),
                (or_(*changes), literal('modified')), else_=literal('unchanged'))
    def rule_count(file):
        return select(func.count()).select_from(r).where(r.c.snapshot_artifact_id == file.c.id)\
            .correlate(file).scalar_subquery()
    columns = [keys.c.component_code, keys.c.filename, kind.label('change_type')]
    for prefix, file in [('before', before), ('after', after)]:
        columns.extend([file.c.id.label(prefix+'_id'), rule_count(file).label(prefix+'_rule_count')])
        columns.extend(file.c[field].label(prefix+'_'+field) for field in VALUE_FIELDS)
    columns.extend(change.label('changed_'+field) for field, change in zip((*VALUE_FIELDS,'policy_rules'), changes))
    joined = keys.outerjoin(before, (before.c.snapshot_id == source_id) &
        (before.c.component_code == keys.c.component_code) & (before.c.filename == keys.c.filename))\
        .outerjoin(after, (after.c.snapshot_id == target_id) &
        (after.c.component_code == keys.c.component_code) & (after.c.filename == keys.c.filename))
    return select(*columns).select_from(joined).subquery('comparison')


def public_file(row):
    def values(prefix):
        if row[prefix+'_id'] is None:
            return None
        return {field: row[prefix+'_'+field] for field in VALUE_FIELDS} | {
            'snapshot_artifact_id': str(row[prefix+'_id']), 'rule_count': row[prefix+'_rule_count']}
    return {'component_code': row['component_code'], 'filename': row['filename'],
        'change_type': row['change_type'], 'changed_fields': [field for field in (*VALUE_FIELDS,'policy_rules')
            if row['before_id'] is not None and row['after_id'] is not None and row['changed_'+field]],
        'before': values('before'), 'after': values('after')}
