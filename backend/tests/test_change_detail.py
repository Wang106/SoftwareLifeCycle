import uuid

import pytest
from fastapi import HTTPException

from app.api.dashboard import change_detail
from app.models.change import AcceptanceCriterion, ChangePoint, Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.core import Customer, Project, SoftwareProduct
from app.models.testing import ChangePointDvpItem, DvpItem, DvpPlan


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class Session:
    def __init__(self, change=None, objects=(), criteria=(), points=(), issues=(), plans=(), items=(), links=()):
        self.change = change
        self.objects = {(type(obj), obj.id): obj for obj in objects}
        self.data = {AcceptanceCriterion: criteria, ChangePoint: points, DvpPlan: plans,
                     DvpItem: items, ChangePointDvpItem: links}
        self.issues = issues

    def scalars(self, statement):
        model = statement.column_descriptions[0]["entity"]
        if model is SoftwareChangeRequest:
            return Rows([self.change] if self.change else [])
        return Rows(self.data[model])

    def execute(self, statement):
        return Rows(self.issues)

    def get(self, model, identifier):
        return self.objects.get((model, identifier))


def test_change_detail_uses_exact_linked_issue_plan_and_dvp_item():
    software = SoftwareProduct(id=uuid.uuid4(), supplier_id=uuid.uuid4(), code="SW-BMS-001", name="BMS")
    customer = Customer(id=uuid.uuid4(), code="CUS-001", name="Customer A")
    project = Project(id=uuid.uuid4(), customer_id=customer.id, project_code="PRJ-X", name="Project X")
    change = SoftwareChangeRequest(id=uuid.uuid4(), request_no="SCR-142", title="Charging correction",
        source="ISSUE", scope="STANDARD", change_type="BUG_FIX", software_id=software.id,
        customer_id=customer.id, project_id=project.id, status="IN_TEST", requirement="Fix timeout")
    criterion = AcceptanceCriterion(id=uuid.uuid4(), change_request_id=change.id,
        criterion_no="AC-001", description="Retest passes")
    point = ChangePoint(id=uuid.uuid4(), change_request_id=change.id, change_no="CP-001",
        title="Timeout logic", status="VERIFIED")
    issue = Issue(id=uuid.uuid4(), issue_no="310", title="Timeout", scope="STANDARD", severity="HIGH", status="OPEN")
    issue_link = IssueChangeRequestRelation(id=uuid.uuid4(), issue_id=issue.id,
        change_request_id=change.id, relation_type="FIXED_BY")
    plan = DvpPlan(id=uuid.uuid4(), change_request_id=change.id, plan_no="DVP-PLAN-142", title="Verification")
    item = DvpItem(id=uuid.uuid4(), plan_id=plan.id, item_no="DVP-032", title="Charging test", scope="SOFTWARE_TEST")
    point_link = ChangePointDvpItem(change_point_id=point.id, dvp_item_id=item.id)
    db = Session(change, [software, customer, project], [criterion], [point], [(issue_link, issue)],
                 [plan], [item], [point_link])

    detail = change_detail("SCR-142", db=db)
    assert detail["software"]["code"] == "SW-BMS-001"
    assert detail["customer"]["name"] == "Customer A"
    assert detail["project"]["code"] == "PRJ-X"
    assert detail["acceptance_criteria"][0]["criterion_no"] == "AC-001"
    assert detail["issues"] == [{"issue_no": "310", "title": "Timeout",
                                 "relation_type": "FIXED_BY", "status": "OPEN"}]
    assert detail["change_points"][0]["dvp_items"] == [{"id": str(item.id), "item_no": "DVP-032"}]
    assert detail["dvp_plans"][0]["items"][0]["id"] == str(item.id)


def test_change_detail_missing_record_returns_404():
    with pytest.raises(HTTPException) as error:
        change_detail("SCR-MISSING", db=Session())
    assert error.value.status_code == 404
