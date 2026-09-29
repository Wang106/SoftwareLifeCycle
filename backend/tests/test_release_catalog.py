import uuid

from app.api.dashboard import list_application_releases
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release
from app.models.snapshot import ReleaseSnapshot


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class CatalogSession:
    def __init__(self, releases, details=(), customers=(), projects=(), bases=(), snapshots=()):
        self.releases = releases
        self.details = details
        self.customers = customers
        self.projects = projects
        self.bases = bases
        self.snapshots = snapshots
        self.release_queries = 0

    def scalars(self, statement):
        model = statement.column_descriptions[0]["entity"]
        if model is Release:
            self.release_queries += 1
            return Rows(self.releases if self.release_queries == 1 else self.bases)
        return Rows({ApplicationReleaseDetail: self.details, Customer: self.customers,
                     Project: self.projects, ReleaseSnapshot: self.snapshots}[model])


def test_release_catalog_returns_latest_snapshot_and_organization():
    customer = Customer(id=uuid.uuid4(), code="CUS-001", name="Customer A")
    project = Project(id=uuid.uuid4(), customer_id=customer.id, project_code="PRJ-X", name="Project X")
    base = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="STANDARD", version="5.1.12", status="RELEASED")
    release = Release(id=uuid.uuid4(), software_id=base.software_id, release_type="APPLICATION", version="2.3.4", status="READY")
    detail = ApplicationReleaseDetail(release_id=release.id, customer_id=customer.id, project_id=project.id, standard_base_release_id=base.id)
    old = ReleaseSnapshot(id=uuid.uuid4(), release_id=release.id, snapshot_no="SNAP-007", snapshot_number=1, content_hash="a" * 64)
    current = ReleaseSnapshot(id=uuid.uuid4(), release_id=release.id, snapshot_no="SNAP-008", snapshot_number=2, content_hash="b" * 64)
    db = CatalogSession([release], [detail], [customer], [project], [base], [current, old])
    assert list_application_releases(db=db) == [{
        "id": str(release.id), "version": "2.3.4", "status": "READY",
        "customer": "Customer A", "project": "Project X", "base_id": str(base.id),
        "base_version": "5.1.12", "snapshot_no": "SNAP-008",
    }]
    assert db.release_queries == 2


def test_release_catalog_empty_database():
    assert list_application_releases(db=CatalogSession([])) == []
