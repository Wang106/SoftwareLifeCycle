import uuid

import pytest
from sqlalchemy import select

from test_impact_assessments import context
from app.models.approval import ApprovalRequest, ReleaseDecision
from app.models.audit import AuditEvent
from app.models.distribution import DeliveryPackage, DeliveryPackageItem, Distribution
from app.models.revocation import ReleaseChainRevocation
from app.services.distribution import DistributionError, DistributionService
from app.services.revocation import RevocationError, RevocationService, governance_state

from pydantic import ValidationError
from app.actor import ActorContext
from app.api.revocations import RevocationCreate
from app.models.distribution import SoftwareAuthorization
from app.models.core import Customer, Project
from app.services.audit import AuditEventService


def reviewed(db, kind, target):
    observation = governance_state(db, kind, target, include_review=True)
    assert observation["target_kind"] == kind and observation["target_id"] == str(target)
    assert observation["review_context"] is not None
    return observation["review_context"]


def full_targets(db, release, package):
    distribution = Distribution(distribution_no="DIST-REVIEW", delivery_package_id=package.id,
        recipient_type="CUSTOMER", recipient_code="C")
    customer = Customer(code="REVIEW", name="Review customer")
    db.add_all([distribution, customer]); db.flush()
    project = Project(customer_id=customer.id, project_code="REVIEW", name="Review project")
    db.add(project); db.flush()
    authorization = SoftwareAuthorization(authorization_no="PA-REVIEW", release_id=release.id,
        snapshot_id=package.snapshot_id, distribution_id=distribution.id,
        customer_id=customer.id, project_id=project.id, site_code="SITE", line_code="LINE")
    db.add(authorization); db.commit()
    return dict(RELEASE=release.id, DELIVERY_PACKAGE=package.id,
                DISTRIBUTION=distribution.id, AUTHORIZATION=authorization.id)


@pytest.mark.parametrize("kind", ["RELEASE", "DELIVERY_PACKAGE", "DISTRIBUTION", "AUTHORIZATION"])
def test_reviewed_four_kinds_bind_original_audit_and_exact_actor(release_chain, kind):
    db, release, package = release_chain
    target = full_targets(db, release, package)[kind]
    expected = reviewed(db, kind, target)
    actor = ActorContext("Engineer", uuid.uuid4(), "Engineer", None, "AUTHENTICATED_PRINCIPAL")
    key = uuid.uuid4()
    row = RevocationService(db).revoke(kind, target, "  已审核原因  ", actor, key, expected)
    event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == f"EVT-RCR-{key.hex}"))
    assert event.actor_principal_id == actor.principal_id and event.declared_actor_name is None
    assert event.entity_id == target and event.entity_type == kind
    assert event.action == kind.replace("DELIVERY_PACKAGE", "DELIVERY") + "_REVOKED"
    assert event.payload_json["protocol_version"] == 1
    assert event.payload_json["review_context"] == expected
    assert event.payload_json["request"] == dict(target_kind=kind, target_id=str(target),
        reason="已审核原因", expected_context=expected)
    assert event.detail == event.payload_json["reason"] == row.reason == "已审核原因"
    assert str(row.snapshot_id) == expected["snapshot_id"]
    assert str(row.release_decision_id) == expected["release_decision_id"]
    assert RevocationService(db).revoke(kind, target, "已审核原因", actor, key, expected).id == key
    assert governance_state(db, kind, target, include_review=True)["review_context"] is None
    changed_actor = ActorContext("Engineer", uuid.uuid4(), "Engineer", None, "AUTHENTICATED_PRINCIPAL")
    with pytest.raises(RevocationError, match="request_id"):
        RevocationService(db).revoke(kind, target, "已审核原因", changed_actor, key, expected)


@pytest.mark.parametrize("field", ["release_id", "snapshot_id", "release_decision_id",
                                  "delivery_package_id", "distribution_id", "authorization_id"])
def test_reviewed_context_mismatch_rolls_back_without_history(release_chain, field):
    db, release, package = release_chain
    expected = reviewed(db, "DELIVERY_PACKAGE", package.id)
    expected[field] = str(uuid.uuid4())
    with pytest.raises(RevocationError, match="context"):
        RevocationService(db).revoke("DELIVERY_PACKAGE", package.id, "Reviewed", request_id=uuid.uuid4(),
                                     expected_context=expected)
    assert not db.in_transaction()
    assert db.scalars(select(ReleaseChainRevocation)).all() == []
    assert db.scalars(select(AuditEvent)).all() == []


@pytest.mark.parametrize("case", ["extra", "null", "context_extra", "missing", "uppercase", "version_bool"])
def test_reviewed_http_body_rejects_ambiguous_context(release_chain, case):
    db, release, _ = release_chain
    body = dict(request_id=str(uuid.uuid4()), reason="Reviewed",
                expected_context=reviewed(db, "RELEASE", release.id))
    if case == "extra": body["actor_name"] = "Untrusted"
    elif case == "null": body["expected_context"] = None
    elif case == "context_extra": body["expected_context"]["role"] = "ADMIN"
    elif case == "missing": del body["expected_context"]["distribution_id"]
    elif case == "uppercase": body["expected_context"]["release_id"] = str(release.id).upper()
    else: body["expected_context"]["version"] = True
    with pytest.raises(ValidationError): RevocationCreate.model_validate(body)


def test_original_legacy_and_reviewed_replays_survive_later_ancestor_revocation(release_chain):
    db, release, package = release_chain
    targets = full_targets(db, release, package)
    expected = reviewed(db, "AUTHORIZATION", targets["AUTHORIZATION"])
    key = uuid.uuid4(); legacy = uuid.uuid4()
    RevocationService(db).revoke("AUTHORIZATION", targets["AUTHORIZATION"], "Reviewed", request_id=key,
                                 expected_context=expected)
    RevocationService(db).revoke("DELIVERY_PACKAGE", package.id, "Legacy", request_id=legacy)
    RevocationService(db).revoke("RELEASE", release.id, "Ancestor", request_id=uuid.uuid4())
    assert RevocationService(db).revoke("AUTHORIZATION", targets["AUTHORIZATION"], "Reviewed",
        request_id=key, expected_context=expected).id == key
    assert RevocationService(db).revoke("DELIVERY_PACKAGE", package.id, "Legacy", request_id=legacy).id == legacy
    old = db.scalar(select(AuditEvent).where(AuditEvent.event_no == f"EVT-RCR-{legacy.hex}"))
    assert set(old.payload_json["request"]) == {"target_kind", "target_id", "reason"}
    assert "protocol_version" not in old.payload_json
    with pytest.raises(RevocationError, match="request_id"):
        RevocationService(db).revoke("AUTHORIZATION", targets["AUTHORIZATION"], "Reviewed", request_id=key)


def test_reviewed_audit_failure_rolls_back_both_records(release_chain, monkeypatch):
    db, release, _ = release_chain
    expected = reviewed(db, "RELEASE", release.id)
    original = AuditEventService.record
    def fail(service, **values):
        original(service, **values)
        raise RuntimeError("audit failure")
    monkeypatch.setattr(AuditEventService, "record", fail)
    with pytest.raises(RuntimeError, match="audit failure"):
        RevocationService(db).revoke("RELEASE", release.id, "Reviewed", request_id=uuid.uuid4(),
                                     expected_context=expected)
    assert not db.in_transaction()
    assert db.scalars(select(ReleaseChainRevocation)).all() == []
    assert db.scalars(select(AuditEvent)).all() == []


@pytest.mark.parametrize("kind,role", [("RELEASE", "DISTRIBUTION_AUTHORITY"),
    ("DELIVERY_PACKAGE", "DISTRIBUTION_AUTHORITY"), ("DISTRIBUTION", "PRODUCTION_AUTHORITY"),
    ("AUTHORIZATION", "PRODUCTION_AUTHORITY")])
@pytest.mark.parametrize("allowed", [False, True])
def test_versioned_routes_retain_exact_project_authorization(release_chain, monkeypatch, kind, role, allowed):
    from app.api import revocations as api
    from app.core.config import settings
    from app.models.core import ApplicationReleaseDetail
    from app.models.security import ProjectMembership, SecurityPrincipal
    from app.authorization import AuthorizationError
    from test_authorization import authenticated_request
    db, release, package = release_chain
    targets = full_targets(db, release, package)
    authorization = db.get(SoftwareAuthorization, targets["AUTHORIZATION"])
    db.add(ApplicationReleaseDetail(release_id=release.id, customer_id=authorization.customer_id,
        project_id=authorization.project_id, standard_base_release_id=release.id))
    principal = SecurityPrincipal(issuer="https://identity.example.com", subject="reviewer",
                                  principal_type="USER", display_name="Reviewer")
    db.add(principal); db.flush()
    db.add(ProjectMembership(principal_id=principal.id, project_id=authorization.project_id,
                              role=role if allowed else "REVIEWER", status="ACTIVE")); db.commit()
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    request = authenticated_request(principal)
    body = RevocationCreate(request_id=uuid.uuid4(), reason="Reviewed",
        expected_context=reviewed(db, kind, targets[kind]))
    endpoint = dict(RELEASE=api.revoke_release, DELIVERY_PACKAGE=api.revoke_delivery,
                    DISTRIBUTION=api.revoke_distribution, AUTHORIZATION=api.revoke_authorization)[kind]
    if allowed:
        assert endpoint(targets[kind], body, db, request)["id"] == str(body.request_id)
    else:
        with pytest.raises(AuthorizationError): endpoint(targets[kind], body, db, request)
        assert db.scalars(select(ReleaseChainRevocation)).all() == []


def test_readonly_http_rejects_even_valid_versioned_request(release_chain, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.config import settings
    db, release, _ = release_chain
    body = dict(request_id=str(uuid.uuid4()), reason="Reviewed",
                expected_context=reviewed(db, "RELEASE", release.id))
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "read_only_mode", True)
    response = TestClient(app).post(f"/api/v1/releases/{release.id}/revocations", json=body)
    assert response.status_code == 403 and response.json()["detail"] == "read_only_mode"
    assert db.scalars(select(ReleaseChainRevocation)).all() == []


def test_review_observation_is_bounded_with_long_unrelated_decision_history(release_chain):
    from datetime import datetime, timezone
    from sqlalchemy import event
    db, release, package = release_chain
    before = reviewed(db, "DELIVERY_PACKAGE", package.id)
    approval = db.scalar(select(ApprovalRequest))
    db.add_all([ReleaseDecision(decision_no=f"RD-OLD-{i}", release_id=release.id,
        snapshot_id=package.snapshot_id, approval_request_id=approval.id,
        readiness_status="READY", decision="HOLD", decided_by="Historical",
        decided_at=datetime(2000, 1, 1, tzinfo=timezone.utc)) for i in range(205)])
    db.commit(); db.expire_all()
    statements = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        assert reviewed(db, "DELIVERY_PACKAGE", package.id) == before
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    decisions = [sql for sql in statements if "from release_decisions" in sql]
    assert len(decisions) == 1 and "limit" in decisions[0]
    assert len(statements) <= 5
    assert db.scalars(select(AuditEvent)).all() == []


@pytest.fixture
def release_chain(context):
    db, _, release, snapshot, _ = context
    approval = ApprovalRequest(approval_no="APR-RCR", target_type="RELEASE",
        target_id=release.id, snapshot_id=snapshot.id, status="APPROVED")
    db.add(approval); db.flush()
    decision = ReleaseDecision(decision_no="RD-RCR", release_id=release.id,
        snapshot_id=snapshot.id, approval_request_id=approval.id,
        readiness_status="READY", decision="RELEASE", decided_by="Manager")
    package = DeliveryPackage(package_no="DP-RCR", revision=1, release_id=release.id,
        snapshot_id=snapshot.id, recipient_type="CUSTOMER", recipient_code="C",
        purpose="PRODUCTION", status="READY")
    db.add_all([decision, package]); db.flush()
    db.add(DeliveryPackageItem(delivery_package_id=package.id,
        snapshot_artifact_id=uuid.uuid4(), policy_decision="ALLOW"))
    db.commit()
    return db, release, package


def test_release_revocation_is_exactly_replayable_and_blocks_descendants(release_chain):
    db, release, package = release_chain
    key = uuid.uuid4()
    first = RevocationService(db).revoke("RELEASE", release.id, "Safety issue", request_id=key)
    retry = RevocationService(db).revoke("RELEASE", release.id, "Safety issue", request_id=key)
    assert first.id == retry.id == key
    assert governance_state(db, "RELEASE", release.id)["governance_state"] == "REVOKED"
    downstream = governance_state(db, "DELIVERY_PACKAGE", package.id)
    assert downstream["governance_state"] == "BLOCKED_BY_ANCESTOR"
    assert not downstream["eligible_for_new_work"]
    assert len(db.scalars(select(ReleaseChainRevocation)).all()) == 1
    assert len(db.scalars(select(AuditEvent).where(
        AuditEvent.event_type == "RELEASE_CHAIN_REVOCATION")).all()) == 1
    with pytest.raises(DistributionError, match="blocked_by_ancestor"):
        DistributionService(db).create_distribution(
            package.id, "DIST-RCR", "CUSTOMER", "C", request_id=uuid.uuid4())


def test_revocation_rejects_changed_retry_and_second_target_event(release_chain):
    db, release, _ = release_chain
    key = uuid.uuid4()
    RevocationService(db).revoke("RELEASE", release.id, "Safety issue", request_id=key)
    with pytest.raises(RevocationError, match="request_id"):
        RevocationService(db).revoke("RELEASE", release.id, "Changed reason", request_id=key)
    with pytest.raises(RevocationError, match="already revoked"):
        RevocationService(db).revoke("RELEASE", release.id, "Second event", request_id=uuid.uuid4())
