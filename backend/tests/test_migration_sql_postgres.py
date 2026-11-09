"""Generated SQL execution only in newly owned namespaces on the CI PG16 service."""
import json
import os
import subprocess
import sys
import uuid

import psycopg
from psycopg import sql
import pytest

from test_pg_catalog_evidence_postgres import ci_url, reject_pg_environment, observe
from test_migration_sql_generation import generate_sql, MAX_SQL, HEAD

EXECUTE = '''import json, sys
import psycopg
from psycopg.pq import TransactionStatus
kwargs = json.loads(sys.stdin.buffer.readline(8192))
body = sys.stdin.buffer.read(1048577)
if not body or len(body) > 1048576: raise SystemExit(2)
try:
    with psycopg.connect(**kwargs, autocommit=True) as connection:
        connection.execute(body.decode('utf-8'), prepare=False)
        if connection.info.transaction_status != TransactionStatus.IDLE: raise SystemExit(3)
except psycopg.errors.StringDataRightTruncation:
    raise SystemExit(32)
'''


def execute_generated(kwargs, body):
    reject_pg_environment()
    assert 0 < len(body.encode()) <= MAX_SQL
    # Fixed trusted driver child, no shell. No credentials/SQL in logs or files.
    # Timeout kills/waits this child; server/cleanup uncertainty still fails.
    result = subprocess.run([sys.executable, '-I', '-c', EXECUTE],
                            input=(json.dumps(kwargs) + '\n' + body).encode(),
                            env={'LANG':'C.UTF-8'}, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=90, check=False)
    return result.returncode


@pytest.fixture
def empty_sql_schema():
    url = ci_url()  # Existing exact repository/CI/loopback/user and PG* guards.
    if sys.platform != 'linux': raise RuntimeError('SQL fixture requires CI Linux')
    namespace = 'ci_sql_' + uuid.uuid4().hex
    kwargs = dict(host=url.host, port=url.port, dbname=url.database, user=url.username,
                  password=url.password, connect_timeout=5,
                  options='-cstatement_timeout=5000 -clock_timeout=1000 -cidle_in_transaction_session_timeout=15000')
    created = False; oid = None
    reject_pg_environment()
    with psycopg.connect(**kwargs, autocommit=True) as admin:
        if not 160000 <= admin.info.server_version < 170000: raise RuntimeError('SQL fixture requires PG16')
        try:
            admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(namespace)))
            created = True
            oid = admin.execute('SELECT oid FROM pg_catalog.pg_namespace WHERE nspname=%s', (namespace,)).fetchone()[0]
            scoped = dict(kwargs, options=kwargs['options'] + f' -csearch_path={namespace}')
            yield admin, kwargs, scoped, namespace, oid
        finally:
            if created:
                found = admin.execute('SELECT oid, nspowner=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user) FROM pg_catalog.pg_namespace WHERE nspname=%s', (namespace,)).fetchone()
                if found != (oid, True): raise RuntimeError('Owned SQL schema identity changed; cleanup stopped')
                admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(namespace)))


def test_generated_sql_executes_original_chain_on_empty_schema(empty_sql_schema):
    admin, kwargs, scoped, namespace, oid = empty_sql_schema
    assert admin.execute('SELECT count(*) FROM pg_catalog.pg_class WHERE relnamespace=%s', (oid,)).fetchone()[0] == 0
    assert execute_generated(scoped, generate_sql()) == 0
    assert admin.execute(sql.SQL('SELECT version_num FROM {}.alembic_version').format(sql.Identifier(namespace))).fetchall() == [(HEAD,)]
    actual = admin.execute('SELECT data_type,character_maximum_length,is_nullable FROM information_schema.columns WHERE table_schema=%s AND table_name=%s AND column_name=%s', (namespace,'alembic_version','version_num')).fetchone()
    assert actual == ('character varying',64,'NO')
    report = observe(kwargs, namespace)
    assert len(report['observations']['tables']) == 7
    assert len(report['observations']['functions']) == 3
    assert len(report['observations']['triggers']) == 6
    assert report['database_verified'] is False  # Finite synthetic observation only.


def test_test_only_32_width_mutant_rejected_without_committed_tables(empty_sql_schema):
    admin, _kwargs, scoped, _namespace, oid = empty_sql_schema
    statement = generate_sql()
    marker = 'version_num VARCHAR(64) NOT NULL'
    assert statement.count(marker) == 1
    # Deliberate test-only negative: production generation never rewrites SQL.
    mutant = statement.replace(marker, 'version_num VARCHAR(32) NOT NULL', 1)
    assert execute_generated(scoped, mutant) == 32
    assert admin.execute('SELECT count(*) FROM pg_catalog.pg_class WHERE relnamespace=%s', (oid,)).fetchone()[0] == 0
