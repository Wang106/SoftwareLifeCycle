import uuid

import pytest
from fastapi import HTTPException

from app.api.dashboard import application_release_downstream
from app.models.core import Release
from app.models.distribution import DeliveryPackage, Distribution, SoftwareAuthorization
from app.models.production import Deployment, ProductionBatch, SoftwareChangeover
from app.models.snapshot import ReleaseSnapshot


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class Session:
    def __init__(self, release, rows=None):
        self.release = release
        self.rows = rows or {}

    def get(self, model, identifier):
        return self.release if model is Release and self.release and identifier == self.release.id else None

    def scalars(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        return Rows(self.rows.get(entity, []))


def test_downstream_keeps_direct_links_and_actual_mismatch_visible():
    release = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    snapshot = ReleaseSnapshot(id=uuid.uuid4(), release_id=release.id, snapshot_no="SNAP-008", snapshot_number=1)
    package = DeliveryPackage(id=uuid.uuid4(), package_no="DP-0226", revision=2, release_id=release.id,
                              snapshot_id=snapshot.id, recipient_type="CUSTOMER", recipient_code="A", purpose="PRODUCTION", status="SEALED")
    distribution = Distribution(id=uuid.uuid4(), distribution_no="DIST-0326", delivery_package_id=package.id,
                                recipient_type="CUSTOMER", recipient_code="A", status="ACKNOWLEDGED")
    authorization = SoftwareAuthorization(id=uuid.uuid4(), authorization_no="PA-0081", release_id=release.id,
        snapshot_id=snapshot.id, distribution_id=distribution.id, customer_id=uuid.uuid4(), project_id=uuid.uuid4(),
        site_code="S1", line_code="L1", status="APPROVED", batch_limit=1)
    deployment = Deployment(id=uuid.uuid4(), deployment_no="DEP-0081", authorization_id=authorization.id,
        production_line_id=uuid.uuid4(), expected_release_id=release.id, expected_snapshot_id=snapshot.id,
        actual_release_id=uuid.uuid4(), actual_snapshot_id=snapshot.id, status="MISMATCH")
    changeover = SoftwareChangeover(id=uuid.uuid4(), changeover_no="CO-0032", deployment_id=deployment.id,
        authorization_id=authorization.id, from_release_id=uuid.uuid4(), to_release_id=release.id, status="PLANNED")
    batch = ProductionBatch(id=uuid.uuid4(), batch_no="PB-1005-A", deployment_id=deployment.id,
        authorization_id=authorization.id, release_id=uuid.uuid4(), snapshot_id=snapshot.id, status="PLANNED")
    db = Session(release, {DeliveryPackage: [package], Distribution: [distribution],
        SoftwareAuthorization: [authorization], Deployment: [deployment], SoftwareChangeover: [changeover],
        ProductionBatch: [batch], ReleaseSnapshot: [snapshot]})
    result = application_release_downstream(release.id, db=db)
    assert result["deliveries"][0]["snapshot_no"] == "SNAP-008"
    assert result["distributions"][0]["package_revision"] == 2
    assert result["authorizations"][0]["distribution_no"] == "DIST-0326"
    assert result["deployments"][0]["actual_release_matches"] is False
    assert result["batches"][0]["release_matches"] is False
    assert result["changeovers"][0]["deployment_no"] == "DEP-0081"


def test_downstream_empty_and_non_application_404():
    release = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="1")
    result = application_release_downstream(release.id, db=Session(release))
    assert all(not rows for rows in result.values())
    standard = Release(id=uuid.uuid4(), software_id=release.software_id, release_type="STANDARD", version="1")
    with pytest.raises(HTTPException) as error:
        application_release_downstream(standard.id, db=Session(standard))
    assert error.value.status_code == 404
