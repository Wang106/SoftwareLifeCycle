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
