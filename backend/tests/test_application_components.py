import uuid

import pytest
from fastapi import HTTPException

from app.api.dashboard import application_release_components
from app.models.core import ApplicationReleaseDetail, ComponentDefinition, Release, ReleaseComponent


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class Session:
    def __init__(self, releases=(), detail=None, asr_components=(), base_components=(), definitions=()):
        self.objects = {(type(row), row.id): row for row in releases}
        if detail:
            self.objects[(ApplicationReleaseDetail, detail.release_id)] = detail
        self.asr_components = asr_components
        self.base_components = base_components
        self.definitions = definitions
        self.component_queries = 0

    def get(self, model, identifier):
        return self.objects.get((model, identifier))

    def scalars(self, statement):
        model = statement.column_descriptions[0]["entity"]
        if model is ReleaseComponent:
            self.component_queries += 1
            return Rows(self.asr_components if self.component_queries == 1 else self.base_components)
        if model is ComponentDefinition:
            return Rows(self.definitions)
        raise AssertionError(model)


def test_component_detail_resolves_only_matching_stored_base_links():
    base = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="STANDARD", version="5.1.12")
    asr = Release(id=uuid.uuid4(), software_id=base.software_id, release_type="APPLICATION", version="2.3.4")
    another_asr = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    detail = ApplicationReleaseDetail(release_id=asr.id, standard_base_release_id=base.id,
        customer_id=uuid.uuid4(), project_id=uuid.uuid4())
    main = ComponentDefinition(id=uuid.uuid4(), code="MAIN", name="Main Application")
    calibration = ComponentDefinition(id=uuid.uuid4(), code="CAL", name="Calibration")
    base_main = ReleaseComponent(id=uuid.uuid4(), release_id=base.id, component_definition_id=main.id,
        version="5.1.12", delta_type="UNCHANGED")
    base_cal = ReleaseComponent(id=uuid.uuid4(), release_id=base.id, component_definition_id=calibration.id,
        version="CAL-30", delta_type="UNCHANGED")
    linked = ReleaseComponent(id=uuid.uuid4(), release_id=asr.id, component_definition_id=main.id,
        version="2.3.4", base_component_id=base_main.id, delta_type="MODIFIED")
    wrong = ReleaseComponent(id=uuid.uuid4(), release_id=asr.id, component_definition_id=main.id,
        version="2.3.5", base_component_id=base_cal.id, delta_type="MODIFIED")
    db = Session([base, asr, another_asr], detail, [linked, wrong], [base_main, base_cal], [main, calibration])

    result = application_release_components(asr.id, db=db)
    assert result["release_id"] == str(asr.id)
    assert result["base_release"]["version"] == "5.1.12"
    assert result["components"][0]["base_component_version"] == "5.1.12"
    assert result["components"][0]["base_link_status"] == "VALID"
    assert result["components"][1]["base_component_version"] is None
    assert result["components"][1]["base_link_status"] == "INVALID"
    assert result["unlinked_base_components"] == [{"id": str(base_cal.id),
        "code": "CAL", "name": "Calibration", "version": "CAL-30"}]


def test_component_detail_without_base_does_not_infer_versions_and_rejects_standard():
    asr = Release(id=uuid.uuid4(), software_id=uuid.uuid4(), release_type="APPLICATION", version="2.3.4")
    base = Release(id=uuid.uuid4(), software_id=asr.software_id, release_type="STANDARD", version="5.1.12")
    definition = ComponentDefinition(id=uuid.uuid4(), code="MAIN", name="Main Application")
    component = ReleaseComponent(id=uuid.uuid4(), release_id=asr.id,
        component_definition_id=definition.id, version="2.3.4", delta_type="MODIFIED")
    db = Session([asr, base], asr_components=[component], definitions=[definition])
    result = application_release_components(asr.id, db=db)
    assert result["base_release"] is None
    assert result["components"][0]["base_link_status"] == "NOT_RECORDED"
    assert result["components"][0]["base_component_version"] is None
    for release_id in (base.id, uuid.uuid4()):
        with pytest.raises(HTTPException) as error:
            application_release_components(release_id, db=db)
        assert error.value.status_code == 404
