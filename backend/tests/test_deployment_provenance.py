import uuid

import pytest
from fastapi import HTTPException

from app.api.production import get_deployment_provenance
from app.models.approval import ApprovalRequest, ReleaseDecision
from app.models.distribution import DeliveryPackage, Distribution, SoftwareAuthorization
from app.models.production import Deployment


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class Session:
    def __init__(self, deployment=None, decisions=(), objects=()):
        self.deployment = deployment
        self.decisions = decisions
        self.objects = {(type(obj), obj.id): obj for obj in objects}

    def scalars(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is Deployment:
            return Rows([self.deployment] if self.deployment else [])
        if entity is ReleaseDecision:
            return Rows(self.decisions)
        raise AssertionError(entity)

    def get(self, model, identifier):
        return self.objects.get((model, identifier))


def test_provenance_uses_stored_links_and_keeps_multiple_decisions():
    release_id, snapshot_id = uuid.uuid4(), uuid.uuid4()
    package = DeliveryPackage(id=uuid.uuid4(), package_no="DP-0226", revision=2,
        release_id=release_id, snapshot_id=snapshot_id, recipient_type="CUSTOMER", recipient_code="A",
        purpose="PRODUCTION", status="DISTRIBUTED")
    distribution = Distribution(id=uuid.uuid4(), distribution_no="DIST-0326",
        delivery_package_id=package.id, recipient_type="CUSTOMER", recipient_code="A", status="ACKNOWLEDGED")
    authorization = SoftwareAuthorization(id=uuid.uuid4(), authorization_no="PA-0081",
        distribution_id=distribution.id, release_id=release_id, snapshot_id=snapshot_id,
        customer_id=uuid.uuid4(), project_id=uuid.uuid4(), site_code="S", line_code="L", status="APPROVED")
    deployment = Deployment(id=uuid.uuid4(), deployment_no="DEP-0081", authorization_id=authorization.id,
        production_line_id=uuid.uuid4(), expected_release_id=release_id, expected_snapshot_id=snapshot_id)
    first = ApprovalRequest(id=uuid.uuid4(), approval_no="APR-1", target_type="RELEASE", target_id=release_id)
    second = ApprovalRequest(id=uuid.uuid4(), approval_no="APR-2", target_type="RELEASE", target_id=release_id)
    decisions = [ReleaseDecision(id=uuid.uuid4(), decision_no=no, release_id=release_id,
        snapshot_id=snapshot_id, approval_request_id=approval.id, readiness_status="READY",
        decision="RELEASE", decided_by="Manager") for no, approval in (("RD-1", first), ("RD-2", second))]
    result = get_deployment_provenance(deployment.deployment_no,
        db=Session(deployment, decisions, [package, distribution, authorization, first, second]))
    assert result["delivery"]["revision"] == 2
    assert result["distribution"]["distribution_no"] == "DIST-0326"
    assert [row["approval_no"] for row in result["release_decisions"]] == ["APR-1", "APR-2"]


def test_provenance_missing_links_are_explicit_and_unknown_deployment_404():
    deployment = Deployment(id=uuid.uuid4(), deployment_no="DEP-1", authorization_id=uuid.uuid4(),
        production_line_id=uuid.uuid4(), expected_release_id=uuid.uuid4(), expected_snapshot_id=uuid.uuid4())
    result = get_deployment_provenance("DEP-1", db=Session(deployment))
    assert result == {"authorization": None, "distribution": None, "delivery": None, "release_decisions": []}
    with pytest.raises(HTTPException) as error:
        get_deployment_provenance("missing", db=Session())
    assert error.value.status_code == 404
