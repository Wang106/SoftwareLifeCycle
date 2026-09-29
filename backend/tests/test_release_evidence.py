import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.dashboard import application_release_evidence
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.testing import DvpExecution, DvpItem


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class EvidenceSession:
    def __init__(self, release=None, snapshot=None, artifacts=(), executions=(), items=()):
        self.release = release
        self.data = {ReleaseSnapshot: [snapshot] if snapshot else [], SnapshotArtifact: artifacts,
                     DvpExecution: executions, DvpItem: items}

    def get(self, model, identifier):
        return self.release if model is Release and self.release and self.release.id == identifier else None

    def scalars(self, statement):
        return Rows(self.data[statement.column_descriptions[0]["entity"]])


def test_evidence_returns_only_latest_execution_on_latest_snapshot():
    release = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    snapshot = ReleaseSnapshot(id=uuid.uuid4(), release_id=release.id, snapshot_no="SNAP-008", snapshot_number=2)
    item = DvpItem(id=uuid.uuid4(), plan_id=uuid.uuid4(), item_no="DVP-032", title="Low-temp charging", scope="SOFTWARE_TEST")
    artifact = SnapshotArtifact(id=uuid.uuid4(), snapshot_id=snapshot.id, source_artifact_id=uuid.uuid4(), component_code="BMS", filename="BMS.hex", artifact_type="HEX", sha256="a" * 64, classification="CONFIDENTIAL", distribution_level="CONTROLLED_EXTERNAL", ai_access_policy="DENY", storage_reference="private://file")
    time = datetime(2026, 9, 29, tzinfo=timezone.utc)
    def execution(number, snapshot_id):
        return DvpExecution(id=uuid.uuid4(), dvp_item_id=item.id, execution_no=number,
                            release_id=release.id, snapshot_id=snapshot_id, result="PASS" if number == 2 else "FAIL", executed_at=time)
    stale = execution(3, uuid.uuid4())
    latest = execution(2, snapshot.id)
    earlier = execution(1, snapshot.id)
    db = EvidenceSession(release, snapshot, [artifact], [stale, latest, earlier], [item])
    result = application_release_evidence(release.id, db=db)
    assert result["snapshot_no"] == "SNAP-008"
    assert len(result["artifacts"]) == 1
    assert result["artifacts"][0]["sha256"] == "a" * 64
    assert "storage_reference" not in result["artifacts"][0]
    assert [(row["item_no"], row["execution_no"]) for row in result["executions"]] == [("DVP-032", 2)]
    assert result["other_snapshot_executions"] == 1


def test_evidence_without_snapshot_is_empty_and_standard_is_rejected():
    release = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.3")
    assert application_release_evidence(release.id, db=EvidenceSession(release)) == {
        "snapshot_no": None, "artifacts": [], "executions": [], "other_snapshot_executions": 0,
    }
    standard = Release(id=uuid.uuid4(), software_id=release.software_id, release_type="STANDARD", version="5.1.12")
    with pytest.raises(HTTPException) as error:
        application_release_evidence(standard.id, db=EvidenceSession(standard))
    assert error.value.status_code == 404
