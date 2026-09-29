import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.dashboard import dvp_item_detail, list_dvp
from app.models.change import SoftwareChangeRequest
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot
from app.models.testing import DvpExecution, DvpItem, DvpPlan, TestRelease as RecordedTestRelease


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class Session:
    def __init__(self, items=(), executions=(), objects=()):
        self.items = items
        self.executions = executions
        self.objects = {(type(obj), obj.id): obj for obj in objects}

    def scalars(self, statement):
        model = statement.column_descriptions[0]["entity"]
        if model is DvpItem:
            return Rows(self.items)
        if model is DvpExecution:
            return Rows(self.executions)
        raise AssertionError(model)

    def get(self, model, identifier):
        return self.objects.get((model, identifier))


def test_dvp_history_keeps_each_execution_on_its_recorded_snapshot():
    change = SoftwareChangeRequest(id=uuid.uuid4(), request_no="SCR-142", title="Charging correction",
        software_id=uuid.uuid4(), status="TESTING")
    plan = DvpPlan(id=uuid.uuid4(), change_request_id=change.id, plan_no="DVP-PLAN-142", title="Verification")
    item = DvpItem(id=uuid.uuid4(), plan_id=plan.id, item_no="DVP-032", title="Low-temp charging",
        scope="SOFTWARE_TEST", status="COMPLETED")
    release = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    old = ReleaseSnapshot(id=uuid.uuid4(), release_id=release.id, snapshot_no="SNAP-007", snapshot_number=1)
    new = ReleaseSnapshot(id=uuid.uuid4(), release_id=release.id, snapshot_no="SNAP-008", snapshot_number=2)
    test_release = RecordedTestRelease(id=uuid.uuid4(), test_release_no="TR-0061", release_id=release.id,
        snapshot_id=new.id, purpose_scope="SOFTWARE_TEST")
    time = datetime(2026, 9, 29, tzinfo=timezone.utc)
    first = DvpExecution(id=uuid.uuid4(), dvp_item_id=item.id, execution_no=1, release_id=release.id,
        snapshot_id=old.id, result="FAIL", actual_result="Timeout", executed_at=time)
    second = DvpExecution(id=uuid.uuid4(), dvp_item_id=item.id, execution_no=2, release_id=release.id,
        snapshot_id=new.id, test_release_id=test_release.id, result="PASS", actual_result="Retest passed", executed_at=time)
    db = Session([item], [first, second], [change, plan, item, release, old, new, test_release])

    detail = dvp_item_detail(item.id, db=db)
    assert detail["plan"]["change_request_no"] == "SCR-142"
    assert [(row["execution_no"], row["result"], row["snapshot_no"], row["test_release_no"])
            for row in detail["executions"]] == [(1, "FAIL", "SNAP-007", None),
                                                 (2, "PASS", "SNAP-008", "TR-0061")]
    assert detail["executions"][1]["release_type"] == "APPLICATION"
    assert list_dvp(db=db)[0]["snapshot_id"] == str(new.id)


def test_dvp_without_execution_has_no_snapshot_and_missing_item_returns_404():
    item = DvpItem(id=uuid.uuid4(), plan_id=uuid.uuid4(), item_no="DVP-034", title="Endurance",
        scope="BATTERY_TEST", status="NOT_STARTED")
    db = Session([item], objects=[item])
    assert list_dvp(db=db)[0]["snapshot_id"] is None
    assert dvp_item_detail(item.id, db=db)["executions"] == []
    with pytest.raises(HTTPException) as error:
        dvp_item_detail(uuid.uuid4(), db=db)
    assert error.value.status_code == 404
