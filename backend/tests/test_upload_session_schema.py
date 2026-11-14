"""Private upload metadata and migration contracts; no external database or I/O."""
import importlib
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]
HEAD = '0030_private_upload_sessions'


def test_upload_session_is_the_single_additive_migration_head():
    config = Config(str(ROOT / 'backend/alembic.ini'))
    config.set_main_option('script_location', str(ROOT / 'backend/alembic'))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == [HEAD]
    assert scripts.get_revision(HEAD).down_revision == '0029_changeover_batch_history'
    assert len(list(scripts.walk_revisions())) == 30


def test_upload_metadata_is_private_and_registered():
    import app.models
    from app.core.db import Base
    model = importlib.import_module('app.models.upload').PrivateUploadSession
    table = model.__table__
    assert Base.metadata.tables['private_upload_sessions'] is table
    assert table.c.id.default is None
    assert table.c.object_id.default is None
    assert set(table.c.keys()) == {'id', 'object_id', 'storage_scope_id', 'actor_principal_id',
        'release_component_id', 'expected_bytes', 'sha256', 'state', 'revision',
        'request_json', 'context_json', 'reservation_receipt_json',
        'stored_receipt_json', 'created_at', 'updated_at'}
    assert {fk.target_fullname for fk in table.foreign_keys} == {
        'security_principals.id', 'release_components.id'}
    assert table.c.stored_receipt_json.type.none_as_null is True


def test_current_schema_pin_preserves_historical_manifest():
    import json
    from app.core.config import Settings
    assert Settings().required_db_revision == HEAD
    old = json.loads((ROOT / 'deploy/offline/migration-schema-0029.json').read_text())
    new = json.loads((ROOT / 'deploy/offline/migration-schema-0030.json').read_text())
    assert old['facts']['version']['head'] == '0029_changeover_batch_history'
    assert new['facts']['version']['head'] == HEAD
    for name, value in old['facts'].items():
        if name != 'version':
            assert new['facts'][name] == value


def test_model_and_migration_metadata_are_identical():
    from sqlalchemy import MetaData
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects import postgresql, sqlite
    from unittest.mock import patch
    from app.models.upload import PrivateUploadSession
    spec = importlib.util.spec_from_file_location('upload_migration', ROOT / 'backend/alembic/versions/0030_private_upload_sessions.py')
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    from sqlalchemy import Table
    tables = []
    metadata = PrivateUploadSession.metadata
    def create_table(name, *args):
        scratch = MetaData()
        for foreign in ('security_principals', 'release_components'):
            metadata.tables[foreign].to_metadata(scratch)
        tables.append(Table(name, scratch, *args))
    with patch.object(migration.op, 'create_table', side_effect=create_table), patch.object(migration.op, 'create_index') as index:
        migration.upgrade()
    index.assert_called_once_with('ix_private_upload_component_created', 'private_upload_sessions', ['release_component_id', 'created_at'])
    for dialect in (postgresql.dialect(), sqlite.dialect()):
        assert str(CreateTable(tables[0]).compile(dialect=dialect)) == str(CreateTable(PrivateUploadSession.__table__).compile(dialect=dialect))


def test_upload_database_constraints_on_synthetic_in_memory_sqlite():
    import uuid
    from datetime import datetime, timezone
    from sqlalchemy import create_engine, insert, JSON, text
    from sqlalchemy.exc import IntegrityError
    import pytest
    from app.models.upload import PrivateUploadSession
    table = PrivateUploadSession.__table__
    engine = create_engine('sqlite://')
    # Only this isolated metadata table is created; no application migration/server.
    table.create(engine)
    row = dict(id=uuid.uuid4(), object_id=uuid.uuid4(), storage_scope_id=uuid.uuid4(),
        actor_principal_id=uuid.uuid4(), release_component_id=uuid.uuid4(), expected_bytes=0,
        sha256='a'*64, state='RESERVED', revision=0, request_json={}, context_json={},
        reservation_receipt_json={}, stored_receipt_json=None,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    invalid = [dict(expected_bytes=-1), dict(revision=-1), dict(sha256='a'*63),
        dict(state='READY'), dict(state='STORED_PRIVATE'), dict(stored_receipt_json={}),
        dict(state='STORED_PRIVATE', stored_receipt_json=JSON.NULL),
        dict(stored_receipt_json=JSON.NULL), dict(request_json=JSON.NULL),
        dict(context_json=JSON.NULL), dict(reservation_receipt_json=JSON.NULL),
        dict(request_json=None), dict(context_json=None), dict(reservation_receipt_json=None),
        dict(storage_scope_id=None), dict(actor_principal_id=None), dict(release_component_id=None)]
    with engine.connect() as connection:
        for mutation in invalid:
            with pytest.raises(IntegrityError):
                connection.execute(insert(table).values(dict(row, **mutation)))
            connection.rollback()
        for state in ('RESERVED','RECEIVING','STAGED','PUBLISHING','RECONCILIATION_REQUIRED','STORED_PRIVATE'):
            connection.execute(insert(table).values(dict(row, state=state,
                stored_receipt_json={} if state=='STORED_PRIVATE' else None)))
            connection.rollback()
        connection.execute(insert(table).values(row))
        connection.commit()
        with pytest.raises(IntegrityError):
            connection.execute(insert(table).values(dict(row, id=uuid.uuid4())))
        connection.rollback()
        assert connection.execute(text('SELECT count(*) FROM private_upload_sessions')).scalar_one() == 1
    engine.dispose()


def test_current_manifest_upload_columns_and_checks_match_migration():
    import ast
    import json
    manifest = json.loads((ROOT / 'deploy/offline/migration-schema-0030.json').read_text())
    from app.models.upload import PrivateUploadSession
    from sqlalchemy import CheckConstraint
    from sqlalchemy.dialects import postgresql
    table = PrivateUploadSession.__table__
    facts = manifest['facts']
    aliases = {'VARCHAR': 'character varying', 'TIMESTAMP WITH TIME ZONE': 'timestamp with time zone'}
    for column in table.c:
        kind = column.type.compile(dialect=postgresql.dialect())
        for old, new in aliases.items():
            kind = kind.replace(old, new)
        assert facts['column:private_upload_sessions.' + column.name] == dict(
            table=table.name, name=column.name, data_type=kind.lower(), nullable=column.nullable)
    for constraint in table.constraints:
        if isinstance(constraint, CheckConstraint):
            assert facts['constraint:private_upload_sessions.' + constraint.name]['expression'] == str(constraint.sqltext)
    source = ast.parse((ROOT / 'backend/alembic/versions/0030_private_upload_sessions.py').read_text())
    upgrade = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name=='upgrade')
    assert [node.value.func.attr for node in upgrade.body] == ['create_table', 'create_index']
    downgrade = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name=='downgrade')
    assert 'IF EXISTS (SELECT 1 FROM private_upload_sessions)' in ast.literal_eval(downgrade.body[0].value.args[0])
    assert [node.value.func.attr for node in downgrade.body] == ['execute', 'drop_index', 'drop_table']


def test_offline_consumers_require_current_head_and_reject_legacy_evidence():
    import hashlib
    import json
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    import offline_readonly_preflight as preflight
    import offline_migration_context as context
    import offline_migration_database_rehearsal as database
    import offline_migration_schema_evidence as schema
    from app.ops.retained_synthetic_restore import SUPPORTED_REVISION
    assert context.REVISION == preflight.REVISION == database.HEAD == SUPPORTED_REVISION == HEAD
    assert HEAD in database.MIGRATE
    assert HEAD in (ROOT / 'deploy/offline/database-readiness.sql').read_text()
    assert json.loads((ROOT / 'deploy/offline-readonly/manifest.example.json').read_text())['required_db_revision'] == HEAD
    legacy_bytes = (ROOT / 'deploy/offline/migration-schema-0029.json').read_bytes()
    assert hashlib.sha256(legacy_bytes).hexdigest() == '0eabda2f0f69fc3cb49d2fde23d9134f62a4acd4071a74a159083e53de67ec54'
    legacy = json.loads(legacy_bytes)
    evidence = dict(format=schema.EVIDENCE_FORMAT, checklist=legacy['checklist'], facts=legacy['facts'])
    assert schema.check_bytes(json.dumps(evidence).encode())['status'] == 'UNKNOWN'
    evidence['checklist'] = schema.CHECKLIST
    assert schema.check_bytes(json.dumps(evidence).encode())['status'] == 'STRUCTURE_CHECKLIST_MISMATCH'
