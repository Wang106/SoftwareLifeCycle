"""Real migration constraints, only inside the existing guarded disposable CI schema."""
import json
import uuid

import psycopg
from psycopg import sql
import pytest

from test_pg_catalog_evidence_postgres import owned_catalog_schema  # noqa: F401


def test_migrated_upload_constraints_and_foreign_keys(owned_catalog_schema):
    connection, _kwargs, namespace = owned_catalog_schema
    table = sql.Identifier(namespace, 'private_upload_sessions')
    # Inspect the actual migration table, retaining both restrictive references.
    references = connection.execute('''SELECT con.confrelid::regclass::text
        FROM pg_catalog.pg_constraint con JOIN pg_catalog.pg_class cls ON cls.oid=con.conrelid
        JOIN pg_catalog.pg_namespace ns ON ns.oid=cls.relnamespace
        WHERE ns.nspname=%s AND cls.relname='private_upload_sessions' AND con.contype='f'
        ORDER BY con.confrelid::regclass::text''', (namespace,)).fetchall()
    assert {row[0].rsplit('.', 1)[-1] for row in references} == {'security_principals', 'release_components'}
    # Clone actual migrated checks/indexes into a session-owned temporary table.
    # LIKE does not clone FKs, so the checks can use entirely synthetic UUIDs.
    connection.execute(sql.SQL('CREATE TEMP TABLE upload_constraint_probe (LIKE {} INCLUDING ALL)').format(table))
    try:
        fields = ('id', 'object_id', 'storage_scope_id', 'actor_principal_id', 'release_component_id',
                  'expected_bytes', 'sha256', 'state', 'revision', 'request_json', 'context_json',
                  'reservation_receipt_json', 'stored_receipt_json', 'created_at', 'updated_at')
        base = dict(zip(fields, (uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(),
            0, 'a'*64, 'RESERVED', 0, '{}', '{}', '{}', None,
            '2026-11-14T00:00:00Z', '2026-11-14T00:00:00Z')))
        query = sql.SQL('INSERT INTO upload_constraint_probe ({}) VALUES ({})').format(
            sql.SQL(',').join(map(sql.Identifier, fields)), sql.SQL(',').join(sql.Placeholder() for _ in fields))
        for mutation in ({'expected_bytes':-1}, {'revision':-1}, {'sha256':'short'}, {'state':'READY'},
                         {'state':'STORED_PRIVATE'}, {'stored_receipt_json':'{}'},
                         {'state':'STORED_PRIVATE','stored_receipt_json':'null'},
                         {'request_json':'null'}, {'context_json':None}, {'reservation_receipt_json':'null'},
                         {'storage_scope_id':None}, {'actor_principal_id':None}, {'release_component_id':None}):
            row = dict(base, **mutation)
            with pytest.raises(psycopg.IntegrityError):
                connection.execute(query, tuple(row[key] for key in fields))
        for state in ('RESERVED','RECEIVING','STAGED','PUBLISHING','RECONCILIATION_REQUIRED','STORED_PRIVATE'):
            row = dict(base, id=uuid.uuid4(), object_id=uuid.uuid4(), state=state,
                       stored_receipt_json=json.dumps({'synthetic':True}) if state=='STORED_PRIVATE' else None)
            connection.execute(query, tuple(row[key] for key in fields))
            with pytest.raises(psycopg.errors.UniqueViolation):
                connection.execute(query, tuple(dict(row,id=uuid.uuid4())[key] for key in fields))
        assert connection.execute('SELECT count(*) FROM upload_constraint_probe').fetchone() == (6,)
    finally:
        connection.execute('DROP TABLE upload_constraint_probe')
