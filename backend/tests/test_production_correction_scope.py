"""Real route authorization binds correction children to the authorized parent.

Synthetic principals are injected into an isolated ASGI app, not a real provider.
SQLite runs locally; PostgreSQL variants use the existing disposable migrated fixture.
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import JSON, MetaData, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models
from app.api import production
from app.auth import AuthenticatedPrincipal
from app.authorization import AuthorizationError
from app.core.config import settings
from app.core.db import Base, get_db
from app.models.audit import AuditEvent
from app.models.core import Customer, Project, Release, SoftwareProduct, Supplier
from app.models.distribution import SoftwareAuthorization
from app.models.production import Deployment, ManufacturingSite, ProductionBatch, ProductionLine, SoftwareChangeover
from app.models.production_history import BatchBaseline, BatchCorrection, ChangeoverBaseline, ChangeoverCorrection
from app.models.security import GlobalRoleAssignment, ProjectMembership, SecurityPrincipal
from test_command_concurrency_postgres import pg  # noqa: F401


@pytest.fixture(params=['sqlite', 'postgres'])
def correction_context(request, monkeypatch):
    if request.param == 'postgres':
        engine, _ = request.getfixturevalue('pg')
    else:
        metadata = MetaData()
        for table in Base.metadata.sorted_tables:
            copied = table.to_metadata(metadata)
            for column in copied.columns:
                if isinstance(column.type, JSONB):
                    column.type = JSON()
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        metadata.create_all(engine)
    monkeypatch.setattr(settings, 'auth_mode', 'oidc')
    with Session(engine, expire_on_commit=False) as db:
        supplier = Supplier(code='SCOPE-SUP', name='Synthetic supplier')
        customer = Customer(code='SCOPE-CUS', name='Synthetic customer')
        actor = SecurityPrincipal(issuer='https://synthetic.example', subject='scope-operator',
                                  principal_type='USER', display_name='Synthetic operator')
        db.add_all([supplier, customer, actor]); db.flush()
        product = SoftwareProduct(supplier_id=supplier.id, code='SCOPE-SW', name='Synthetic software')
        owned = Project(customer_id=customer.id, project_code='SCOPE-OWN', name='Owned')
        foreign = Project(customer_id=customer.id, project_code='SCOPE-OTHER', name='Other')
        db.add_all([product, owned, foreign]); db.flush()
        target = Release(software_id=product.id, release_type='STANDARD', version='scope-target')
        source = Release(software_id=product.id, release_type='STANDARD', version='scope-source')
        db.add_all([target, source]); db.flush()
        from app.models.snapshot import ReleaseSnapshot
        snapshot = ReleaseSnapshot(release_id=target.id, snapshot_no='SCOPE-SNAP', snapshot_number=1,
                                   status='FROZEN', content_hash='b'*64)
        db.add(snapshot); db.flush()
        deps, children = {}, {}
        for name, project in [('owned', owned), ('foreign', foreign), ('sibling', owned)]:
            authorization = SoftwareAuthorization(authorization_no='SCOPE-AUTH-'+name,
                release_id=target.id, snapshot_id=snapshot.id, customer_id=customer.id, project_id=project.id,
                site_code='SCOPE-SITE-'+name, line_code='SCOPE-LINE', purpose='PRODUCTION', status='APPROVED')
            site = ManufacturingSite(site_code='SCOPE-SITE-'+name, customer_id=customer.id,
                                     project_id=project.id, name='Synthetic site')
            db.add_all([authorization, site]); db.flush()
            line = ProductionLine(site_id=site.id, line_code='SCOPE-LINE', name='Synthetic line')
            db.add(line); db.flush()
            dep = Deployment(deployment_no='SCOPE-DEP-'+name, authorization_id=authorization.id,
                             production_line_id=line.id, expected_release_id=target.id,
                             expected_snapshot_id=snapshot.id)
            db.add(dep); db.flush()
            co = SoftwareChangeover(changeover_no='SCOPE-CO-'+name, deployment_id=dep.id,
                 authorization_id=authorization.id, from_release_id=source.id,
                 to_release_id=target.id, status='COMPLETED', changed_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
            batch = ProductionBatch(batch_no='SCOPE-BATCH-'+name, deployment_id=dep.id,
                authorization_id=authorization.id, release_id=target.id, snapshot_id=snapshot.id,
                started_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
            db.add_all([co, batch]); db.flush()
            deps[name] = dep.deployment_no
            children[name] = {'changeover': co.changeover_no, 'batch': batch.batch_no}
        grant = ProjectMembership(principal_id=actor.id, project_id=owned.id, role='PRODUCTION_OPERATOR')
        db.add(grant); db.commit()
        actor_id, grant_id, source_id = actor.id, grant.id, source.id
    app = FastAPI()
    app.include_router(production.router)
    @app.exception_handler(AuthorizationError)
    async def denied(_request, exc):
        return JSONResponse(status_code=403, content={'detail': str(exc)})
    @app.middleware('http')
    async def inject_synthetic_principal(req, call_next):
        req.state.principal = AuthenticatedPrincipal(id=actor_id, issuer='https://synthetic.example',
            subject='scope-operator', principal_type='USER', display_name='Synthetic operator', email=None)
        return await call_next(req)
    def route_db():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = route_db
    with TestClient(app) as client:
        yield {'client': client, 'engine': engine, 'deps': deps, 'children': children,
               'actor_id': actor_id, 'grant_id': grant_id, 'source_id': source_id}
    if request.param == 'sqlite':
        engine.dispose()


def payload(ctx, kind, **changes):
    data = {'request_id': str(uuid.uuid4()), 'expected_revision': 0, 'predecessor_id': None,
            'correction_reason': 'Correct synthetic recording', 'note': 'corrected'}
    if kind == 'changeover':
        data.update(from_release_id=str(ctx['source_id']), changed_at='2026-01-02T00:00:00Z')
    else:
        data.update(started_at='2026-01-02T00:00:00Z', ended_at=None, changeover_id=None)
    return {**data, **changes}


def post(ctx, kind, parent, child, body):
    segment = 'changeovers' if kind == 'changeover' else 'batches'
    return ctx['client'].post(f"/api/v1/deployments/{ctx['deps'][parent]}/{segment}/{child}/correction", json=body)


def stored(ctx):
    # Full baseline/correction/audit and physical facts before/after denial, not just counts.
    models = [Deployment, ProductionBatch, SoftwareChangeover, BatchBaseline,
              ChangeoverBaseline, BatchCorrection, ChangeoverCorrection, AuditEvent]
    with Session(ctx['engine']) as db:
        return {model.__tablename__: sorted(repr(tuple(row)) for row in db.execute(select(model.__table__)))
                for model in models}


@pytest.mark.parametrize('kind', ['changeover', 'batch'])
def test_foreign_child_cannot_use_authorized_parent(correction_context, kind):
    ctx = correction_context
    before = stored(ctx)
    response = post(ctx, kind, 'owned', ctx['children']['foreign'][kind], payload(ctx, kind))
    assert response.status_code == 404, response.text
    assert response.json() == {'detail': 'production correction target not found'}
    assert stored(ctx) == before


@pytest.mark.parametrize('kind', ['changeover', 'batch'])
@pytest.mark.parametrize('target', ['sibling', 'missing'])
def test_parent_binding_holds_for_same_project_and_missing_targets(correction_context, kind, target, monkeypatch):
    ctx = correction_context
    def must_not_run(*args, **kwargs):
        raise AssertionError('service must not run for mismatched route context')
    monkeypatch.setattr(production.ProductionService, 'correct_'+kind, must_not_run)
    before = stored(ctx)
    child = ctx['children']['sibling'][kind] if target == 'sibling' else 'SCOPE-MISSING'
    response = post(ctx, kind, 'owned', child, payload(ctx, kind))
    assert response.status_code == 404
    assert response.json() == {'detail': 'production correction target not found'}
    assert stored(ctx) == before


@pytest.mark.parametrize('kind', ['changeover', 'batch'])
def test_unauthorized_parent_rejects_before_child_resolution(correction_context, kind, monkeypatch):
    ctx = correction_context
    def must_not_run(*args, **kwargs):
        raise AssertionError('child query must not run before parent authorization')
    monkeypatch.setattr(production, '_require_correction_target', must_not_run)
    before = stored(ctx)
    for child in [ctx['children']['foreign'][kind], 'SCOPE-MISSING']:
        response = post(ctx, kind, 'foreign', child, payload(ctx, kind))
        assert response.status_code == 403
        assert response.json() == {'detail': 'insufficient_scope'}
    assert stored(ctx) == before


@pytest.mark.parametrize('kind', ['changeover', 'batch'])
def test_valid_target_success_and_identical_replay_preserve_one_correction(correction_context, kind):
    ctx = correction_context
    body = payload(ctx, kind)
    first = post(ctx, kind, 'owned', ctx['children']['owned'][kind], body)
    assert first.status_code == 200, first.text
    before_replay = stored(ctx)
    replay = post(ctx, kind, 'owned', ctx['children']['owned'][kind], body)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert stored(ctx) == before_replay
    model = ChangeoverCorrection if kind == 'changeover' else BatchCorrection
    prefix = 'EVT-CC-' if kind == 'changeover' else 'EVT-BC-'
    with Session(ctx['engine']) as db:
        row = db.get(model, uuid.UUID(body['request_id']))
        assert row is not None and row.revision == 1 and row.actor_principal_id == ctx['actor_id']
        audit = db.scalar(select(AuditEvent).where(AuditEvent.event_no == prefix+uuid.UUID(body['request_id']).hex))
        assert audit.actor_principal_id == ctx['actor_id'] and audit.action == 'CORRECTED'


@pytest.mark.parametrize('kind', ['changeover', 'batch'])
def test_suspended_scope_cannot_create_or_replay(correction_context, kind):
    ctx = correction_context
    body = payload(ctx, kind)
    assert post(ctx, kind, 'owned', ctx['children']['owned'][kind], body).status_code == 200
    with Session(ctx['engine']) as db:
        db.get(ProjectMembership, ctx['grant_id']).status = 'SUSPENDED'
        db.commit()
    before = stored(ctx)
    for candidate in [body, payload(ctx, kind)]:
        response = post(ctx, kind, 'owned', ctx['children']['owned'][kind], candidate)
        assert response.status_code == 403
    assert stored(ctx) == before


@pytest.mark.parametrize('kind', ['changeover', 'batch'])
def test_global_admin_still_cannot_mix_parent_and_child_or_replay_through_wrong_parent(correction_context, kind):
    ctx = correction_context
    with Session(ctx['engine']) as db:
        db.add(GlobalRoleAssignment(principal_id=ctx['actor_id'], role='PLATFORM_ADMIN'))
        db.commit()
    body = payload(ctx, kind)
    assert post(ctx, kind, 'foreign', ctx['children']['foreign'][kind], body).status_code == 200
    before = stored(ctx)
    for candidate in [body, payload(ctx, kind)]:
        response = post(ctx, kind, 'owned', ctx['children']['foreign'][kind], candidate)
        assert response.status_code == 404
        assert response.json() == {'detail': 'production correction target not found'}
    assert stored(ctx) == before


@pytest.mark.parametrize('kind', ['changeover', 'batch'])
def test_existing_request_id_for_other_child_cannot_replay_or_mutate(correction_context, kind):
    ctx = correction_context
    body = payload(ctx, kind)
    assert post(ctx, kind, 'owned', ctx['children']['owned'][kind], body).status_code == 200
    before = stored(ctx)
    # Correct parent, different child, same authorized project: existing service
    # request binding must still reject a key belonging to another record.
    response = post(ctx, kind, 'sibling', ctx['children']['sibling'][kind], body)
    assert response.status_code == 409
    assert stored(ctx) == before
