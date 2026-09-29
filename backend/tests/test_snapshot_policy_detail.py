import uuid

import pytest
from fastapi import HTTPException

from app.api.dashboard import application_snapshot_policy
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class Session:
    def __init__(self, releases=(), snapshots=(), artifacts=(), rules=()):
        self.objects = {release.id: release for release in releases}
        self.data = {ReleaseSnapshot: snapshots, SnapshotArtifact: artifacts,
                     SnapshotArtifactDistributionRule: rules}

    def get(self, model, identifier):
        return self.objects.get(identifier) if model is Release else None

    def scalars(self, statement):
        return Rows(self.data[statement.column_descriptions[0]["entity"]])


def test_snapshot_policy_uses_frozen_artifacts_and_rules_without_storage_reference():
    first = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    second = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    snapshot = ReleaseSnapshot(id=uuid.uuid4(), release_id=second.id, snapshot_no="SNAP-008",
        snapshot_number=8, status="FROZEN", content_hash="a" * 64)
    artifact = SnapshotArtifact(id=uuid.uuid4(), snapshot_id=snapshot.id,
        source_artifact_id=uuid.uuid4(), component_code="BMS", component_version="2.3.4",
        filename="BMS.hex", artifact_type="HEX", sha256="b" * 64,
        classification="CONFIDENTIAL", distribution_level="CONTROLLED_EXTERNAL",
        ai_access_policy="DENY", storage_reference="private://secret-file")
    rule = SnapshotArtifactDistributionRule(id=uuid.uuid4(), snapshot_artifact_id=artifact.id,
        recipient_type="CUSTOMER", recipient_code="CUS-001", purpose="PRODUCTION", decision="APPROVAL_REQUIRED")

    result = application_snapshot_policy(second.id, db=Session([first, second], [snapshot], [artifact], [rule]))
    assert result["snapshot"]["content_hash"] == "a" * 64
    assert result["artifacts"][0]["filename"] == "BMS.hex"
    assert result["artifacts"][0]["policy_rules"] == [{
        "recipient_type": "CUSTOMER", "purpose": "PRODUCTION",
        "recipient_code": "CUS-001", "decision": "APPROVAL_REQUIRED",
    }]
    assert "storage_reference" not in result["artifacts"][0]


def test_snapshot_policy_empty_release_and_rejects_wrong_release_type():
    application = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    standard = Release(id=uuid.uuid4(), software_id=application.software_id, release_type="STANDARD", version="5.1.12")
    db = Session([application, standard])
    assert application_snapshot_policy(application.id, db=db) == {"snapshot": None, "artifacts": []}
    for release_id in (standard.id, uuid.uuid4()):
        with pytest.raises(HTTPException) as error:
            application_snapshot_policy(release_id, db=db)
        assert error.value.status_code == 404
