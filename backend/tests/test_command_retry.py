"""Business retry/rollback checks; PostgreSQL lock coverage is in a separate module."""
import uuid
from dataclasses import replace
from datetime import datetime, timezone, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from test_command_audit import prepare_snapshot_source, trusted_actor
from test_distribution_catalog import chain
from test_impact_assessments import context
from app.actor import ActorContext
from app.api.production import BatchCreate, create_batch
from app.api.releases import SnapshotCreate, create_snapshot
from app.models.audit import AuditEvent
from app.models.core import Release
from app.models.production import Deployment, ProductionBatch
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.services.audit import AuditEventService
from app.services.production import ProductionError, ProductionService
from app.services.snapshot import SnapshotError, SnapshotService


def counts(db):
    return {model: db.scalar(select(func.count()).select_from(model))
            for model in (ReleaseSnapshot, SnapshotArtifact, ProductionBatch, AuditEvent)}


@pytest.fixture
def batch_context(chain):
    db, release, _, old, _, _, authorizations, _, _ = chain
    deployment = db.scalar(select(Deployment).where(Deployment.deployment_no == 'DEP'))
    deployment.authorization_id = authorizations[1].id
    db.commit()
    return db, deployment, authorizations[1]


def test_snapshot_retry_returns_frozen_original_after_source_changes(context):
    db, _, release, _, _ = context
    prepare_snapshot_source(db, release)
    key = uuid.uuid4()
    first = SnapshotService().create(db, release.id, request_id=key)
    before = counts(db)
    release.version = 'new source version'
    db.commit()
    retry = SnapshotService().create(db, release.id, request_id=key)
    assert retry.id == key == first.id
    assert counts(db) == before
    assert retry.release_metadata_json['version'] == '1'
    # No key preserves legacy behavior: each call creates a fresh freeze.
    assert SnapshotService().create(db, release.id).id != key


@pytest.mark.parametrize('case', ['release', 'actor', 'legacy', 'mode', 'declaration'])
def test_snapshot_conflicting_key_and_actor_binding(context, case):
    db, _, release, old, _ = context
    prepare_snapshot_source(db, release)
    actor = trusted_actor(db, 'maintainer', 'Maintainer')
    key = uuid.uuid4()
    SnapshotService().create(db, release.id, request_id=key, actor_context=actor)
    target = release.id
    if case == 'release':
        other = Release(software_id=release.software_id, release_type='STANDARD', version='2')
        db.add(other); db.commit(); target = other.id
    elif case == 'actor':
        actor = trusted_actor(db, 'other', 'Maintainer')
    elif case == 'legacy': key = old.id
    elif case == 'mode': actor = ActorContext.legacy(None)
    else: actor = replace(actor, declared_name='changed declaration')
    before = counts(db)
    with pytest.raises(SnapshotError, match='request_id'):
        SnapshotService().create(db, target, request_id=key, actor_context=actor)
    assert counts(db) == before


def test_snapshot_http_contract_legacy_and_optional_body(context):
    db, _, release, _, _ = context
    prepare_snapshot_source(db, release)
    first = create_snapshot(release.id, db, payload=SnapshotCreate(request_id=uuid.uuid4()))
    legacy = create_snapshot(release.id, db)
    assert first['id'] != legacy['id']
    with pytest.raises(ValidationError): SnapshotCreate(request_id='invalid')
    with pytest.raises(ValidationError): SnapshotCreate(unexpected=True)


def test_batch_retry_precedes_mutable_state_and_quota_checks(batch_context):
    db, deployment, authorization = batch_context
    authorization.batch_limit = 1; db.commit()
    actor = trusted_actor(db, 'operator', 'Operator')
    key = uuid.uuid4()
    first = ProductionService(db).create_batch('DEP', 'RETRY', request_id=key, actor_context=actor)
    before = counts(db)
    deployment.status = 'MISMATCH'; authorization.status = 'REVOKED'; db.commit()
    retry = ProductionService(db).create_batch('DEP', 'RETRY', request_id=key, actor_context=actor)
    assert retry.id == first.id == key and counts(db) == before


@pytest.mark.parametrize('field,value', [('batch_no', 'OTHER'), ('note', 'changed'),
    ('changeover_id', uuid.uuid4()), ('started_at', datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ('deployment_no', 'OTHER')])
def test_batch_payload_conflicts(batch_context, field, value):
    db, deployment, _ = batch_context
    key = uuid.uuid4()
    args = dict(deployment_no='DEP', batch_no='RETRY', request_id=key)
    ProductionService(db).create_batch(**args)
    if field == 'deployment_no':
        other = Deployment(deployment_no='OTHER', authorization_id=deployment.authorization_id,
            production_line_id=deployment.production_line_id,
            expected_release_id=deployment.expected_release_id,
            expected_snapshot_id=deployment.expected_snapshot_id, status='MATCH')
        db.add(other); db.commit()
    before = counts(db)
    with pytest.raises(ProductionError, match='request_id'):
        ProductionService(db).create_batch(**{**args, field: value})
    assert counts(db) == before


def test_batch_actor_conflict_and_duplicate_business_number(batch_context):
    db, _, _ = batch_context
    actor = trusted_actor(db, 'operator', 'Operator')
    key = uuid.uuid4()
    ProductionService(db).create_batch('DEP', 'RETRY', request_id=key, actor_context=actor)
    other = trusted_actor(db, 'other', 'Operator')
    before = counts(db)
    for current in (other, ActorContext.legacy(None)):
        with pytest.raises(ProductionError, match='request_id'):
            ProductionService(db).create_batch('DEP', 'RETRY', request_id=key, actor_context=current)
    with pytest.raises(ProductionError, match='number already exists'):
        ProductionService(db).create_batch('DEP', 'RETRY', request_id=uuid.uuid4())
    with pytest.raises(ProductionError, match='number already exists'):
        ProductionService(db).create_batch('DEP', 'RETRY')
    assert counts(db) == before


def test_batch_timestamp_normalization_and_http_response(batch_context):
    db, _, _ = batch_context
    key = uuid.uuid4()
    first = create_batch('DEP', BatchCreate(batch_no='RETRY', request_id=key,
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc)), db)
    retry = create_batch('DEP', BatchCreate(batch_no='RETRY', request_id=key,
        started_at=datetime(2026, 1, 1, 8, tzinfo=timezone(timedelta(hours=8)))), db)
    assert retry == first
    with pytest.raises(HTTPException) as exc:
        create_batch('DEP', BatchCreate(batch_no='OTHER', request_id=key), db)
    assert exc.value.status_code == 409
    with pytest.raises(ValidationError): BatchCreate(batch_no='B', request_id='invalid')


@pytest.mark.parametrize('kind', ['snapshot', 'batch'])
@pytest.mark.parametrize('failure', ['audit', 'flush', 'commit', 'validation'])
def test_failures_rollback_and_key_can_be_retried(context, batch_context, monkeypatch, kind, failure):
    if kind == 'snapshot':
        db, _, release, _, _ = context
        prepare_snapshot_source(db, release)
        release_id = release.id
        run = lambda: SnapshotService().create(db, release_id, request_id=key)
    else:
        db, deployment, _ = batch_context
        run = lambda: ProductionService(db).create_batch('DEP', 'ROLLBACK', request_id=key)
    key = uuid.uuid4(); before = counts(db)
    with monkeypatch.context() as patch:
        if failure == 'audit':
            original = AuditEventService.record
            def fail(*a, **kw):
                original(*a, **kw)
                raise RuntimeError('audit failure')
            patch.setattr(AuditEventService, 'record', fail)
        elif failure == 'commit':
            def fail(*a, **kw): raise RuntimeError('commit failure')
            patch.setattr(db, 'commit', fail)
        elif failure == 'flush':
            def fail(*a, **kw): raise IntegrityError('injected', {}, Exception('failure'))
            patch.setattr(db, 'flush', fail)
        elif kind == 'snapshot':
            # Invalid source is persisted, not a pending write, and restored below.
            from app.models.core import Artifact
            artifact = db.scalar(select(Artifact)); artifact.distribution_level = 'EXTERNAL'; db.commit()
        else:
            deployment.status = 'MISMATCH'; db.commit()
        with pytest.raises((RuntimeError, SnapshotError, ProductionError)):
            run()
    assert counts(db) == before
    if failure == 'validation':
        if kind == 'snapshot': artifact.distribution_level = 'INTERNAL_ONLY'
        else: deployment.status = 'MATCH'
        db.commit()
    assert run().id == key
    assert not db.in_transaction() or not db.dirty


@pytest.mark.parametrize('kind', ['snapshot', 'batch'])
def test_oidc_retry_still_requires_active_exact_scope(context, batch_context, monkeypatch, kind):
    from app.auth import AuthenticatedPrincipal
    from app.authorization import AuthorizationError
    from app.core.config import settings
    from app.models.security import ProjectMembership, SecurityPrincipal, SoftwareMembership
    from starlette.requests import Request
    db, _, release, _, _ = context
    if kind == 'snapshot': prepare_snapshot_source(db, release)
    actor = trusted_actor(db, f'{kind}-scope', 'Scoped Operator')
    principal = db.get(SecurityPrincipal, actor.principal_id)
    request = Request({'type': 'http', 'method': 'POST', 'path': '/', 'headers': []})
    request.state.principal = AuthenticatedPrincipal(id=principal.id, issuer=principal.issuer,
        subject=principal.subject, principal_type=principal.principal_type,
        display_name=principal.display_name, email=None)
    key = uuid.uuid4()
    if kind == 'snapshot':
        grant = SoftwareMembership(principal_id=principal.id, software_id=release.software_id,
                                   role='SOFTWARE_MAINTAINER', status='ACTIVE')
        run = lambda: create_snapshot(release.id, db, request, SnapshotCreate(request_id=key))
    else:
        authorization = batch_context[2]
        grant = ProjectMembership(principal_id=principal.id, project_id=authorization.project_id,
                                  role='PRODUCTION_OPERATOR', status='ACTIVE')
        run = lambda: create_batch('DEP', BatchCreate(batch_no='SCOPED', request_id=key), db, request)
    monkeypatch.setattr(settings, 'auth_mode', 'oidc')
    before = counts(db)
    with pytest.raises(AuthorizationError): run()
    assert counts(db) == before
    db.add(grant); db.commit()
    first = run(); assert run() == first
    grant.status = 'SUSPENDED'; db.commit()
    after = counts(db)
    with pytest.raises(AuthorizationError): run()
    assert counts(db) == after


@pytest.mark.parametrize('body', [None, 'null', '{}', 'key'])
def test_snapshot_http_optional_body_compatibility(monkeypatch, body):
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api import releases
    from app.core.config import settings
    key = uuid.uuid4()
    calls = []
    def fake_create(self, db, release_id, actor_context=None, request_id=None):
        calls.append(request_id)
        return SimpleNamespace(id=key, snapshot_no='S', content_hash='a' * 64, status='FROZEN')
    monkeypatch.setattr(settings, 'auth_mode', 'disabled')
    monkeypatch.setattr(settings, 'read_only_mode', False)
    monkeypatch.setattr(SnapshotService, 'create', fake_create)
    def fake_db(): yield SimpleNamespace(get=lambda *args: None)
    app.dependency_overrides[releases.get_db] = fake_db
    try:
        with TestClient(app) as client:
            kwargs = {} if body is None else {'content': body if body != 'key' else '{"request_id":"'+str(key)+'"}',
                                             'headers': {'Content-Type': 'application/json'}}
            response = client.post(f'/api/v1/releases/{uuid.uuid4()}/create-snapshot', **kwargs)
            assert response.status_code == 201
            assert calls == [key if body == 'key' else None]
    finally:
        app.dependency_overrides.pop(releases.get_db, None)
