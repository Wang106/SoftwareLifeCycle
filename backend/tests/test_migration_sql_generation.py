"""Real offline SQL generation, requiring pinned dependencies but no database."""
import ast
from pathlib import Path
import subprocess
import sys
import tempfile

from alembic.runtime.migration import MigrationContext
from alembic.ddl.postgresql import PostgresqlImpl
from sqlalchemy import String

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
HEAD = '0029_changeover_batch_history'
MAX_SQL = 1024 * 1024
GENERATE = '''import resource, sys
resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
sys.path.insert(0, sys.argv[1])
from unittest.mock import patch
from alembic import command
from alembic.config import Config
config = Config(sys.argv[1] + '/alembic.ini')
config.set_main_option('script_location', sys.argv[1] + '/alembic')
with patch('sqlalchemy.engine_from_config', side_effect=AssertionError('offline must not connect')), patch('psycopg.connect', side_effect=AssertionError('offline must not connect')):
    command.upgrade(config, '0029_changeover_batch_history', sql=True)
'''


def generate_sql():
    # Empty cwd and explicit settings prevent reading developer .env or DB URLs.
    env = {'LANG':'C.UTF-8', 'DATABASE_URL':'postgresql+psycopg://unused:unused@127.0.0.1:1/unused',
           'AUTH_MODE':'disabled', 'READ_ONLY_MODE':'true', 'SEED_ON_STARTUP':'false'}
    with tempfile.TemporaryDirectory(prefix='slc-offline-sql-') as directory, tempfile.TemporaryFile() as output:
        result = subprocess.run([sys.executable, '-I', '-c', GENERATE, str(BACKEND)], cwd=directory,
                                env=env, stdout=output, stderr=subprocess.DEVNULL, timeout=60, check=False)
        assert result.returncode == 0, 'Offline SQL generation failed'
        output.seek(0); raw = output.read(MAX_SQL + 1)
    assert 0 < len(raw) <= MAX_SQL
    return raw.decode('utf-8')


def test_real_generated_sql_has_wide_primary_key_and_all_revisions():
    statement = generate_sql()
    assert 'version_num VARCHAR(64) NOT NULL' in statement
    assert 'version_num VARCHAR(32)' not in statement
    assert 'deployment_actual_baselines%ROWTYPE' in statement
    assert '%%ROWTYPE' not in statement
    assert 'CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)' in statement
    assert statement.count('-- Running upgrade ') == 29
    assert "'0008_authorization_distribution_link'" in statement
    assert "'0029_changeover_batch_history'" in statement
    assert statement.lstrip().startswith('BEGIN;') and statement.rstrip().endswith('COMMIT;')


def test_real_hook_alternates_offline_online_preserving_schema_and_pk():
    # Load only the production extension, not env.py's execution entrypoint.
    nodes = [n for n in ast.parse((BACKEND / 'alembic/env.py').read_text()).body
             if isinstance(n, ast.ClassDef) and n.name == 'OfflineVersionPostgresqlImpl']
    assert len(nodes) == 1
    scope = {'PostgresqlImpl':PostgresqlImpl, 'String':String}
    for _ in range(2):
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<production-version-hook>', 'exec'), scope)
        cls = scope['OfflineVersionPostgresqlImpl']
        assert cls.__bases__ == (PostgresqlImpl,)
        for offline, width in ((True,64), (False,32), (True,64)):
            ctx = MigrationContext.configure(dialect_name='postgresql', opts={'as_sql':offline})
            assert type(ctx.impl) is cls
            for pk in (False, True):
                table = ctx.impl.version_table_impl(version_table='custom_versions', version_table_schema='only_here', version_table_pk=pk)
                assert table.name == 'custom_versions' and table.schema == 'only_here'
                assert table.c.version_num.type.length == width and table.c.version_num.nullable is False
                assert list(table.primary_key.columns.keys()) == (['version_num'] if pk else [])
