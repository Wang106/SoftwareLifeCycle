import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.api.dashboard import application_release_decision
from app.models.approval import ApprovalRequest, ReleaseDecision
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None


class DecisionSession:
    def __init__(self, objects, query_rows):
        self.objects = objects
        self.query_rows = list(query_rows)

    def get(self, model, identifier):
        return self.objects.get((model, identifier))

    def scalars(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        return Rows(self.query_rows.pop(0).get(entity, []))


def test_decision_rejects_non_application_release():
    release = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="STANDARD", version="5.1.12")
    db = DecisionSession({(Release, release.id): release}, [])
    with pytest.raises(HTTPException) as error:
        application_release_decision(release.id, db=db)
    assert error.value.status_code == 404


def test_decision_keeps_historical_snapshot_distinct_from_current():
    release = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    old_snapshot = ReleaseSnapshot(id=uuid.uuid4(), release_id=release.id, snapshot_no="SNAP-007", snapshot_number=1, status="FROZEN", content_hash="a" * 64)
    current_snapshot = ReleaseSnapshot(id=uuid.uuid4(), release_id=release.id, snapshot_no="SNAP-008", snapshot_number=2, status="FROZEN", content_hash="b" * 64)
    approval = ApprovalRequest(id=uuid.uuid4(), approval_no="APR-0121", target_type="RELEASE", target_id=release.id, snapshot_id=old_snapshot.id, status="APPROVED")
    decision = ReleaseDecision(id=uuid.uuid4(), decision_no="RD-0081", release_id=release.id,
        snapshot_id=old_snapshot.id, approval_request_id=approval.id, readiness_status="READY",
        decision="RELEASE", decided_by="Release Manager", decision_notes="Released frozen snapshot",
        decided_at=datetime.now(UTC) - timedelta(days=1))
    objects = {(Release, release.id): release, (ReleaseSnapshot, old_snapshot.id): old_snapshot,
               (ApprovalRequest, approval.id): approval}
    db = DecisionSession(objects, [{ReleaseSnapshot: [current_snapshot]}, {ReleaseDecision: [decision]}])

    result = application_release_decision(release.id, db=db)

    assert result["release_id"] == str(release.id)
    assert result["current_snapshot_no"] == "SNAP-008"
    assert result["decision"]["snapshot_no"] == "SNAP-007"
    assert result["decision"]["is_current_snapshot"] is False
    assert result["decision"]["approval_status"] == "APPROVED"


def test_decision_returns_none_without_formal_record():
    release = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.5")
    db = DecisionSession({(Release, release.id): release}, [{ReleaseSnapshot: []}, {ReleaseDecision: []}])

    assert application_release_decision(release.id, db=db) == {
        "release_id": str(release.id), "current_snapshot_no": None, "decision": None,
    }
