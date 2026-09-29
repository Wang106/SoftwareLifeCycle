import uuid

import pytest
from fastapi import HTTPException

from app.api import dashboard
from app.api.dashboard import application_release_profile
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release, SoftwareProduct
from app.models.snapshot import ReleaseSnapshot


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None


class ProfileSession:
    def __init__(self, rows, snapshots=()):
        self.rows = rows
        self.snapshots = snapshots

    def get(self, model, identifier):
        return self.rows.get((model, identifier))

    def scalars(self, statement):
        assert statement.column_descriptions[0]["entity"] is ReleaseSnapshot
        return Rows(self.snapshots)


def test_profile_rejects_standard_and_missing_releases():
    standard = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="STANDARD", version="5.1.12")
    db = ProfileSession({(Release, standard.id): standard})
    for release_id in (standard.id, uuid.uuid4()):
        with pytest.raises(HTTPException) as error:
            application_release_profile(release_id, db=db)
        assert error.value.status_code == 404


def test_profile_without_snapshot_has_no_fabricated_coverage():
    software = SoftwareProduct(id=uuid.uuid4(), supplier_id=uuid.uuid4(), code="BMS", name="BMS")
    customer = Customer(id=uuid.uuid4(), code="CUS-001", name="Customer A")
    project = Project(id=uuid.uuid4(), customer_id=customer.id, project_code="PRJ-X", name="Project X")
    base = Release(id=uuid.uuid4(), software_id=software.id, release_type="STANDARD", version="5.1.12")
    release = Release(id=uuid.uuid4(), software_id=software.id, release_type="APPLICATION", version="2.3.3", status="SUPERSEDED")
    detail = ApplicationReleaseDetail(release_id=release.id, customer_id=customer.id, project_id=project.id, standard_base_release_id=base.id)
    rows = {(Release, release.id): release, (Release, base.id): base,
            (ApplicationReleaseDetail, release.id): detail, (SoftwareProduct, software.id): software,
            (Customer, customer.id): customer, (Project, project.id): project}
    profile = application_release_profile(release.id, db=ProfileSession(rows))
    assert profile["id"] == str(release.id)
    assert profile["customer"]["code"] == "CUS-001"
    assert profile["project"]["id"] == str(project.id)
    assert profile["base_release"]["version"] == "5.1.12"
    assert profile["base_release"]["id"] == str(base.id)
    assert profile["snapshot"] is None
    assert profile["coverage"] is None


def test_profile_uses_latest_snapshot_for_coverage(monkeypatch):
    release = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    snapshot = ReleaseSnapshot(id=uuid.uuid4(), release_id=release.id, snapshot_no="SNAP-008", snapshot_number=2, status="FROZEN", content_hash="a" * 64)

    class Coverage:
        def as_dict(self):
            return {"snapshot_no": "SNAP-008", "dvp_execution_coverage": 67}

    class Trace:
        def __init__(self, db):
            pass

        def release_coverage(self, release_id, snapshot_id):
            assert (release_id, snapshot_id) == (release.id, snapshot.id)
            return Coverage()

    monkeypatch.setattr(dashboard, "TraceabilityService", Trace)
    profile = application_release_profile(release.id, db=ProfileSession({(Release, release.id): release}, [snapshot]))
    assert profile["snapshot"]["content_hash"] == "a" * 64
    assert profile["coverage"]["dvp_execution_coverage"] == 67
