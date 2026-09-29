import uuid

import pytest
from fastapi import HTTPException

from app.api.distribution import get_distribution
from app.models.core import Release
from app.models.distribution import DeliveryPackage, Distribution, SoftwareAuthorization
from app.models.snapshot import ReleaseSnapshot


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class Session:
    def __init__(self, distribution=None, authorizations=(), objects=()):
        self.distribution = distribution
        self.authorizations = authorizations
        self.objects = {(type(obj), obj.id): obj for obj in objects}

    def scalars(self, statement):
        model = statement.column_descriptions[0]["entity"]
        if model is Distribution:
            return Rows([self.distribution] if self.distribution else [])
        if model is SoftwareAuthorization:
            return Rows(self.authorizations)
        raise AssertionError(model)

    def get(self, model, identifier):
        return self.objects.get((model, identifier))


def test_distribution_detail_resolves_exact_delivery_and_linked_authorizations():
    release = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    snapshot = ReleaseSnapshot(id=uuid.uuid4(), release_id=release.id, snapshot_no="SNAP-008", snapshot_number=2)
    package = DeliveryPackage(id=uuid.uuid4(), package_no="DP-0226", revision=2,
        release_id=release.id, snapshot_id=snapshot.id, recipient_type="CUSTOMER", recipient_code="CUS-001", purpose="PRODUCTION")
    record = Distribution(id=uuid.uuid4(), distribution_no="DIST-0326", delivery_package_id=package.id,
        recipient_type="CUSTOMER", recipient_code="CUS-001", status="ACKNOWLEDGED")
    authorization = SoftwareAuthorization(id=uuid.uuid4(), authorization_no="PA-0081", distribution_id=record.id,
        release_id=release.id, snapshot_id=snapshot.id, customer_id=uuid.uuid4(), project_id=uuid.uuid4(),
        site_code="FACTORY-A", line_code="LINE-2", status="APPROVED")

    result = get_distribution("DIST-0326", db=Session(record, [authorization], [release, snapshot, package]))
    assert result["delivery"] == {"id": str(package.id), "package_no": "DP-0226", "revision": 2, "purpose": "PRODUCTION"}
    assert result["snapshot_no"] == "SNAP-008"
    assert result["authorizations"] == [{"authorization_no": "PA-0081", "status": "APPROVED",
        "site_code": "FACTORY-A", "line_code": "LINE-2"}]


def test_distribution_detail_returns_404_for_unknown_reference():
    with pytest.raises(HTTPException) as error:
        get_distribution("DIST-MISSING", db=Session())
    assert error.value.status_code == 404
