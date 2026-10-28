"""Joined synthetic domain acceptance; not real identity/browser/deployment acceptance.

Unlike the production catalogue fixtures, authorization is created DRAFT through the
real service with authenticated creator evidence and can only progress via P1 approval.
Existing route/proxy authorization tests remain separate and are not replaced here.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.actor import ActorContext
from app.models.audit import AuditEvent
from app.models.core import Release
from app.models.distribution import SoftwareAuthorization
from app.models.production import Deployment, ManufacturingSite, ProductionBatch, ProductionLine, SoftwareChangeover
from app.models.production_history import BatchBaseline, BatchCorrection, ChangeoverBaseline, ChangeoverCorrection
from app.models.security import SecurityPrincipal
from app.services.audit import AuditEventService
from app.services.production import ProductionError, ProductionService
from app.services.production_history import effective_actual, effective_batch, effective_changeover
from app.services.revocation import RevocationService, governance_state
from test_authorization_approval import approval_db, actor_request, body, service, submit  # noqa:F401
from test_authorization_approval_postgres import approval_pg  # noqa:F401
from test_command_concurrency_postgres import pg  # noqa:F401

AT = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)


@pytest.fixture(params=['sqlite', 'postgres'])
def integrated_db(request):
    if request.param == 'sqlite':
        yield request.getfixturevalue('approval_db')
    else:
        engine, ids = request.getfixturevalue('approval_pg')
        with Session(engine, expire_on_commit=False) as db:
            yield db, ids


def totals(db):
    return tuple(db.scalar(select(func.count()).select_from(model)) for model in (
        AuditEvent, Deployment, SoftwareChangeover, ProductionBatch,
        BatchBaseline, BatchCorrection, ChangeoverBaseline, ChangeoverCorrection))


def event(db, number, entity, actor_id):
    row = db.scalar(select(AuditEvent).where(AuditEvent.event_no == number))
    assert row is not None and row.entity_id == entity
    assert row.actor_principal_id == actor_id and row.declared_actor_name is None
    return row


def approved_production(db, ids):
    """No APPROVED authorization shortcut; even the creator rejection is real."""
    authorization = db.get(SoftwareAuthorization, ids['authorization'])
    assert authorization.status == 'DRAFT' and authorization.approved_at is None
    creation = event(db, 'EVT-PA-'+authorization.id.hex, authorization.id, ids['people']['creator'])
    assert creation.payload_json['status'] == 'DRAFT'
    site = ManufacturingSite(site_code='PAA-SITE', customer_id=authorization.customer_id,
        project_id=authorization.project_id, name='Synthetic isolated site')
    db.add(site); db.flush()
    line = ProductionLine(site_id=site.id, line_code='PAA-LINE', name='Synthetic isolated line')
    current = db.get(Release, ids['release'])
    old = Release(software_id=current.software_id, release_type=current.release_type,
                  version='INTEGRATION-OLD', status='RELEASED')
    corrected_old = Release(software_id=current.software_id, release_type=current.release_type,
                            version='INTEGRATION-CORRECTED-OLD', status='RELEASED')
    db.add_all([line, old, corrected_old]); db.commit()
    principal = db.get(SecurityPrincipal, ids['people']['approver'])
    actor = ActorContext(principal.display_name, principal.id, principal.display_name, None, 'AUTHENTICATED_PRINCIPAL')
    production = ProductionService(db)
    confirmation = body(db, ids)
    before = totals(db)
    with pytest.raises(HTTPException) as denial:
        submit(db, ids, confirmation, name='creator')
    assert denial.value.status_code == 403 and denial.value.detail == 'creator_cannot_approve'
    denied_authorization = db.get(SoftwareAuthorization, ids['authorization'], populate_existing=True)
    assert denied_authorization.status == 'DRAFT' and denied_authorization.approved_at is None
    with pytest.raises(ProductionError, match='approved production authorization'):
        production.create_deployment('INT-PREAPPROVAL', authorization.id, line.id,
                                     actor_context=actor, request_id=uuid.uuid4())
    assert totals(db) == before
    original_receipt = submit(db, ids, confirmation)
    assert original_receipt['creator_principal_id'] != original_receipt['approver_principal_id']
    assert original_receipt['applied_status'] == 'APPROVED'
    assert db.get(SoftwareAuthorization, authorization.id).status == 'APPROVED'
    deployment_key = uuid.uuid4()
    deployment = production.create_deployment('INT-DEPLOY', authorization.id, line.id,
                                              actor_context=actor, request_id=deployment_key)
    assert deployment.status == 'PENDING'
    assert (deployment.expected_release_id, deployment.expected_snapshot_id) == (ids['release'], ids['snapshot'])
    event(db, 'EVT-DPLOY-'+deployment_key.hex, deployment.id, actor.principal_id)
    before = totals(db)
    with pytest.raises(ProductionError, match='matching actual software'):
        production.create_batch(deployment.deployment_no, 'INT-PREMATCH', started_at=AT,
                                actor_context=actor, request_id=uuid.uuid4())
    assert totals(db) == before
    actual_key = uuid.uuid4()
    actual = production.report_actual(deployment.deployment_no, ids['release'], ids['snapshot'],
        deployed_at=AT, actor_context=actor, request_id=actual_key, expected_version=0)
    assert actual.status == 'MATCH' and effective_actual(db, deployment).status == 'MATCH'
    event(db, 'EVT-DA-'+actual_key.hex, deployment.id, actor.principal_id)
    co_key, batch_key = uuid.uuid4(), uuid.uuid4()
    co = production.create_changeover(deployment.deployment_no, 'INT-CHANGEOVER', old.id,
        changed_at=AT, note='Original source', actor_context=actor, request_id=co_key)
    batch = production.create_batch(deployment.deployment_no, 'INT-BATCH', changeover_id=co.id,
        started_at=AT+timedelta(minutes=10), note='Original batch', actor_context=actor, request_id=batch_key)
    event(db, 'EVT-CO-'+co_key.hex, co.id, actor.principal_id)
    event(db, 'EVT-PB-'+batch_key.hex, batch.id, actor.principal_id)
    assert (batch.release_id, batch.snapshot_id) == (ids['release'], ids['snapshot'])
    return actor, line.id, deployment, co, batch, corrected_old.id, confirmation, original_receipt


def test_dual_approval_production_corrections_revocation_and_original_receipt(integrated_db):
    db, ids = integrated_db
    actor, line_id, deployment, co, batch, source, confirmation, receipt = approved_production(db, ids)
    production = ProductionService(db)
    original_source = co.from_release_id
    co_key, batch_key = uuid.uuid4(), uuid.uuid4()
    co_body = dict(changeover_no=co.changeover_no, from_release_id=source,
        changed_at=AT+timedelta(minutes=1), note='Corrected source', correction_reason='Synthetic exact source correction',
        expected_revision=0, predecessor_id=None, actor_context=actor, request_id=co_key)
    batch_body = dict(batch_no=batch.batch_no, started_at=AT+timedelta(minutes=11),
        ended_at=AT+timedelta(minutes=20), changeover_id=co.id, note='Corrected batch interval',
        correction_reason='Synthetic exact interval correction', expected_revision=0,
        predecessor_id=None, actor_context=actor, request_id=batch_key)
    first_co = production.correct_changeover(**co_body)
    first_batch = production.correct_batch(**batch_body)
    count = totals(db)
    assert production.correct_changeover(**co_body) == first_co
    assert production.correct_batch(**batch_body) == first_batch
    assert totals(db) == count
    db.expire_all()
    assert db.get(SoftwareChangeover, co.id).from_release_id == original_source
    assert db.get(ProductionBatch, batch.id).note == 'Original batch'
    current_co, current_batch = effective_changeover(db, co), effective_batch(db, batch)
    assert current_co.from_release_id == source and current_co.to_release_id == ids['release']
    assert current_batch.release_id == ids['release'] and current_batch.snapshot_id == ids['snapshot']
    assert current_co.history_state == current_batch.history_state == 'IMPORTED_CORRECTED'
    for model, parent_field, parent_id, key in (
        (ChangeoverCorrection, 'changeover_id', co.id, co_key), (BatchCorrection, 'batch_id', batch.id, batch_key)):
        rows = db.scalars(select(model).where(getattr(model, parent_field) == parent_id)).all()
        assert len(rows) == 1 and rows[0].id == key and rows[0].revision == 1 and rows[0].predecessor_id is None
    for prefix, key, target in [('EVT-CC-', co_key, co.id), ('EVT-BC-', batch_key, batch.id)]:
        audit = event(db, prefix+key.hex, target, actor.principal_id)
        assert audit.payload_json['deployment_no'] == deployment.deployment_no
    review = governance_state(db, 'AUTHORIZATION', ids['authorization'], include_review=True)['review_context']
    RevocationService(db).revoke('AUTHORIZATION', ids['authorization'], 'Synthetic withdrawal of new production work',
        actor_context=actor, request_id=uuid.uuid4(), expected_context=review)
    assert governance_state(db, 'AUTHORIZATION', ids['authorization'])['eligible_for_new_work'] is False
    before = totals(db)
    historical = service(db).receipt(ids['number'], actor_request(db, ids), confirmation['request_id'])
    assert historical == receipt and historical['applied_status'] == 'APPROVED'
    assert totals(db) == before
    # New work is blocked; historical correction/reporting policy is intentionally unchanged.
    with pytest.raises(ProductionError, match='revoked'):
        production.create_deployment('INT-AFTER-REVOCATION', ids['authorization'], line_id,
                                     actor_context=actor, request_id=uuid.uuid4())
    with pytest.raises(ProductionError, match='revoked'):
        production.create_batch(deployment.deployment_no, 'INT-AFTER-REVOCATION', started_at=AT,
                                actor_context=actor, request_id=uuid.uuid4())
    assert totals(db) == before


def test_joined_batch_correction_audit_failure_rolls_back_and_same_key_recovers(integrated_db, monkeypatch):
    db, ids = integrated_db
    actor, _, _, co, batch, _, _, _ = approved_production(db, ids)
    key = uuid.uuid4()
    body = dict(batch_no=batch.batch_no, started_at=AT+timedelta(minutes=11), ended_at=AT+timedelta(minutes=20),
        changeover_id=co.id, note='Atomic correction', correction_reason='Synthetic audit atomicity',
        expected_revision=0, predecessor_id=None, actor_context=actor, request_id=key)
    before = totals(db)
    with monkeypatch.context() as patch:
        original = AuditEventService.record
        def fail_after_insert(service, **kwargs):
            original(service, **kwargs)
            raise RuntimeError('injected joined correction audit failure')
        patch.setattr(AuditEventService, 'record', fail_after_insert)
        with pytest.raises(RuntimeError, match='injected joined correction audit failure'):
            ProductionService(db).correct_batch(**body)
    assert not db.in_transaction()
    with Session(db.get_bind()) as persisted:
        assert totals(persisted) == before
        assert persisted.get(BatchCorrection, key) is None
        assert persisted.scalar(select(BatchBaseline).where(BatchBaseline.batch_id == batch.id)) is None
        assert persisted.scalar(select(AuditEvent).where(AuditEvent.event_no == 'EVT-BC-'+key.hex)) is None
        assert persisted.get(ProductionBatch, batch.id).note == 'Original batch'
    assert totals(db) == before
    assert db.get(BatchCorrection, key) is None
    assert db.scalar(select(BatchBaseline).where(BatchBaseline.batch_id == batch.id)) is None
    db.expire_all()
    assert db.get(ProductionBatch, batch.id).note == 'Original batch'
    first = ProductionService(db).correct_batch(**body)
    after = totals(db)
    assert ProductionService(db).correct_batch(**body) == first and totals(db) == after
    assert db.get(BatchCorrection, key).revision == 1
    event(db, 'EVT-BC-'+key.hex, batch.id, actor.principal_id)
