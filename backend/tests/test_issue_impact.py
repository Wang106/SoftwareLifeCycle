import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.api.impact import issue_impact
from app.models.change import Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release, SoftwareProduct
from app.models.production import Deployment, ProductionBatch


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class ImpactSession:
    def __init__(self, data, linked=()):
        self.data = data
        self.linked = linked
        self.statements = []

    def scalars(self, statement):
        self.statements.append(statement)
        return Rows(self.data.get(statement.column_descriptions[0]["entity"], []))

    def execute(self, statement):
        self.statements.append(statement)
        return Rows(self.linked)


def test_issue_impact_marks_same_software_releases_as_candidates():
    issue = Issue(id=uuid.uuid4(), issue_no="310", title="Charging timeout", scope="STANDARD", severity="HIGH")
    product = SoftwareProduct(id=uuid.uuid4(), supplier_id=uuid.uuid4(), code="BMS", name="BMS")
    customer = Customer(id=uuid.uuid4(), code="CUS-001", name="Customer A")
    project = Project(id=uuid.uuid4(), customer_id=customer.id, project_code="PRJ-X", name="Project X")
    scr = SoftwareChangeRequest(id=uuid.uuid4(), request_no="SCR-142", title="Fix timeout", software_id=product.id, source="ISSUE", scope="STANDARD", change_type="BUG_FIX", status="IN_TEST")
    relation = IssueChangeRequestRelation(issue_id=issue.id, change_request_id=scr.id, relation_type="FIXED_BY")
    release = Release(id=uuid.uuid4(), software_id=product.id, release_type="APPLICATION", version="2.3.4", status="READY")
    detail = ApplicationReleaseDetail(release_id=release.id, customer_id=customer.id, project_id=project.id, standard_base_release_id=uuid.uuid4())
    deployment = Deployment(id=uuid.uuid4(), deployment_no="DEP-0081", actual_release_id=release.id)
    batch = ProductionBatch(id=uuid.uuid4(), batch_no="PB-1005-A", release_id=release.id)
    db = ImpactSession({Issue: [issue], SoftwareProduct: [product], Release: [release],
                        ApplicationReleaseDetail: [detail], Customer: [customer], Project: [project],
                        Deployment: [deployment], ProductionBatch: [batch]}, [(relation, scr)])
    result = issue_impact("310", db=db)
    assert result["linked_changes"][0]["request_no"] == "SCR-142"
    candidate = result["candidate_releases"][0]
    assert candidate["id"] == str(release.id)
    assert candidate["customer"] == "Customer A"
    assert candidate["deployment_count"] == 1
    assert candidate["batch_count"] == 1
    assert "requires review" in result["basis"]
    deployment_query = next(s for s in db.statements if s.column_descriptions[0]["entity"] is Deployment)
    assert "actual_release_id" in str(deployment_query.compile(dialect=postgresql.dialect()))


def test_unlinked_issue_has_no_inferred_releases():
    issue = Issue(id=uuid.uuid4(), issue_no="402", title="Unknown impact", scope="DEPLOYMENT", severity="HIGH")
    result = issue_impact("402", db=ImpactSession({Issue: [issue]}))
    assert result["candidate_releases"] == []
    assert result["linked_changes"] == []


def test_missing_issue_returns_404():
    with pytest.raises(HTTPException) as error:
        issue_impact("missing", db=ImpactSession({Issue: []}))
    assert error.value.status_code == 404
