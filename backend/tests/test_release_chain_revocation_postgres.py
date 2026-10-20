"""Migrated PostgreSQL locks, immutability, guards and downgrade safety."""
import uuid

import pytest
from alembic import command as migration
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from test_distribution_concurrency_postgres import chain
from test_command_concurrency_postgres import pg, count, overlapping_commands
from app.models.audit import AuditEvent
from app.models.revocation import ReleaseChainRevocation
from app.services.revocation import RevocationError, RevocationService, governance_state
from app.services.approval import ApprovalService
from app.services.distribution import DistributionService
from app.services.audit import AuditEventService
from app.models.approval import ApprovalRequest, ReleaseDecision
from app.services.release_decision import effective_release_decision


@pytest.mark.parametrize("same_key", [False, True])
def test_reviewed_competitors_use_one_atomic_original_audit(chain, monkeypatch, same_key):
    engine, contexts = chain
    target = contexts[0]["release"]
    with Session(engine) as db:
        expected = governance_state(db, "RELEASE", target, include_review=True)["review_context"]
    key = uuid.uuid4(); other = key if same_key else uuid.uuid4()
    first, second = overlapping_commands(engine, monkeypatch,
        lambda db: RevocationService(db).revoke("RELEASE", target, "Reviewed", request_id=key,
                                              expected_context=expected),
        lambda db: RevocationService(db).revoke("RELEASE", target, "Reviewed", request_id=other,
                                              expected_context=expected))
    assert first[0] == "ok" and second[0] == ("ok" if same_key else "conflict")
    with Session(engine) as db:
        assert count(db, ReleaseChainRevocation) == 1
        assert count(db, AuditEvent, event_type="RELEASE_CHAIN_REVOCATION") == 1
        event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == f"EVT-RCR-{key.hex}"))
        assert event.payload_json["review_context"] == expected


@pytest.mark.parametrize("revocation_first", [False, True])
def test_reviewed_ancestor_revocation_serializes_with_descendant_permission(chain, monkeypatch, revocation_first):
    engine, contexts = chain
    ids = contexts[0]
    with Session(engine) as db:
        expected = governance_state(db, "RELEASE", ids["release"], include_review=True)["review_context"]
        before = count(db, AuditEvent)
    revoke = lambda db: RevocationService(db).revoke("RELEASE", ids["release"], "Reviewed",
        request_id=uuid.uuid4(), expected_context=expected)
    distribute = lambda db: DistributionService(db).create_distribution(ids["package"],
        "DIST-COMPETING", "CUSTOMER", "C", request_id=uuid.uuid4())
    first, second = overlapping_commands(engine, monkeypatch,
        revoke if revocation_first else distribute, distribute if revocation_first else revoke)
    assert first[0] == "ok"
    assert second[0] == ("conflict" if revocation_first else "ok")
    with Session(engine) as db:
        assert count(db, ReleaseChainRevocation) == 1
        assert count(db, AuditEvent) == before + (1 if revocation_first else 2)


@pytest.mark.parametrize("revocation_first", [False, True])
def test_reviewed_decision_pin_is_checked_after_shared_release_lock(chain, monkeypatch, revocation_first):
    engine, contexts = chain
    target = contexts[0]["release"]
    with Session(engine) as db:
        expected = governance_state(db, "RELEASE", target, include_review=True)["review_context"]
        db.add(ApprovalRequest(approval_no="APR-REVIEW-NEW", target_type="RELEASE", target_id=target,
            snapshot_id=uuid.UUID(expected["snapshot_id"]), status="APPROVED"))
        db.commit()
    revoke = lambda db: RevocationService(db).revoke("RELEASE", target, "Reviewed", request_id=uuid.uuid4(),
        expected_context=expected)
    replace = lambda db: ApprovalService(db).create_release_decision("APR-REVIEW-NEW", "RD-REVIEW-NEW",
        "Manager", "READY", "RELEASE", request_id=uuid.uuid4(),
        supersedes_id=uuid.UUID(expected["release_decision_id"]), correction_reason="New formal review")
    first, second = overlapping_commands(engine, monkeypatch,
        revoke if revocation_first else replace, replace if revocation_first else revoke)
    assert first[0] == "ok" and second[0] == "conflict"
    if not revocation_first: assert "context" in second[1]
    with Session(engine) as db:
        assert count(db, ReleaseChainRevocation) == (1 if revocation_first else 0)
        assert count(db, AuditEvent, event_type="RELEASE_CHAIN_REVOCATION") == (1 if revocation_first else 0)


@pytest.mark.parametrize("reviewed", [False, True])
def test_original_retry_survives_later_decision_and_ancestor_changes(chain, reviewed):
    engine, contexts = chain
    ids = contexts[0]; key = uuid.uuid4()
    with Session(engine) as db:
        expected = governance_state(db, "DELIVERY_PACKAGE", ids["package"], include_review=True)["review_context"] if reviewed else None
        original = effective_release_decision(db, ids["release"])
        predecessor, snapshot = original.id, original.snapshot_id
        RevocationService(db).revoke("DELIVERY_PACKAGE", ids["package"], "Original", request_id=key,
                                     expected_context=expected)
        event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == f"EVT-RCR-{key.hex}"))
        payload = event.payload_json.copy()
        db.add(ApprovalRequest(approval_no="APR-LATER", target_type="RELEASE", target_id=ids["release"],
                              snapshot_id=snapshot, status="APPROVED")); db.commit()
        ApprovalService(db).create_release_decision("APR-LATER", "RD-LATER", "Manager", "READY", "RELEASE",
            request_id=uuid.uuid4(), supersedes_id=predecessor, correction_reason="Later decision")
        RevocationService(db).revoke("RELEASE", ids["release"], "Later ancestor", request_id=uuid.uuid4())
    with Session(engine) as db:
        before = count(db, AuditEvent)
        assert RevocationService(db).revoke("DELIVERY_PACKAGE", ids["package"], "Original", request_id=key,
                                           expected_context=expected).id == key
        event = db.scalar(select(AuditEvent).where(AuditEvent.event_no == f"EVT-RCR-{key.hex}"))
        assert event.payload_json == payload and count(db, AuditEvent) == before


def test_reviewed_pg_audit_failure_is_atomic_and_releases_locks(chain, monkeypatch):
    engine, contexts = chain
    target = contexts[0]["release"]; key = uuid.uuid4()
    with Session(engine) as db:
        expected = governance_state(db, "RELEASE", target, include_review=True)["review_context"]
        before = count(db, AuditEvent)
        original = AuditEventService.record
        def fail(service, **values):
            original(service, **values)
            raise RuntimeError("after original audit")
        monkeypatch.setattr(AuditEventService, "record", fail)
        with pytest.raises(RuntimeError):
            RevocationService(db).revoke("RELEASE", target, "Original", request_id=key, expected_context=expected)
        assert not db.in_transaction()
        assert count(db, ReleaseChainRevocation) == 0 and count(db, AuditEvent) == before
    monkeypatch.setattr(AuditEventService, "record", original)
    with Session(engine) as db:
        assert RevocationService(db).revoke("RELEASE", target, "Original", request_id=key,
                                           expected_context=expected).id == key


@pytest.mark.parametrize("same_key", [False, True])
def test_competing_release_revocations_are_serialized(chain, monkeypatch, same_key):
    engine, contexts = chain
    release_id = contexts[0]["release"]
    key = uuid.uuid4()
    other = key if same_key else uuid.uuid4()
    first, second = overlapping_commands(
        engine, monkeypatch,
        lambda db: RevocationService(db).revoke("RELEASE", release_id, "Safety issue", request_id=key),
        lambda db: RevocationService(db).revoke("RELEASE", release_id, "Safety issue", request_id=other),
    )
    assert first[0] == "ok"
    assert second[0] == ("ok" if same_key else "conflict")
    if same_key:
        assert first[1] == second[1]
    with Session(engine) as db:
        assert count(db, ReleaseChainRevocation) == 1
        assert count(db, AuditEvent, event_type="RELEASE_CHAIN_REVOCATION") == 1


def test_append_only_old_writer_guard_and_guarded_downgrade(chain):
    engine, contexts = chain
    context = contexts[0]
    with Session(engine, expire_on_commit=False) as db:
        row = RevocationService(db).revoke(
            "RELEASE", context["release"], "Permanent safety withdrawal", request_id=uuid.uuid4()
        )
        for sql in (
            "UPDATE release_chain_revocations SET reason=reason WHERE id=:id",
            "DELETE FROM release_chain_revocations WHERE id=:id",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(sql), {"id": row.id}); db.commit()
            db.rollback()
        with pytest.raises(DBAPIError, match="new permission-bearing records are forbidden"):
            db.execute(text("""INSERT INTO delivery_packages
                (id, package_no, revision, release_id, snapshot_id, recipient_type,
                 recipient_code, purpose, status, created_at)
                SELECT :id, 'OLD-WRITER', 1, release_id, snapshot_id,
                       recipient_type, recipient_code, purpose, 'READY', now()
                  FROM delivery_packages WHERE id=:package"""),
                {"id": uuid.uuid4(), "package": context["package"]})
            db.commit()
        db.rollback()
    with pytest.raises(DBAPIError, match="revocation history would be lost"):
        migration.downgrade(Config("alembic.ini"), "0025_release_decision_supersession")
