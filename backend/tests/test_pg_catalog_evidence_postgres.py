"""Real PG16 evidence only on the existing GitHub CI-owned disposable database.

No import-time I/O. No local fallback, external DSN, role/permission changes,
Docker calls, seed, stamp or create_all. Each case owns one random schema.
"""
import ast
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
sys.path.insert(0, str(ROOT / 'scripts'))
import offline_pg_guard_contracts as guards
spec = importlib.util.spec_from_file_location('pg_catalog_evidence', ROOT / 'scripts/offline_pg_catalog_evidence.py')
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


def reject_pg_environment():
    # libpq PGHOSTADDR can override the routing implied by host=127.0.0.1.
    # Reject even empty overrides rather than silently clearing a user's config.
    if any(key.startswith('PG') for key in os.environ):
        raise RuntimeError('PG environment overrides are not allowed in catalog CI fixtures')


def ci_url():
    reject_pg_environment()
    if (os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('CI') != 'true'
            or os.environ.get('GITHUB_REPOSITORY') != 'Wang106/SoftwareLifeCycle'):
        raise RuntimeError('PG catalog tests require the authorized repository GitHub CI')
    raw = os.environ.get('TEST_POSTGRES_URL', '')
    try:
        url = make_url(raw)
        if (url.drivername != 'postgresql+psycopg' or url.host != '127.0.0.1'
                or url.port != 5432 or url.database != 'software_lifecycle_ci'
                or url.username != 'slc_ci' or not url.password or url.query):
            raise ValueError()
    except Exception:
        raise RuntimeError('PG catalog tests require the fixed loopback CI target') from None
    return url


@pytest.fixture
def owned_catalog_schema():
    url = ci_url()  # Guard before any connection or migration import.
    namespace = 'ci_catalog_' + uuid.uuid4().hex
    kwargs = dict(host=url.host, port=url.port, dbname=url.database,
                  user=url.username, password=url.password, connect_timeout=5,
                  options='-cstatement_timeout=5000 -clock_timeout=1000 -cidle_in_transaction_session_timeout=15000')
    created = False
    oid = None
    reject_pg_environment()
    with psycopg.connect(**kwargs, autocommit=True) as admin:
        if not 160000 <= admin.info.server_version < 170000:
            raise RuntimeError('PG catalog tests require PG16')
        try:
            admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(namespace)))
            created = True
            oid = admin.execute('SELECT oid FROM pg_catalog.pg_namespace WHERE nspname=%s', (namespace,)).fetchone()[0]
            scoped = url.update_query_dict({'options': f'-csearch_path={namespace} -cstatement_timeout=10000 -clock_timeout=1000'})
            env = {k: v for k, v in os.environ.items() if not k.startswith('PG')}
            env.update(DATABASE_URL=scoped.render_as_string(hide_password=False), AUTH_MODE='disabled',
                       SEED_ON_STARTUP='false', READ_ONLY_MODE='false')
            # Actual existing chain, no shell, explicit fixed cwd and finite subprocess.
            result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', '0029_changeover_batch_history'],
                                    cwd=BACKEND, env=env, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=90, check=False)
            if result.returncode != 0:
                raise RuntimeError('Isolated catalog fixture migration failed')
            actual = admin.execute(sql.SQL('SELECT version_num FROM {}.alembic_version').format(sql.Identifier(namespace))).fetchall()
            assert actual == [('0029_changeover_batch_history',)]
            yield admin, kwargs, namespace
        finally:
            if created:
                # Exact same namespace OID and current ownership, never search by prefix.
                found = admin.execute('SELECT oid, nspowner = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user) FROM pg_catalog.pg_namespace WHERE nspname=%s', (namespace,)).fetchone()
                if found != (oid, True):
                    raise RuntimeError('Owned catalog fixture identity changed; cleanup stopped')
                admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(namespace)))


def observe(kwargs, namespace):
    reject_pg_environment()
    with psycopg.connect(**kwargs, autocommit=True) as connection:
        connection.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        try:
            connection.execute('SET LOCAL search_path=pg_catalog')
            result = catalog.collect(connection, namespace)
        finally:
            connection.rollback()
        return result


def rows(report, group):
    return report['observations'][group]


def test_actual_chain_catalog_and_exact_function_body_mapping(owned_catalog_schema):
    admin, kwargs, namespace = owned_catalog_schema
    report = observe(kwargs, namespace)
    assert report['namespace'] == namespace and namespace != 'public'
    assert report['database_verified'] is False
    assert len(rows(report, 'tables')) == 7
    assert len(rows(report, 'functions')) == 3
    assert len(rows(report, 'triggers')) == 6
    assert all(r['namespace'] == namespace for group in report['observations'].values() for r in group)
    # Compare real prosrc hash against exact source literal, no SQL execution here.
    source = ast.parse((BACKEND / 'alembic/versions/0029_changeover_batch_history.py').read_text())
    bodies = {}
    for node in ast.walk(source):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'execute' and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            value = node.args[0].value
            for name in catalog.FUNCTIONS:
                marker = 'CREATE FUNCTION ' + name + '()'
                if marker in value:
                    bodies[name] = value.split(marker, 1)[1].split('$$', 2)[1]
    for row in rows(report, 'functions'):
        assert row['body_sha256'] == hashlib.sha256(bodies[row['name']].encode()).hexdigest()
    predecessor = next(r for r in rows(report, 'constraints') if r['name'] == 'fk_changeover_corr_predecessor')
    assert predecessor['columns'] == ['changeover_id', 'predecessor_id']
    assert predecessor['reference_columns'] == ['changeover_id', 'id']
    assert predecessor['reference_namespace'] == namespace
    partial = next(r for r in rows(report, 'indexes') if r['name'] == 'ux_changeover_corr_single_successor')
    assert partial['unique'] and partial['predicate'] == '(predecessor_id IS NOT NULL)'
    assert all(r['type_bits'] == 27 and r['enabled'] == 'O' for r in rows(report, 'triggers'))
    assert all(r['argument_count'] == r['argument_bytes'] == 0 and r['has_when'] is False
               for r in rows(report, 'triggers'))
    checked = guards.check_observation(report, namespace)
    assert checked['status'] == 'GUARD_CONTRACT_MATCHED'
    assert len(checked['checks']) == 9 and checked['complete_schema_verified'] is False
    check = next(r for r in rows(report, 'constraints') if r['name'] == 'ck_changeover_corr_revision_positive')
    assert check['definition'] == 'CHECK ((revision >= 1))'


def test_disabled_trigger_observed_not_invented_enabled(owned_catalog_schema):
    admin, kwargs, namespace = owned_catalog_schema
    admin.execute(sql.SQL('ALTER TABLE {}.batch_baselines DISABLE TRIGGER batch_baselines_append_only').format(sql.Identifier(namespace)))
    report = observe(kwargs, namespace)
    assert next(r for r in rows(report, 'triggers') if r['name'] == 'batch_baselines_append_only')['enabled'] == 'D'
    assert guards.check_observation(report, namespace)['status'] == 'GUARD_CONTRACT_MISMATCH'
    # Same fixture and original guard name: structured evidence, no deparse edits.
    for suffix, expected_when, expected_count in [
            ("WHEN (OLD.id IS NOT NULL) EXECUTE FUNCTION {}.reject_changeover_batch_history_mutation()", True, 0),
            ("EXECUTE FUNCTION {}.reject_changeover_batch_history_mutation('synthetic')", False, 1)]:
        admin.execute(sql.SQL('DROP TRIGGER batch_baselines_append_only ON {}.batch_baselines').format(sql.Identifier(namespace)))
        statement = ('CREATE TRIGGER batch_baselines_append_only BEFORE DELETE OR UPDATE ON {}.batch_baselines '
                     'FOR EACH ROW ' + suffix)
        admin.execute(sql.SQL(statement).format(sql.Identifier(namespace), sql.Identifier(namespace)))
        report = observe(kwargs, namespace)
        row = next(r for r in rows(report, 'triggers') if r['name'] == 'batch_baselines_append_only')
        assert row['has_when'] is expected_when and row['argument_count'] == expected_count
        assert (row['argument_bytes'] > 0) is (expected_count > 0)
        assert guards.check_observation(report, namespace)['status'] == 'GUARD_CONTRACT_MISMATCH'


def test_function_body_mutation_is_observed(owned_catalog_schema):
    admin, kwargs, namespace = owned_catalog_schema
    before = observe(kwargs, namespace)
    admin.execute(sql.SQL('CREATE OR REPLACE FUNCTION {}.reject_changeover_batch_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$').format(sql.Identifier(namespace)))
    after = observe(kwargs, namespace)
    name = 'reject_changeover_batch_history_mutation'
    assert next(r for r in rows(before, 'functions') if r['name'] == name)['body_sha256'] != next(r for r in rows(after, 'functions') if r['name'] == name)['body_sha256']
    assert guards.check_observation(before, namespace)['status'] == 'GUARD_CONTRACT_MATCHED'
    assert guards.check_observation(after, namespace)['status'] == 'GUARD_CONTRACT_MISMATCH'


def test_changed_column_and_missing_table_are_observed(owned_catalog_schema):
    admin, kwargs, namespace = owned_catalog_schema
    admin.execute(sql.SQL('ALTER TABLE {}.batch_baselines ALTER COLUMN recorded_status TYPE varchar(31)').format(sql.Identifier(namespace)))
    report = observe(kwargs, namespace)
    assert next(r for r in rows(report, 'columns') if r['table'] == 'batch_baselines' and r['name'] == 'recorded_status')['type'] == 'character varying(31)'
    # No cascade outside the fixture; this empty leaf has no inbound dependencies.
    admin.execute(sql.SQL('DROP TABLE {}.batch_corrections').format(sql.Identifier(namespace)))
    report = observe(kwargs, namespace)
    assert 'batch_corrections' not in {r['name'] for r in rows(report, 'tables')}


def test_partial_index_unique_change_is_observed(owned_catalog_schema):
    admin, kwargs, namespace = owned_catalog_schema
    admin.execute(sql.SQL('DROP INDEX {}.ux_changeover_corr_single_successor').format(sql.Identifier(namespace)))
    admin.execute(sql.SQL('CREATE INDEX ux_changeover_corr_single_successor ON {}.changeover_corrections(predecessor_id) WHERE predecessor_id IS NOT NULL').format(sql.Identifier(namespace)))
    report = observe(kwargs, namespace)
    item = next(r for r in rows(report, 'indexes') if r['name'] == 'ux_changeover_corr_single_successor')
    assert item['unique'] is False and item['predicate'] == '(predecessor_id IS NOT NULL)'


def test_same_names_other_namespace_do_not_satisfy_missing_objects(owned_catalog_schema):
    admin, kwargs, namespace = owned_catalog_schema
    # Existing public test schemas are neither read nor changed. A missing exact
    # namespace is rejected before any observations can be substituted.
    with pytest.raises(catalog.CatalogError):
        observe(kwargs, namespace + '_missing')


def test_wrong_transaction_is_rejected(owned_catalog_schema):
    admin, kwargs, namespace = owned_catalog_schema
    reject_pg_environment()
    with psycopg.connect(**kwargs, autocommit=True) as connection:
        connection.execute('BEGIN READ WRITE')
        try:
            with pytest.raises(catalog.CatalogError):
                catalog.collect(connection, namespace)
        finally:
            connection.rollback()


def test_idle_autocommit_defaults_are_not_an_active_snapshot(owned_catalog_schema):
    admin, kwargs, namespace = owned_catalog_schema
    reject_pg_environment()
    with psycopg.connect(**kwargs, autocommit=True) as connection:
        connection.execute('SET default_transaction_read_only=on')
        connection.execute("SET default_transaction_isolation='repeatable read'")
        connection.execute('SET search_path=pg_catalog')
        with pytest.raises(catalog.CatalogError):
            catalog.collect(connection, namespace)
