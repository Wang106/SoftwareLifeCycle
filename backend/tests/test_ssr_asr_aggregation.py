"""Aggregated ASR component differences and unlinked-base blocks for one baseline SSR."""
import uuid
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_impact_assessments import context
from test_command_concurrency_postgres import pg
from app.api.standard_release_views import aggregated_differences, standard_release
from app.core.db import get_db
from app.main import app
from app.models.audit import AuditEvent
from app.models.core import (
    ApplicationReleaseDetail, ComponentDefinition, Customer, Project, Release,
    ReleaseComponent, SoftwareProduct, StandardReleaseDetail,
)


def add_component(db, release, code=None, name=None):
    definition = ComponentDefinition(code=code or f'D-{uuid.uuid4().hex[:10]}', name=name or 'Controller')
    db.add(definition); db.flush()
    component = ReleaseComponent(release_id=release.id, component_definition_id=definition.id, version='1.0')
    db.add(component); db.flush()
    return definition, component


def add_asr(db, base, version='app', customer_id=None, project_id=None):
    product = db.get(SoftwareProduct, base.software_id)
    asr = Release(software_id=product.id, release_type='APPLICATION', version=version, status='DRAFT')
    db.add(asr); db.flush()
    db.add(ApplicationReleaseDetail(release_id=asr.id, customer_id=customer_id or uuid.uuid4(),
        project_id=project_id or uuid.uuid4(), standard_base_release_id=base.id))
    return asr


@pytest.fixture
def standard(context):
    db, _, base, *_ = context
    db.add(StandardReleaseDetail(release_id=base.id, git_branch='main', git_commit='raw'))
    db.commit()
    return db, base


def test_empty_baseline_zero_derived(standard):
    db, base = standard
    result = aggregated_differences(base.id, db)
    assert result['release']['id'] == str(base.id) and result['derived_application_count'] == 0
    assert result['delta_type_aggregate']['asr_declaration_count'] == 0
    assert all(v == 0 for bucket in result['delta_type_aggregate']['by_delta_type'].values() for v in bucket.values())
    assert result['unlinked_base_aggregate']['baseline_component_count'] == 0
    assert result['unlinked_base_aggregate']['blocked_component_count'] == 0
    assert result['unlinked_base_aggregate']['blocks'] == []


def test_delta_type_distribution_and_link_status(standard):
    db, base = standard
    definition, base_component = add_component(db, base)
    other_def, other_base = add_component(db, base)
    asr = add_asr(db, base)
    # VALID: unchanged + linked to base_component; INVALID: modified + wrong link;
    # NOT_RECORDED: added with no base pointer; REMOVED: with no base pointer.
    rows = [
        ReleaseComponent(release_id=asr.id, component_definition_id=definition.id,
            base_component_id=base_component.id, delta_type='UNCHANGED', version='1.0'),
        ReleaseComponent(release_id=asr.id, component_definition_id=definition.id,
            base_component_id=other_base.id, delta_type='MODIFIED', version='1.1'),
        ReleaseComponent(release_id=asr.id, component_definition_id=other_def.id,
            base_component_id=None, delta_type='ADDED', version='2.0'),
        ReleaseComponent(release_id=asr.id, component_definition_id=other_def.id,
            base_component_id=None, delta_type='REMOVED', version=None),
    ]
    db.add_all(rows); db.commit()
    result = aggregated_differences(base.id, db)
    assert result['derived_application_count'] == 1
    agg = result['delta_type_aggregate']
    assert agg['asr_declaration_count'] == 4
    by = agg['by_delta_type']
    assert by['UNCHANGED'] == {'VALID': 1, 'INVALID': 0, 'NOT_RECORDED': 0}
    assert by['MODIFIED'] == {'VALID': 0, 'INVALID': 1, 'NOT_RECORDED': 0}
    assert by['ADDED'] == {'VALID': 0, 'INVALID': 0, 'NOT_RECORDED': 1}
    assert by['REMOVED'] == {'VALID': 0, 'INVALID': 0, 'NOT_RECORDED': 1}


def test_unlinked_base_blocks_across_asrs(standard):
    db, base = standard
    definition_a, comp_a = add_component(db, base)
    definition_b, comp_b = add_component(db, base)
    # ASR-1 links A only; ASR-2 links neither; ASR-3 links both. Thus A is blocked
    # by ASR-2 (unlinked_application_count=1), B is blocked by ASR-1 and ASR-2 (2).
    for version, linked in [('app-1', [comp_a]), ('app-2', []), ('app-3', [comp_a, comp_b])]:
        asr = add_asr(db, base, version=version)
        for comp in linked:
            db.add(ReleaseComponent(release_id=asr.id, component_definition_id=comp.component_definition_id,
                base_component_id=comp.id, delta_type='UNCHANGED', version='1.0'))
    db.commit()
    result = aggregated_differences(base.id, db)
    assert result['derived_application_count'] == 3
    unlinked = result['unlinked_base_aggregate']
    assert unlinked['baseline_component_count'] == 2
    assert unlinked['blocked_component_count'] == 2
    by_code = {b['component_code']: b['unlinked_application_count'] for b in unlinked['blocks']}
    assert by_code[definition_a.code] == 1
    assert by_code[definition_b.code] == 2


def test_sibling_and_foreign_asrs_do_not_leak(standard):
    db, base = standard
    definition, comp = add_component(db, base)
    asr = add_asr(db, base, version='mine')
    db.add(ReleaseComponent(release_id=asr.id, component_definition_id=definition.id,
        base_component_id=comp.id, delta_type='UNCHANGED', version='1.0'))
    # A foreign ASR on a different baseline SSR must not be counted.
    other_base = Release(software_id=base.software_id, release_type='STANDARD', version='other-base')
    db.add(other_base); db.flush()
    db.add(StandardReleaseDetail(release_id=other_base.id))
    foreign = add_asr(db, other_base, version='foreign')
    db.add(ReleaseComponent(release_id=foreign.id, component_definition_id=definition.id,
        base_component_id=None, delta_type='ADDED', version='9.9'))
    db.commit()
    result = aggregated_differences(base.id, db)
    assert result['derived_application_count'] == 1
    assert result['delta_type_aggregate']['asr_declaration_count'] == 1
    assert result['unlinked_base_aggregate']['blocked_component_count'] == 0


def test_exact_standard_parent_404(standard):
    db, base = standard
    with pytest.raises(HTTPException) as error:
        aggregated_differences(uuid.uuid4(), db)
    assert error.value.status_code == 404
    base.release_type = 'APPLICATION'; db.commit()
    with pytest.raises(HTTPException) as error:
        aggregated_differences(base.id, db)
    assert error.value.status_code == 404


def test_readonly_no_audit_write(standard):
    db, base = standard
    add_component(db, base)
    asr = add_asr(db, base)
    db.commit()
    before = db.scalar(select(func.count()).select_from(AuditEvent))
    aggregated_differences(base.id, db)
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == before


def test_growth_fixed_queries(standard):
    db, base = standard
    definition, comp = add_component(db, base)
    asr = add_asr(db, base, version='seed-app')
    db.add(ReleaseComponent(release_id=asr.id, component_definition_id=definition.id,
        base_component_id=comp.id, delta_type='UNCHANGED', version='1.0'))
    db.commit()
    rid = base.id
    calls = []
    def capture(_conn, _cursor, statement, *_):
        calls.append(statement.lower())
    def read():
        db.expunge_all()
        calls.clear()
        event.listen(db.bind, 'before_cursor_execute', capture)
        try:
            aggregated_differences(rid, db)
        finally:
            event.remove(db.bind, 'before_cursor_execute', capture)
        return list(calls)
    small = read()
    for n in range(120):
        add_asr(db, base, version=f'grow-{n}')
    db.commit()
    grown = read()
    assert len(small) == len(grown)


def test_http_readonly_and_validation(standard, monkeypatch):
    from app import main
    db, base = standard
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    with engine.connect() as c:
        db.connection().connection.driver_connection.backup(c.connection.driver_connection)
    route_db = Session(engine)
    app.dependency_overrides[get_db] = lambda: route_db
    monkeypatch.setattr(main.settings, 'read_only_mode', True)
    try:
        with TestClient(app) as client:
            url = f'/api/v1/releases/standard/id/{base.id}/aggregated-differences'
            response = client.get(url)
            assert response.status_code == 200
            assert response.json()['derived_application_count'] == 0
            assert client.get('/api/v1/releases/standard/id/bad/aggregated-differences').status_code == 422
            assert client.post(f'/api/v1/releases/{base.id}/create-snapshot', json={}).status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)
        route_db.close()
        engine.dispose()


def test_real_migrated_postgresql_no_audit_write(pg):
    engine, ids = pg
    with Session(engine) as db:
        base = db.get(Release, ids['release'])
        customer = db.scalar(select(Customer.id)); project = db.scalar(select(Project.id))
        definition, comp = add_component(db, base)
        asr = add_asr(db, base, version='pg-app', customer_id=customer, project_id=project)
        db.add(ReleaseComponent(release_id=asr.id, component_definition_id=definition.id,
            base_component_id=comp.id, delta_type='MODIFIED', version='1.2'))
        db.commit()
        before = db.scalar(select(func.count()).select_from(AuditEvent))
        result = aggregated_differences(base.id, db)
        assert result['derived_application_count'] >= 1
        assert result['delta_type_aggregate']['by_delta_type']['MODIFIED']['VALID'] >= 1
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == before
