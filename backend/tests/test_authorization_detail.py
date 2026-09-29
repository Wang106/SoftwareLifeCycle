import uuid

import pytest
from fastapi import HTTPException

from app.api.distribution import get_authorization
from app.models.core import Customer, Project, Release
from app.models.distribution import DeliveryPackage, Distribution, SoftwareAuthorization
from app.models.production import Deployment, ProductionBatch
from app.models.snapshot import ReleaseSnapshot


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class Session:
    def __init__(self, authorization=None, deployments=(), batches=(), objects=()):
        self.authorization = authorization
        self.deployments = deployments
        self.batches = batches
        self.objects = {(type(obj), obj.id): obj for obj in objects}

    def scalars(self, statement):
        model = statement.column_descriptions[0]["entity"]
        if model is SoftwareAuthorization:
            return Rows([self.authorization] if self.authorization else [])
        if model is Deployment:
            return Rows(self.deployments)
        if model is ProductionBatch:
            return Rows(self.batches)
        raise AssertionError(model)

    def get(self, model, identifier):
        return self.objects.get((model, identifier))


def test_authorization_detail_tracks_exact_package_and_actual_production():
    release = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    snapshot = ReleaseSnapshot(id=uuid.uuid4(), release_id=release.id, snapshot_no="SNAP-008", snapshot_number=2)
    customer = Customer(id=uuid.uuid4(), code="CUS-001", name="Customer A")
    project = Project(id=uuid.uuid4(), customer_id=customer.id, project_code="PRJ-X", name="Project X")
    package = DeliveryPackage(id=uuid.uuid4(), package_no="DP-0226", revision=2,
        release_id=release.id, snapshot_id=snapshot.id, recipient_type="CUSTOMER", recipient_code=customer.code,
        purpose="PRODUCTION")
    distribution = Distribution(id=uuid.uuid4(), distribution_no="DIST-0326", delivery_package_id=package.id,
        recipient_type="CUSTOMER", recipient_code=customer.code, status="ACKNOWLEDGED")
    authorization = SoftwareAuthorization(id=uuid.uuid4(), authorization_no="PA-0081", distribution_id=distribution.id,
        release_id=release.id, snapshot_id=snapshot.id, customer_id=customer.id, project_id=project.id,
        site_code="FACTORY-A", line_code="LINE-2", status="APPROVED", batch_limit=1)
    deployment = Deployment(id=uuid.uuid4(), deployment_no="DEP-0081", authorization_id=authorization.id,
        production_line_id=uuid.uuid4(), expected_release_id=release.id, expected_snapshot_id=snapshot.id,
        actual_release_id=release.id, actual_snapshot_id=uuid.uuid4(), status="MISMATCH")
    batch = ProductionBatch(id=uuid.uuid4(), batch_no="PB-1005-A", deployment_id=deployment.id,
        authorization_id=authorization.id, release_id=release.id, snapshot_id=snapshot.id, status="ACTIVE")

    detail = get_authorization("PA-0081", db=Session(authorization, [deployment], [batch],
        [release, snapshot, customer, project, package, distribution]))
    assert detail["distribution"]["package_revision"] == 2
    assert detail["deployments"] == [{"deployment_no": "DEP-0081", "status": "MISMATCH",
        "actual_release_matches": True, "actual_snapshot_matches": False}]
    assert detail["batches"] == [{"batch_no": "PB-1005-A", "status": "ACTIVE"}]


def test_authorization_detail_missing_record_returns_404():
    with pytest.raises(HTTPException) as error:
        get_authorization("PA-MISSING", db=Session())
    assert error.value.status_code == 404
