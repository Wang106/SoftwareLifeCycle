import uuid

import pytest
from fastapi import HTTPException

from app.api.production import get_batch, list_batches
from app.models.core import Release
from app.models.distribution import SoftwareAuthorization
from app.models.production import Deployment, ProductionBatch, SoftwareChangeover
from app.models.snapshot import ReleaseSnapshot


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class Session:
    def __init__(self, batches=(), objects=()):
        self.batches = batches
        self.objects = {(type(obj), obj.id): obj for obj in objects}

    def scalars(self, statement):
        assert statement.column_descriptions[0]["entity"] is ProductionBatch
        return Rows(self.batches)

    def get(self, model, identifier):
        return self.objects.get((model, identifier))


def test_batch_detail_compares_recorded_authorization_deployment_and_changeover():
    release = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    snapshot = ReleaseSnapshot(id=uuid.uuid4(), release_id=release.id, snapshot_no="SNAP-008", snapshot_number=2)
    authorization = SoftwareAuthorization(id=uuid.uuid4(), authorization_no="PA-0081",
        distribution_id=uuid.uuid4(), release_id=release.id, snapshot_id=snapshot.id,
        customer_id=uuid.uuid4(), project_id=uuid.uuid4(), site_code="FACTORY-A", line_code="LINE-2",
        status="APPROVED", batch_limit=1)
    deployment = Deployment(id=uuid.uuid4(), deployment_no="DEP-0081", authorization_id=authorization.id,
        production_line_id=uuid.uuid4(), expected_release_id=release.id, expected_snapshot_id=snapshot.id,
        actual_release_id=release.id, actual_snapshot_id=uuid.uuid4(), status="MISMATCH")
    changeover = SoftwareChangeover(id=uuid.uuid4(), changeover_no="CO-0032", deployment_id=deployment.id,
        authorization_id=authorization.id, from_release_id=uuid.uuid4(), to_release_id=release.id,
        status="COMPLETED")
    batch = ProductionBatch(id=uuid.uuid4(), batch_no="PB-1005-A", deployment_id=deployment.id,
        changeover_id=changeover.id, authorization_id=authorization.id, release_id=release.id,
        snapshot_id=snapshot.id, status="ACTIVE")
    db = Session([batch], [release, snapshot, authorization, deployment, changeover])

    assert list_batches(db=db)[0]["batch_no"] == "PB-1005-A"
    detail = get_batch("PB-1005-A", db=db)
    assert detail["software"]["snapshot_no"] == "SNAP-008"
    assert detail["deployment"]["deployment_no"] == "DEP-0081"
    assert detail["authorization"]["batch_limit"] == 1
    assert detail["changeover"]["changeover_no"] == "CO-0032"
    assert detail["matches"] == {
        "authorized_release": True, "authorized_snapshot": True,
        "deployed_release": True, "deployed_snapshot": False, "changeover_deployment": True,
    }


def test_batch_detail_missing_record_returns_404():
    with pytest.raises(HTTPException) as error:
        get_batch("PB-MISSING", db=Session())
    assert error.value.status_code == 404
