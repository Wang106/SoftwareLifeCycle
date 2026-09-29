import uuid

import pytest
from fastapi import HTTPException

from app.api.organizations import _customers, _projects, _suppliers, get_project
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release, SoftwareProduct, Supplier
from app.models.production import ManufacturingSite


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class CatalogSession:
    def __init__(self, objects):
        self.objects = objects

    def scalars(self, statement):
        model = statement.column_descriptions[0]["entity"]
        return Rows(self.objects.get(model, []))

    def get(self, model, identifier):
        return next((row for row in self.objects.get(model, []) if row.id == identifier), None)


def test_organization_catalog_uses_real_relationships_and_latest_release():
    supplier = Supplier(id=uuid.uuid4(), code="SUP-001", name="Supplier A", status="ACTIVE")
    customer = Customer(id=uuid.uuid4(), code="CUS-001", name="Customer A", status="ACTIVE")
    project = Project(id=uuid.uuid4(), customer_id=customer.id, project_code="PRJ-X", name="Project X", status="ACTIVE")
    product = SoftwareProduct(id=uuid.uuid4(), supplier_id=supplier.id, code="SW-BMS", name="BMS", status="ACTIVE")
    standard = Release(id=uuid.uuid4(), software_id=product.id, release_type="STANDARD", version="5.1.12", status="RELEASED")
    application = Release(id=uuid.uuid4(), software_id=product.id, release_type="APPLICATION", version="2.3.4", status="READY")
    detail = ApplicationReleaseDetail(release_id=application.id, customer_id=customer.id, project_id=project.id, standard_base_release_id=standard.id)
    site = ManufacturingSite(site_code="FACTORY-A", project_id=project.id, customer_id=customer.id, name="Factory A", status="ACTIVE")
    db = CatalogSession({Supplier: [supplier], Customer: [customer], Project: [project], SoftwareProduct: [product], Release: [application], ApplicationReleaseDetail: [detail], ManufacturingSite: [site]})
    supplier_db = CatalogSession({SoftwareProduct: [product], Release: [standard]})

    assert _suppliers(supplier_db, [supplier])[0]["software"][0]["standard_version"] == "5.1.12"
    assert _customers(db, [customer])[0]["projects"][0]["release"] == {
        "id": str(application.id), "version": "2.3.4", "status": "READY",
    }
    profile = _projects(db, [project])[0]
    assert profile["id"] == str(project.id)
    assert profile["customer"]["code"] == "CUS-001"
    assert profile["sites"][0]["code"] == "FACTORY-A"
    assert profile["release"]["id"] == str(application.id)
    assert get_project(str(project.id), db=db)["code"] == "PRJ-X"


def test_duplicate_project_codes_require_uuid():
    first = Project(id=uuid.uuid4(), customer_id=uuid.uuid4(), project_code="PRJ-X", name="First")
    second = Project(id=uuid.uuid4(), customer_id=uuid.uuid4(), project_code="PRJ-X", name="Second")
    db = CatalogSession({Project: [first, second]})
    with pytest.raises(HTTPException) as error:
        get_project("PRJ-X", db=db)
    assert error.value.status_code == 409
