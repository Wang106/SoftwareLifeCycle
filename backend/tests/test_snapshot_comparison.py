import copy
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.snapshots import compare_snapshots
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule
from app.services.snapshot_comparison import SnapshotComparisonError, compare_manifests


def artifact(filename='app.hex', **changes):
    return {'component_code': 'APP', 'filename': filename, 'artifact_type': 'HEX',
            'component_version': '1.0', 'sha256': 'a' * 64, 'classification': 'CONFIDENTIAL',
            'distribution_level': 'EXTERNAL', 'ai_access_policy': 'DENY',
            'policy_rules': [{'recipient_type': 'CUSTOMER', 'recipient_code': 'A',
                              'purpose': 'PRODUCTION', 'decision': 'ALLOW'}], **changes}


def test_added_removed_modified_unchanged_and_reverse_comparison():
    before = [artifact('removed.hex'), artifact('changed.hex'), artifact('same.hex')]
    after = [artifact('added.hex'), artifact('changed.hex', sha256='b' * 64), artifact('same.hex')]
    original = copy.deepcopy((before, after))
    result = compare_manifests(before, after)
    assert result['summary'] == {'added': 1, 'removed': 1, 'modified': 1, 'unchanged': 1}
    changed = next(row for row in result['files'] if row['filename'] == 'changed.hex')
    assert changed['changed_fields'] == ['sha256']
    assert changed['before']['sha256'] == 'a' * 64
    assert changed['after']['sha256'] == 'b' * 64
    reverse = compare_manifests(after, before)
    assert next(row for row in reverse['files'] if row['filename'] == 'added.hex')['change_type'] == 'removed'
    assert next(row for row in reverse['files'] if row['filename'] == 'removed.hex')['change_type'] == 'added'
    assert (before, after) == original


@pytest.mark.parametrize(('field', 'value'), [
    ('artifact_type', 'ELF'), ('component_version', '2.0'), ('sha256', 'c' * 64),
    ('classification', 'STRICTLY_CONFIDENTIAL'), ('distribution_level', 'INTERNAL_ONLY'),
    ('ai_access_policy', 'LOCAL_ONLY'), ('policy_rules', []),
])
def test_each_frozen_field_is_compared_independently(field, value):
    result = compare_manifests([artifact()], [artifact(**{field: value})])
    assert result['summary']['modified'] == 1
    assert result['files'][0]['changed_fields'] == [field]


def test_rule_order_and_record_ids_are_not_changes():
    rules = artifact()['policy_rules'] + [{'recipient_type': 'FACTORY', 'recipient_code': None,
                                         'purpose': 'PRODUCTION', 'decision': 'DENY'}]
    result = compare_manifests([artifact(id='old', policy_rules=rules)],
                              [artifact(id='new', policy_rules=list(reversed(rules)))])
    assert result['summary']['unchanged'] == 1


@pytest.mark.parametrize(('field', 'value'), [('recipient_code', 'B'), ('purpose', 'VALIDATION'),
                                           ('decision', 'APPROVAL_REQUIRED')])
def test_recipient_rule_changes_are_detected_with_same_file_hash(field, value):
    before = artifact()
    after = copy.deepcopy(before)
    after['policy_rules'][0][field] = value
    result = compare_manifests([before], [after])
    assert result['files'][0]['changed_fields'] == ['policy_rules']


def test_same_filename_in_different_components_is_not_collapsed():
    result = compare_manifests([artifact(), artifact(component_code='BOOT')], [artifact()])
    assert result['summary']['removed'] == 1
    assert result['summary']['unchanged'] == 1


def test_duplicate_file_identity_is_rejected():
    with pytest.raises(SnapshotComparisonError, match='Ambiguous'):
        compare_manifests([artifact(), artifact()], [])
    with pytest.raises(SnapshotComparisonError):
        compare_manifests([], [artifact(), artifact()])


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class FrozenSession:
    def __init__(self, snapshots, artifacts=(), rules=()):
        self.snapshots, self.artifacts, self.rules = snapshots, artifacts, rules

    def scalars(self, statement):
        model = statement.column_descriptions[0]['entity']
        parameters = list(statement.compile().params.values())
        if model is ReleaseSnapshot:
            return Rows([row for row in self.snapshots if row.snapshot_no == parameters[0]])
        if model is SnapshotArtifact:
            return Rows([row for row in self.artifacts if row.snapshot_id == parameters[0]])
        if model is SnapshotArtifactDistributionRule:
            return Rows([row for row in self.rules if row.snapshot_artifact_id in parameters[0]])
        raise AssertionError('Comparison must only read frozen models')


def snapshot(number, release_id):
    return ReleaseSnapshot(id=uuid.uuid4(), release_id=release_id, snapshot_no=f'SNAP-{number}',
        snapshot_number=number, status='FROZEN', content_hash='a' * 64,
        created_at=datetime(2026, 9, 29, tzinfo=timezone.utc),
        release_metadata_json={'version': '1.0', 'release_type': 'APPLICATION'})


def test_api_reads_frozen_policies_even_when_snapshot_hashes_match():
    release_id = uuid.uuid4()
    old, new = snapshot(1, release_id), snapshot(2, release_id)
    new.release_metadata_json = {'version': '2.0', 'release_type': 'APPLICATION'}
    artifacts = [SnapshotArtifact(id=uuid.uuid4(), snapshot_id=s.id, **{
        key: value for key, value in artifact().items() if key != 'policy_rules'}) for s in [old, new]]
    rules = [SnapshotArtifactDistributionRule(id=uuid.uuid4(), snapshot_artifact_id=row.id,
        recipient_type='CUSTOMER', recipient_code='A', purpose='PRODUCTION', decision=decision)
        for row, decision in zip(artifacts, ['ALLOW', 'DENY'])]
    result = compare_snapshots(old.snapshot_no, new.snapshot_no, db=FrozenSession([old, new], artifacts, rules))
    assert result['content_hash_matches'] is True
    assert result['summary']['modified'] == 1
    assert result['files'][0]['changed_fields'] == ['policy_rules']
    assert result['metadata_changes'] == [{'field': 'version', 'before': '1.0', 'after': '2.0'}]
    assert 'storage_reference' not in result['files'][0]['before']


def test_same_snapshot_and_empty_manifest_are_valid():
    row = snapshot(1, uuid.uuid4())
    result = compare_snapshots(row.snapshot_no, row.snapshot_no, db=FrozenSession([row]))
    assert result['summary'] == dict.fromkeys(('added', 'removed', 'modified', 'unchanged'), 0)
    assert result['files'] == []
    assert result['metadata_changes'] == []


def test_cross_release_comparison_is_rejected():
    old, new = snapshot(1, uuid.uuid4()), snapshot(2, uuid.uuid4())
    with pytest.raises(HTTPException) as error:
        compare_snapshots(old.snapshot_no, new.snapshot_no, db=FrozenSession([old, new]))
    assert error.value.status_code == 409


def test_api_duplicate_frozen_identity_returns_409():
    row = snapshot(1, uuid.uuid4())
    artifacts = [SnapshotArtifact(id=uuid.uuid4(), snapshot_id=row.id, **{
        key: value for key, value in artifact().items() if key != 'policy_rules'}) for _ in range(2)]
    with pytest.raises(HTTPException) as error:
        compare_snapshots(row.snapshot_no, row.snapshot_no, db=FrozenSession([row], artifacts))
    assert error.value.status_code == 409


@pytest.mark.parametrize(('source_no', 'target_no'), [('missing', 'SNAP-1'), ('SNAP-1', 'missing')])
def test_missing_comparison_snapshot_returns_404(source_no, target_no):
    row = snapshot(1, uuid.uuid4())
    with pytest.raises(HTTPException) as error:
        compare_snapshots(source_no, target_no, db=FrozenSession([row]))
    assert error.value.status_code == 404
