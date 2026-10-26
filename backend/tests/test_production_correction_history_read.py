"""Public sample history: exact nested scope, bounded evidence and coherent heads."""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models.production import ProductionBatch, SoftwareChangeover
from app.models.production_history import BatchBaseline, BatchCorrection, ChangeoverBaseline, ChangeoverCorrection
from app.services.production_history import effective_batch, effective_changeover
from test_production_correction_scope import correction_context, payload, post, stored  # noqa: F401
from test_command_concurrency_postgres import pg  # noqa: F401


def url(ctx, kind, child=None):
    plural = 'changeovers' if kind == 'changeover' else 'batches'
    return f"/api/v1/deployments/{ctx['deps']['owned']}/{plural}/{child or ctx['children']['owned'][kind]}/history"


def models(kind):
    return ((SoftwareChangeover, ChangeoverBaseline, ChangeoverCorrection, 'changeover_id', 'changeover_no')
            if kind == 'changeover' else
            (ProductionBatch, BatchBaseline, BatchCorrection, 'batch_id', 'batch_no'))


def append(ctx, kind, revision=0, predecessor=None, **kw):
    body = payload(ctx, kind)
    body.update(expected_revision=revision, predecessor_id=predecessor,
                note=f'corrected note {revision+1}', correction_reason=f'reason {revision+1}')
    body.update(kw)
    response = post(ctx, kind, 'owned', ctx['children']['owned'][kind], body)
    assert response.status_code == 200, response.text
    return body['request_id']


@pytest.mark.parametrize('kind', ['changeover', 'batch'])
def test_no_baseline_is_unknown_and_read_only(correction_context, kind):
    ctx = correction_context; before = stored(ctx)
    response = ctx['client'].get(url(ctx, kind))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['recorded_baseline'] is None and data['history_state'] == 'NOT_RECORDED'
    assert data['effective']['revision'] == 0 and data['effective']['head_id'] is None
    assert data['corrections'] == [] and data['correction_count'] == 0
    assert data['truncated'] is False and data['limit'] == 50
    assert stored(ctx) == before


@pytest.mark.parametrize('kind', ['changeover', 'batch'])
def test_exact_parent_mismatch_and_missing_indistinguishable(correction_context, kind):
    ctx = correction_context; before = stored(ctx)
    for child in (ctx['children']['foreign'][kind], ctx['children']['sibling'][kind], 'MISSING'):
        response = ctx['client'].get(url(ctx, kind, child))
        assert response.status_code == 404
        assert response.json() == {'detail': 'production history target not found'}
    assert stored(ctx) == before


@pytest.mark.parametrize('kind', ['changeover', 'batch'])
def test_original_head_null_replacement_and_audit_projection(correction_context, kind):
    ctx = correction_context
    first = append(ctx, kind)
    second = append(ctx, kind, 1, first, note=None)
    before = stored(ctx)
    response = ctx['client'].get(url(ctx, kind)); data = response.json()
    assert data['effective']['revision'] == 2 and data['effective']['head_id'] == second
    assert data['effective']['values']['note'] is None
    assert data['recorded_baseline']['values']['note'] is None
    assert data['history_state'] == 'IMPORTED_CORRECTED'
    assert [c['id'] for c in data['corrections']] == [second, first]
    assert data['corrections'][0]['predecessor_id'] == first
    assert [c['correction_reason'] for c in data['corrections']] == ['reason 2', 'reason 1']
    assert all(c['audit_event_no'] for c in data['corrections']) and data['correction_count'] == 2
    assert stored(ctx) == before
    for forbidden in ('actor_name', 'actor_principal_id', 'request_json', str(ctx['actor_id']), 'Synthetic operator'):
        assert forbidden not in response.text
    model, _, _, _, number = models(kind)
    with Session(ctx['engine']) as db:
        child = db.scalar(select(model).where(getattr(model, number) == ctx['children']['owned'][kind]))
        eff = (effective_changeover if kind == 'changeover' else effective_batch)(db, child)
        assert eff.note == data['effective']['values']['note']
        assert eff.history_state == data['history_state']
        assert eff.correction_count == data['correction_count']


@pytest.mark.parametrize('kind', ['changeover', 'batch'])
def test_large_ledger_bounds_rows_queries_and_excludes_identity(correction_context, kind):
    ctx = correction_context; predecessor = append(ctx, kind)
    model, base, corr, target, number = models(kind)
    with Session(ctx['engine']) as db:
        child = db.scalar(select(model).where(getattr(model, number) == ctx['children']['owned'][kind]))
        baseline = db.scalar(select(base).where(getattr(base, target) == child.id))
        for revision in range(2, 57):
            key = uuid.uuid4()
            values = {'from_release_id': ctx['source_id'], 'changed_at': datetime(2026, 2, 1, tzinfo=timezone.utc)} if kind == 'changeover' else {'started_at': datetime(2026, 2, 1, tzinfo=timezone.utc)}
            db.add(corr(id=key, **{target: child.id}, baseline_id=baseline.id,
                predecessor_id=uuid.UUID(str(predecessor)), revision=revision, **values,
                note=f'item {revision}', correction_reason=f'reason {revision}', actor_name='PRIVATE ACTOR',
                actor_principal_id=ctx['actor_id'], request_json={'secret': 'PRIVATE REQUEST'},
                audit_event_no=f'HISTORY-{kind}-{revision}'))
            db.flush(); predecessor = key
        db.commit()
    statements = []
    def record(_conn, _cursor, statement, _params, _context, _many): statements.append(statement)
    event.listen(ctx['engine'], 'before_cursor_execute', record)
    try: response = ctx['client'].get(url(ctx, kind))
    finally: event.remove(ctx['engine'], 'before_cursor_execute', record)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['correction_count'] == 56 and data['truncated'] is True
    assert len(data['corrections']) == 50
    assert [c['revision'] for c in data['corrections']] == list(range(56, 6, -1))
    assert data['effective']['revision'] == 56 and data['effective']['head_id'] == str(predecessor)
    assert data['effective']['values'] == data['corrections'][0]['values']
    assert len(statements) <= 4
    assert 'count(' in statements[0].lower() and 'over (' in statements[0].lower()
    assert all('request_json' not in sql and 'actor_principal_id' not in sql and 'actor_name' not in sql for sql in statements)
    assert 'PRIVATE ACTOR' not in response.text and 'PRIVATE REQUEST' not in response.text


@pytest.mark.parametrize('kind', ['changeover', 'batch'])
def test_sample_get_read_only_mode_without_identity(correction_context, kind, monkeypatch):
    from app.main import app
    ctx = correction_context
    monkeypatch.setattr(settings, 'read_only_mode', True)
    monkeypatch.setattr(settings, 'auth_mode', 'disabled')
    def read_db():
        with Session(ctx['engine']) as db: yield db
    prior = dict(app.dependency_overrides); app.dependency_overrides[get_db] = read_db
    before = stored(ctx)
    try:
        with TestClient(app) as client:
            response = client.get(url(ctx, kind))
            assert response.status_code == 200, response.text
            assert client.post(url(ctx, kind).removesuffix('/history')+'/correction', json={}).status_code == 403
    finally:
        app.dependency_overrides.clear(); app.dependency_overrides.update(prior)
    assert stored(ctx) == before


@pytest.mark.parametrize('kind', ['changeover', 'batch'])
@pytest.mark.parametrize('source,state', [('LEGACY_CURRENT','LEGACY'), ('IMPORTED_CURRENT','IMPORTED'), ('FIRST_RECORD','FIRST_RECORD')])
def test_uncorrected_baseline_source_is_preserved(correction_context, kind, source, state):
    ctx = correction_context
    model, base, _, target, number = models(kind)
    with Session(ctx['engine']) as db:
        child = db.scalar(select(model).where(getattr(model, number) == ctx['children']['owned'][kind]))
        fields = ({'from_release_id': child.from_release_id, 'to_release_id': child.to_release_id,
                   'recorded_changed_at': child.changed_at} if kind == 'changeover' else
                  {'release_id': child.release_id, 'snapshot_id': child.snapshot_id,
                   'changeover_id': child.changeover_id, 'recorded_started_at': child.started_at,
                   'recorded_ended_at': child.ended_at})
        db.add(base(**{target: child.id}, **fields, recorded_status=child.status,
                    recorded_note='original record', source=source)); db.commit()
    before = stored(ctx)
    data = ctx['client'].get(url(ctx, kind)).json()
    assert data['recorded_baseline']['source'] == source and data['history_state'] == state
    assert data['effective']['values'] == data['recorded_baseline']['values']
    assert data['effective']['revision'] == 0 and data['effective']['head_id'] is None
    assert data['correction_count'] == 0 and data['corrections'] == []
    assert stored(ctx) == before


@pytest.mark.parametrize('correction_context', ['postgres'], indirect=True)
@pytest.mark.parametrize('kind', ['changeover', 'batch'])
def test_concurrent_append_after_projection_does_not_mix_head_context(correction_context, kind):
    from app.services.production import ProductionService
    ctx = correction_context; first = append(ctx, kind); second = uuid.uuid4()
    appended = False
    def append_during_metadata(_conn, _cursor, statement, _params, _context, _many):
        nonlocal appended
        if appended or not statement.startswith('SELECT releases.id, releases.version'):
            return
        appended = True
        with Session(ctx['engine']) as other:
            kwargs = dict(request_id=second, expected_revision=1, predecessor_id=uuid.UUID(first),
                          correction_reason='concurrent append', note='newer context')
            if kind == 'changeover': kwargs['from_release_id'] = ctx['source_id']
            getattr(ProductionService(other), 'correct_'+kind)(ctx['children']['owned'][kind], **kwargs)
    event.listen(ctx['engine'], 'before_cursor_execute', append_during_metadata)
    try: response = ctx['client'].get(url(ctx, kind))
    finally: event.remove(ctx['engine'], 'before_cursor_execute', append_during_metadata)
    assert appended and response.status_code == 200, response.text
    data = response.json()
    assert data['effective']['head_id'] == first and data['effective']['revision'] == 1
    assert data['correction_count'] == 1 and len(data['corrections']) == 1
    assert data['effective']['values'] == data['corrections'][0]['values']
    fresh = ctx['client'].get(url(ctx, kind)).json()
    assert fresh['effective']['head_id'] == str(second) and fresh['correction_count'] == 2
