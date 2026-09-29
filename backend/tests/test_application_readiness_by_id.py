import uuid

import pytest
from fastapi import HTTPException

from app.api import dashboard
from app.models.core import Release
from app.models.governance import PolicyException
from app.models.snapshot import ReleaseSnapshot


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class Session:
    def __init__(self, releases=(), snapshot=None, exceptions=()):
        self.objects = {(type(obj), obj.id): obj for obj in (*releases, *([snapshot] if snapshot else []))}
        self.exceptions = exceptions

    def get(self, model, identifier):
        return self.objects.get((model, identifier))

    def scalars(self, statement):
        assert statement.column_descriptions[0]["entity"] is PolicyException
        return Rows(self.exceptions)


def test_readiness_by_id_uses_exact_release_and_its_snapshot(monkeypatch):
    first = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    second = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    snapshot = ReleaseSnapshot(id=uuid.uuid4(), release_id=second.id, snapshot_no="SNAP-008",
        snapshot_number=8, status="FROZEN")
    exception = PolicyException(id=uuid.uuid4(), exception_no="PEX-0018", snapshot_id=snapshot.id,
        rule_code="VERIFICATION_CURRENT_SNAPSHOT_COMPLETE", scope="Verification", status="APPROVED",
        reason="Endurance pending")
    selected = []

    class Coverage:
        def __init__(self, db):
            pass

        def release_coverage(self, release_id):
            selected.append(release_id)
            return self

        def as_dict(self):
            return {"snapshot_id": str(snapshot.id), "snapshot_no": snapshot.snapshot_no,
                    "dvp_execution_coverage": 67, "current_snapshot_executed": 2,
                    "required_dvp_total": 3, "change_coverage": 100, "change_points_covered": 2,
                    "change_points_total": 2, "issue_verification_coverage": 100,
                    "issues_covered": 1, "issues_total": 1, "snapshot_match": True}

    class Policy:
        def __init__(self, db):
            pass

        def summarize_release(self, release_id):
            selected.append(release_id)
            return self

        def as_dict(self):
            return {"artifact_total": 4, "sha_completeness": 100, "sha_complete": 4,
                    "policy_completeness": 100, "policy_complete": 4}

    monkeypatch.setattr(dashboard, "TraceabilityService", Coverage)
    monkeypatch.setattr(dashboard, "ArtifactPolicyService", Policy)
    result = dashboard.application_release_readiness(second.id,
        db=Session([first, second], snapshot, [exception]))
    assert selected == [second.id, second.id]
    assert result["overall"] == "READY"
    assert result["coverage"]["snapshot_no"] == "SNAP-008"
    assert result["exceptions"][0]["exception_no"] == "PEX-0018"
    verification = next(row for row in result["rules"] if row["group"] == "Verification")
    assert (verification["raw"], verification["effective"]) == ("FAIL", "EXCEPTION_GRANTED")


def test_readiness_by_id_rejects_missing_or_standard_release():
    standard = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="STANDARD", version="5.1.12")
    db = Session([standard])
    for release_id in [standard.id, uuid.uuid4()]:
        with pytest.raises(HTTPException) as error:
            dashboard.application_release_readiness(release_id, db=db)
        assert error.value.status_code == 404
