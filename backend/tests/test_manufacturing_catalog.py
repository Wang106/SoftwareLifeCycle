import uuid

from app.api.production import list_sites
from app.models.core import Customer, Project
from app.models.production import Deployment, ManufacturingSite, ProductionLine


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class CatalogSession:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        return Rows(self.rows.get(entity, []))


def test_manufacturing_catalog_returns_recorded_control_summary():
    customer = Customer(id=uuid.uuid4(), code="CUS-001", name="Customer A")
    project = Project(id=uuid.uuid4(), customer_id=customer.id, project_code="PRJ-X", name="Project X")
    site = ManufacturingSite(id=uuid.uuid4(), site_code="FACTORY-A", customer_id=customer.id,
        project_id=project.id, name="Factory A", region="APAC", status="ACTIVE")
    matching_line = ProductionLine(id=uuid.uuid4(), site_id=site.id, line_code="LINE-1", name="Line 1", status="ACTIVE")
    pending_line = ProductionLine(id=uuid.uuid4(), site_id=site.id, line_code="LINE-2", name="Line 2", status="ACTIVE")
    idle_line = ProductionLine(id=uuid.uuid4(), site_id=site.id, line_code="LINE-3", name="Line 3", status="ACTIVE")
    match = Deployment(id=uuid.uuid4(), deployment_no="DEP-001", authorization_id=uuid.uuid4(),
        production_line_id=matching_line.id, expected_release_id=uuid.uuid4(), expected_snapshot_id=uuid.uuid4(), status="MATCH")
    pending = Deployment(id=uuid.uuid4(), deployment_no="DEP-002", authorization_id=uuid.uuid4(),
        production_line_id=pending_line.id, expected_release_id=uuid.uuid4(), expected_snapshot_id=uuid.uuid4(), status="PENDING")
    older_mismatch = Deployment(id=uuid.uuid4(), deployment_no="DEP-000", authorization_id=uuid.uuid4(),
        production_line_id=matching_line.id, expected_release_id=uuid.uuid4(), expected_snapshot_id=uuid.uuid4(), status="MISMATCH")
    db = CatalogSession({ManufacturingSite: [site], ProductionLine: [matching_line, pending_line, idle_line],
        Deployment: [match, older_mismatch, pending], Customer: [customer], Project: [project]})

    result = list_sites(db=db)

    assert result == [{
        "id": str(site.id), "site_code": "FACTORY-A", "name": "Factory A", "region": "APAC", "status": "ACTIVE",
        "customer": {"code": "CUS-001", "name": "Customer A"},
        "project": {"code": "PRJ-X", "name": "Project X"},
        "line_count": 3, "deployed_line_count": 2, "matching_line_count": 1, "attention_line_count": 1,
    }]


def test_manufacturing_catalog_empty_state_is_not_fabricated():
    assert list_sites(db=CatalogSession({ManufacturingSite: []})) == []
