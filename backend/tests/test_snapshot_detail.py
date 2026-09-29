import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.snapshots import snapshot_detail
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class Session:
    def __init__(self, snapshot, current=None, release=None, artifacts=(), rules=()):
        self.snapshot = snapshot
        self.current = current or snapshot
        self.release = release
        self.artifacts = artifacts
        self.rules = rules
        self.snapshot_queries = 0

    def get(self, model, identifier):
        assert model is Release
        assert identifier == self.snapshot.release_id
        return self.release

    def scalars(self, statement):
        model = statement.column_descriptions[0]['entity']
        if model is ReleaseSnapshot:
            self.snapshot_queries += 1
            return Rows([self.snapshot if self.snapshot_queries == 1 else self.current] if self.snapshot else [])
        if model is SnapshotArtifact:
            assert self.snapshot.id in statement.compile().params.values()
            return Rows(self.artifacts)
        if model is SnapshotArtifactDistributionRule:
            return Rows(self.rules)
        raise AssertionError(model)


def make_snapshot(release, number):
    return ReleaseSnapshot(id=uuid.uuid4(), release_id=release.id, snapshot_no=f'SNAP-{number:03}',
        snapshot_number=number, status='FROZEN', content_hash=str(number) * 64,
        created_at=datetime(2026, 9, 29, tzinfo=timezone.utc))


def test_historical_snapshot_uses_its_own_frozen_manifest_and_rules():
    release = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type='APPLICATION', version='2.3.4')
    old, current = make_snapshot(release, 1), make_snapshot(release, 2)
    artifact = SnapshotArtifact(id=uuid.uuid4(), snapshot_id=old.id, source_artifact_id=uuid.uuid4(),
        filename='old.hex', artifact_type='HEX', component_code='APP', sha256='a' * 64,
        classification='CONFIDENTIAL', distribution_level='CONTROLLED_EXTERNAL', ai_access_policy='DENY')
    rule = SnapshotArtifactDistributionRule(id=uuid.uuid4(), snapshot_artifact_id=artifact.id,
        recipient_type='CUSTOMER', recipient_code='CUS-001', purpose='VALIDATION', decision='APPROVAL_REQUIRED')
    result = snapshot_detail(old.snapshot_no, db=Session(old, current, release, [artifact], [rule]))
    assert result['id'] == str(old.id)
    assert result['content_hash'] == old.content_hash
    assert result['is_current_snapshot'] is False
    assert result['artifacts'][0]['filename'] == 'old.hex'
    assert result['artifacts'][0]['policy_rules'][0]['decision'] == 'APPROVAL_REQUIRED'
    assert 'storage_reference' not in result['artifacts'][0]


def test_standard_snapshot_with_no_artifacts_is_not_fabricated():
    release = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type='STANDARD', version='5.1.12')
    snapshot = make_snapshot(release, 1)
    result = snapshot_detail(snapshot.snapshot_no, db=Session(snapshot, release=release))
    assert result['is_current_snapshot'] is True
    assert result['release']['type'] == 'STANDARD'
    assert result['artifacts'] == []


def test_snapshot_missing_returns_404_without_using_latest():
    with pytest.raises(HTTPException) as error:
        snapshot_detail('UNKNOWN', db=Session(None))
    assert error.value.status_code == 404
