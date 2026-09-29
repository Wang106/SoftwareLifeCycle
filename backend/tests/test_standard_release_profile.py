import uuid

import pytest
from fastapi import HTTPException

from app.api.dashboard import list_standard_releases, standard_release_profile
from app.models.core import (ApplicationReleaseDetail, ComponentDefinition, Release,
                             ReleaseComponent, SoftwareProduct, StandardReleaseDetail, Supplier)


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class Session:
    def __init__(self, records, collections):
        self.records = records
        self.collections = collections

    def get(self, model, identifier):
        return self.records.get((model, identifier))

    def scalars(self, statement):
        model = statement.column_descriptions[0]["entity"]
        return Rows(self.collections.get(model, []))


def test_standard_catalog_includes_software_and_supplier():
    supplier = Supplier(id=uuid.uuid4(), code="SUP-A", name="Supplier A")
    product = SoftwareProduct(id=uuid.uuid4(), supplier_id=supplier.id, code="BMS", name="Battery Management")
    release = Release(id=uuid.uuid4(), software_id=product.id, release_type="STANDARD", version="5.1.12", status="RELEASED")
    db = Session({}, {Release: [release], SoftwareProduct: [product], Supplier: [supplier]})
    assert list_standard_releases(db=db) == [{"id": str(release.id), "version": "5.1.12",
        "status": "RELEASED", "software": {"code": "BMS", "name": "Battery Management"},
        "supplier": {"code": "SUP-A", "name": "Supplier A"}}]
    assert list_standard_releases(db=Session({}, {})) == []


def test_standard_profile_traces_components_and_exact_application_releases():
    supplier = Supplier(id=uuid.uuid4(), code="SUP-A", name="Supplier A")
    product = SoftwareProduct(id=uuid.uuid4(), supplier_id=supplier.id, code="BMS", name="Battery Management")
    previous = Release(id=uuid.uuid4(), software_id=product.id, release_type="STANDARD", version="5.1.11")
    release = Release(id=uuid.uuid4(), software_id=product.id, release_type="STANDARD", version="5.1.12", status="RELEASED")
    detail = StandardReleaseDetail(release_id=release.id, previous_release_id=previous.id, git_branch="main", git_commit="abc123")
    definition = ComponentDefinition(id=uuid.uuid4(), code="MCU", name="Controller")
    component = ReleaseComponent(id=uuid.uuid4(), release_id=release.id, component_definition_id=definition.id, version="2.0")
    application = Release(id=uuid.uuid4(), software_id=product.id, release_type="APPLICATION", version="2.3.4", status="READY")
    application_detail = ApplicationReleaseDetail(release_id=application.id, customer_id=uuid.uuid4(),
        project_id=uuid.uuid4(), standard_base_release_id=release.id)
    records = {(Release, row.id): row for row in (previous, release)}
    records.update({(StandardReleaseDetail, release.id): detail, (SoftwareProduct, product.id): product,
                    (Supplier, supplier.id): supplier})
    db = Session(records, {ReleaseComponent: [component], ComponentDefinition: [definition],
                           ApplicationReleaseDetail: [application_detail], Release: [application]})
    result = standard_release_profile(release.id, db=db)
    assert result["previous_release"] == {"id": str(previous.id), "version": "5.1.11"}
    assert result["components"] == [{"id": str(component.id), "code": "MCU", "name": "Controller", "version": "2.0"}]
    assert result["applications"] == [{"id": str(application.id), "version": "2.3.4", "status": "READY"}]
    assert result["source"] == {"branch": "main", "commit": "abc123"}


def test_standard_profile_rejects_application_and_missing_release():
    application = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    db = Session({(Release, application.id): application}, {})
    for release_id in (application.id, uuid.uuid4()):
        with pytest.raises(HTTPException) as error:
            standard_release_profile(release_id, db=db)
        assert error.value.status_code == 404
