"""Standard-library contracts; no installed DB drivers or database operations."""
import ast
import json
import subprocess
import sys
from unittest import mock
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / 'backend/alembic/env.py'


class WidthContractTests(unittest.TestCase):
    def load_extension(self):
        tree = ast.parse(ENV.read_text())
        nodes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'OfflineVersionPostgresqlImpl']
        self.assertEqual(len(nodes), 1, 'offline version table extension is missing')
        class String:
            def __init__(self, length): self.length = length
        class Base:
            def version_table_impl(self, **kw):
                self.received = kw
                self.original = SimpleNamespace(c=SimpleNamespace(version_num=SimpleNamespace(type=String(32))))
                return self.original
        scope = {'PostgresqlImpl': Base, 'String': String}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ENV), 'exec'), scope)
        return scope['OfflineVersionPostgresqlImpl']

    def test_offline_width_is_64(self):
        instance = self.load_extension()(); instance.as_sql = True
        table = instance.version_table_impl(version_table='custom', version_table_schema='scope', version_table_pk=False)
        self.assertEqual(table.c.version_num.type.length, 64)
        self.assertIs(table, instance.original)
        self.assertEqual(instance.received, {'version_table':'custom', 'version_table_schema':'scope', 'version_table_pk':False})

    def test_online_table_is_unmodified(self):
        instance = self.load_extension()(); instance.as_sql = False
        table = instance.version_table_impl(version_table='alembic_version', version_table_schema=None, version_table_pk=True)
        self.assertEqual(table.c.version_num.type.length, 32)
        self.assertIs(table, instance.original)

    def test_extension_uses_original_postgres_base_and_public_hook(self):
        tree = ast.parse(ENV.read_text())
        extension = self.load_extension()
        self.assertEqual(extension.__dialect__, 'postgresql')
        imports = [n for n in tree.body if isinstance(n, ast.ImportFrom)]
        self.assertTrue(any(n.module == 'alembic.ddl.postgresql' and any(a.name == 'PostgresqlImpl' for a in n.names) for n in imports))
        self.assertFalse(any(isinstance(n, ast.Attribute) and n.attr in {'_version', '_impls'} for n in ast.walk(tree)))

    def test_offline_configure_pins_named_paramstyle(self):
        from contextlib import nullcontext
        node = next(n for n in ast.parse(ENV.read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'run_migrations_offline')
        seen = {}
        context = SimpleNamespace(configure=lambda **kw: seen.update(kw),
                                  begin_transaction=nullcontext, run_migrations=lambda: None)
        scope = {'context':context, 'config':SimpleNamespace(get_main_option=lambda key:'synthetic://no-connection'),
                 'target_metadata':None}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(ENV), 'exec'), scope)
        scope['run_migrations_offline']()
        self.assertEqual(seen.get('dialect_opts'), {'paramstyle':'named'})
        self.assertIs(seen['literal_binds'], True)

    def test_all_revision_ids_fit_fixed_width_and_long_revision_exists(self):
        revisions = []
        for path in (ROOT / 'backend/alembic/versions').glob('*.py'):
            for node in ast.parse(path.read_text()).body:
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'revision' for t in node.targets):
                    revisions.append(ast.literal_eval(node.value))
        self.assertEqual(len([r for r in revisions if r != '0030_private_upload_sessions']), 29)
        self.assertEqual(len(revisions), 30)
        self.assertGreater(max(map(len, revisions)), 32)
        self.assertLessEqual(max(map(len, revisions)), 64)


class SQLFixtureContracts(unittest.TestCase):
    path = ROOT / 'backend/tests/test_migration_sql_postgres.py'

    def test_catalog_connection_uses_compatible_timeout(self):
        tree = ast.parse(self.path.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'empty_sql_schema')
        options = [n.value for n in ast.walk(function) if isinstance(n, ast.Constant) and isinstance(n.value,str) and n.value.startswith('-cstatement_timeout=')]
        self.assertEqual(options, ['-cstatement_timeout=5000 -clock_timeout=1000 -cidle_in_transaction_session_timeout=15000'])

    def load_executor(self):
        tree = ast.parse(self.path.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'execute_generated')
        guard = mock.Mock()
        runner = mock.Mock(return_value=SimpleNamespace(returncode=0))
        scope = {'reject_pg_environment':guard, 'MAX_SQL':1024*1024, 'json':json, 'sys':sys,
                 'subprocess':SimpleNamespace(run=runner, DEVNULL=subprocess.DEVNULL), 'EXECUTE':'trusted fixture child'}
        exec(compile(ast.Module(body=[function],type_ignores=[]),str(self.path),'exec'),scope)
        return scope['execute_generated'],guard,runner

    def test_executor_is_bounded_and_does_not_inherit_environment(self):
        execute, guard, runner = self.load_executor()
        self.assertEqual(execute({'password':'synthetic'},'SELECT 1;'),0)
        guard.assert_called_once()
        args,kw = runner.call_args
        self.assertEqual(args[0], [sys.executable,'-I','-c','trusted fixture child'])
        self.assertEqual(kw['timeout'],90)
        self.assertEqual(kw['env'],{'LANG':'C.UTF-8'})
        self.assertEqual(kw['input'], b'{"password": "synthetic"}\nSELECT 1;')
        self.assertEqual(kw['stdout'],subprocess.DEVNULL)
        self.assertEqual(kw['stderr'],subprocess.DEVNULL)

    def test_executor_rejects_size_before_subprocess(self):
        execute, _guard, runner = self.load_executor()
        for value in ('', 'x'*(1024*1024+1), '\u4e2d'*(1024*1024//3+1)):
            with self.assertRaises(AssertionError): execute({},value)
        runner.assert_not_called()

    def test_executor_guard_failure_prevents_subprocess(self):
        execute, guard, runner = self.load_executor()
        guard.side_effect = RuntimeError('reject')
        with self.assertRaises(RuntimeError): execute({},'SELECT 1;')
        runner.assert_not_called()

    def test_executor_timeout_is_not_retried_or_reclassified(self):
        execute, _guard, runner = self.load_executor()
        runner.side_effect = subprocess.TimeoutExpired('fixture',90)
        with self.assertRaises(subprocess.TimeoutExpired): execute({},'SELECT 1;')
        self.assertEqual(runner.call_count,1)


if __name__ == '__main__': unittest.main()
