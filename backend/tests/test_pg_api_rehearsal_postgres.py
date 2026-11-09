"""Actual HTTP/PG integration only on the existing isolated GitHub CI target.

No import-time I/O. API connects to one new synthetic namespace only; no company
DB, real identity, permission changes, startup migration/seed or container use.
"""
import importlib.util
from pathlib import Path
import uuid

from psycopg import sql
from test_pg_catalog_evidence_postgres import owned_catalog_schema, ci_url, observe

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('pg_api_rehearsal', ROOT / 'scripts/offline_pg_api_rehearsal.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def selected_rows(admin, namespace):
    return {name: admin.execute(sql.SQL('SELECT count(*) FROM {}.{}').format(
        sql.Identifier(namespace), sql.Identifier(name))).fetchone()[0]
        for name in ('releases', 'release_snapshots', 'audit_events', 'deployments')}


def test_real_readonly_api_ready_catalogs_and_denied_writes(owned_catalog_schema):
    admin, kwargs, namespace = owned_catalog_schema
    base = ci_url().render_as_string(hide_password=False)
    before_catalog = observe(kwargs, namespace)
    before_rows = selected_rows(admin, namespace)
    assert all(count == 0 for count in before_rows.values())
    with api.APIProcess(base, namespace) as process:
        status, body = process.request('GET', '/health/ready')
        ready = api.json_body(body)
        assert status == 200 and ready == {'status': 'ready', 'version': '0.18.50',
                                         'database_revision': '0029_changeover_batch_history'}
        for path in ('/api/v1/release-catalog/application?limit=1', '/api/v1/audit/events?limit=1'):
            status, body = process.request('GET', path)
            catalog = api.json_body(body)
            assert status == 200 and catalog['total'] == 0 and catalog['items'] == []
            assert catalog['limit'] == 1 and catalog['next_offset'] is None
        status, body = process.request('POST', '/api/v1/deployments')
        assert status == 403 and api.json_body(body) == {'detail': 'read_only_mode'}
        status, body = process.request('GET', '/api/v1/security/me')
        assert status == 401 and api.json_body(body) == {'detail': 'oidc_not_enabled'}
    # Successful exit is checked by APIProcess before observations after startup.
    assert observe(kwargs, namespace) == before_catalog
    assert selected_rows(admin, namespace) == before_rows
    assert admin.execute(sql.SQL('SELECT version_num FROM {}.alembic_version').format(
        sql.Identifier(namespace))).fetchall() == [('0029_changeover_batch_history',)]


def test_empty_owned_schema_not_ready_and_no_startup_migration(owned_catalog_schema):
    admin, _kwargs, _migrated = owned_catalog_schema
    base = ci_url().render_as_string(hide_password=False)
    namespace = 'ci_api_' + uuid.uuid4().hex
    created = False
    oid = None
    try:
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(namespace)))
        created = True
        oid = admin.execute('SELECT oid FROM pg_catalog.pg_namespace WHERE nspname=%s', (namespace,)).fetchone()[0]
        with api.APIProcess(base, namespace) as process:
            status, body = process.request('GET', '/health/ready')
            assert status == 503 and api.json_body(body) == {'status': 'not_ready', 'reason': 'database_unavailable'}
            status, body = process.request('GET', '/api/v1/release-catalog/application?limit=1')
            assert status == 500 and body == b'Internal Server Error'
            status, body = process.request('POST', '/api/v1/deployments')
            assert status == 403 and api.json_body(body) == {'detail': 'read_only_mode'}
        # No version table or application table appeared in the empty namespace.
        assert admin.execute('SELECT count(*) FROM pg_catalog.pg_class WHERE relnamespace=%s', (oid,)).fetchone()[0] == 0
    finally:
        if created:
            found = admin.execute('SELECT oid, nspowner=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user) FROM pg_catalog.pg_namespace WHERE nspname=%s', (namespace,)).fetchone()
            if found != (oid, True):
                raise RuntimeError('Owned empty API schema identity changed; cleanup stopped')
            admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(namespace)))
