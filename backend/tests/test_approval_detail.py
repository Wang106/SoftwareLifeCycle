import uuid

import pytest
from fastapi import HTTPException

from app.api.dashboard import get_approval
from app.models.approval import ApprovalAction, ApprovalRequest, ApprovalStep
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class Session:
    def __init__(self, approval=None, steps=(), actions=(), objects=()):
        self.approval = approval
        self.steps = steps
        self.actions = actions
        self.objects = {(type(obj), obj.id): obj for obj in objects}

    def scalars(self, statement):
        model = statement.column_descriptions[0]["entity"]
        if model is ApprovalRequest:
            return Rows([self.approval] if self.approval else [])
        if model is ApprovalStep:
            return Rows(self.steps)
        if model is ApprovalAction:
            return Rows(self.actions)
        raise AssertionError(model)

    def get(self, model, identifier):
        return self.objects.get((model, identifier))


def test_approval_detail_keeps_exact_release_snapshot_and_action_step():
    release = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    snapshot = ReleaseSnapshot(id=uuid.uuid4(), release_id=release.id, snapshot_no="SNAP-008",
        snapshot_number=8, content_hash="a" * 64)
    approval = ApprovalRequest(id=uuid.uuid4(), approval_no="APR-0121", target_type="RELEASE",
        target_id=release.id, snapshot_id=snapshot.id, status="APPROVED", submitted_by="Lead")
    step = ApprovalStep(id=uuid.uuid4(), approval_request_id=approval.id, step_order=1,
        role_name="Test Lead", status="APPROVED")
    action = ApprovalAction(id=uuid.uuid4(), approval_request_id=approval.id,
        step_id=step.id, actor_name="Tester", action="APPROVED", comment="Evidence reviewed")

    detail = get_approval("APR-0121", db=Session(approval, [step], [action], [release, snapshot]))
    assert detail["target_id"] == str(release.id)
    assert detail["target"] == {"release_type": "APPLICATION", "release_version": "2.3.4",
                                "snapshot_no": "SNAP-008", "content_hash": "a" * 64}
    assert detail["actions"][0]["step_id"] == str(step.id)


def test_approval_detail_missing_record_returns_404():
    with pytest.raises(HTTPException) as error:
        get_approval("APR-MISSING", db=Session())
    assert error.value.status_code == 404
