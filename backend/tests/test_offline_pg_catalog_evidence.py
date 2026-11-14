"""Local mocks only: these tests do not open a database connection."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from enum import IntEnum
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/offline_pg_catalog_evidence.py'


class Cursor:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []
        self.closed = False
    def execute(self, query, parameters=None):
        self.calls.append((query, parameters))
        self.rows = next(self.results)
    def fetchmany(self, count):
        return self.rows[:count]
    def close(self):
        self.closed = True


class Status(IntEnum):
    IDLE = 0
    INTRANS = 2
    INERROR = 3


class Connection:
    def __init__(self, results):
        self.c = Cursor(results)
        self.info = SimpleNamespace(transaction_status=Status.INTRANS)
    def cursor(self):
        return self.c


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), 'catalog collector is not implemented')
        spec = importlib.util.spec_from_file_location('catalog', SCRIPT)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.context = {'server_version_num': 160015, 'read_only': True,
                        'isolation': 'repeatable read', 'search_path': 'pg_catalog',
                        'statement_timeout_ms': 5000, 'lock_timeout_ms': 1000,
                        'idle_timeout_ms': 15000, 'namespace_oid': 12345}
        self.namespace = 'ci_catalog_' + 'a' * 32
    def connection(self, context=None, groups=None):
        return Connection([[(self.context if context is None else context,)]] +
                          ([[] for _ in range(6)] if groups is None else groups))
    def test_empty_observation_is_not_schema_acceptance(self):
        c = self.connection()
        result = self.m.collect(c, self.namespace)
        self.assertEqual(result['status'], 'CATALOG_COLLECTED_NOT_ACCEPTANCE')
        self.assertEqual(result['format'], 'slc-pg16-catalog-observation-v2')
        self.assertEqual(result['namespace'], self.namespace)
        self.assertFalse(result['database_verified'])
        self.assertFalse(result['complete_schema_verified'])
        self.assertEqual(len(c.c.calls), 7)
        self.assertTrue(c.c.closed)
    def test_namespace_is_never_public_rewritten(self):
        result = self.m.collect(self.connection(), self.namespace)
        self.assertNotIn('public', json.dumps(result))
    def test_bad_namespace_is_rejected_before_cursor(self):
        for name in ('', 'public; DROP TABLE x', 'pg_catalog', 'information_schema', 'pg_temp_1', 'A', 'x' * 64, None):
            with self.subTest(name=name), self.assertRaises(self.m.CatalogError):
                self.m.collect(object(), name)
    def test_non_pg16_is_rejected(self):
        for version in (150000, 170000, True, '160015'):
            context = dict(self.context, server_version_num=version)
            with self.assertRaises(self.m.CatalogError):
                self.m.collect(self.connection(context), self.namespace)
    def test_transaction_and_timeout_preconditions_fail_closed(self):
        for field, value in [('read_only', False), ('isolation', 'read committed'),
                             ('search_path', 'public'), ('statement_timeout_ms', 0),
                             ('statement_timeout_ms', 5001), ('lock_timeout_ms', 1001),
                             ('idle_timeout_ms', 15001), ('idle_timeout_ms', True)]:
            with self.subTest(field=field, value=value), self.assertRaises(self.m.CatalogError):
                self.m.collect(self.connection(dict(self.context, **{field: value})), self.namespace)
    def test_context_shape_must_be_exact(self):
        for context in ({}, dict(self.context, extra='secret'), None):
            with self.assertRaises(self.m.CatalogError):
                self.m.collect(self.connection(context if context is not None else {}), self.namespace)
    def test_queries_are_fixed_selects_and_namespace_is_bound(self):
        c = self.connection(); self.m.collect(c, self.namespace)
        for query, params in c.c.calls[1:]:
            self.assertEqual(params, (12345,))
            self.assertNotIn(self.namespace, query)
            self.assertTrue(query.lstrip().startswith('SELECT'))
            for verb in ('CREATE ', 'ALTER ', 'DROP ', 'GRANT ', 'REVOKE ', 'INSERT ', 'UPDATE ', 'DELETE '):
                self.assertNotIn(verb, query)
    def test_no_commit_rollback_or_connection_ownership(self):
        c = self.connection(); self.m.collect(c, self.namespace)
        self.assertFalse(hasattr(c, 'commit'))
        self.assertFalse(hasattr(c, 'rollback'))
    def test_row_limits_reject_not_truncate(self):
        groups = [[({},)] * 20] + [[] for _ in range(5)]
        with self.assertRaises(self.m.CatalogError):
            self.m.collect(self.connection(groups=groups), self.namespace)
    def test_wrong_record_types_reject(self):
        for value in (None, [], 'secret', {'extra': 'secret'}):
            groups = [[(value,)]] + [[] for _ in range(5)]
            with self.assertRaises(self.m.CatalogError):
                self.m.collect(self.connection(groups=groups), self.namespace)
    def test_wrong_namespace_record_rejects(self):
        row = copy.deepcopy(self.m.EXAMPLES['tables'])
        row['namespace'] = 'other'
        groups = [[(row,)]] + [[] for _ in range(5)]
        with self.assertRaises(self.m.CatalogError):
            self.m.collect(self.connection(groups=groups), self.namespace)
    def test_duplicate_records_reject(self):
        row = dict(self.m.EXAMPLES['tables'], namespace=self.namespace)
        groups = [[(row,), (row,)]] + [[] for _ in range(5)]
        with self.assertRaises(self.m.CatalogError):
            self.m.collect(self.connection(groups=groups), self.namespace)
    def test_function_body_hash_preserves_bytes(self):
        row = dict(self.m.EXAMPLES['functions'], namespace=self.namespace, source='\n BEGIN\n RETURN NEW;\n END;\n')
        groups = [[] for _ in range(6)]; groups[4] = [(row,)]
        result = self.m.collect(self.connection(groups=groups), self.namespace)
        import hashlib
        actual = result['observations']['functions'][0]
        self.assertEqual(actual['body_sha256'], hashlib.sha256(row['source'].encode()).hexdigest())
        self.assertNotIn('source', actual)
    def test_raw_expression_is_not_normalized(self):
        row = dict(self.m.EXAMPLES['constraints'], namespace=self.namespace, definition="CHECK (((x)::text = 'A'::text))")
        groups = [[] for _ in range(6)]; groups[2] = [(row,)]
        result = self.m.collect(self.connection(groups=groups), self.namespace)
        self.assertEqual(result['observations']['constraints'][0]['definition'], row['definition'])
    def test_execute_failure_is_fixed_error_without_partial_result(self):
        c = self.connection(); c.c.execute = lambda *args: (_ for _ in ()).throw(RuntimeError('SECRET'))
        with self.assertRaisesRegex(self.m.CatalogError, '^CATALOG_COLLECTION_FAILED$') as error:
            self.m.collect(c, self.namespace)
        self.assertNotIn('SECRET', str(error.exception))
        self.assertTrue(c.c.closed)
    def test_close_failure_is_not_success(self):
        c = self.connection(); c.c.close = lambda: (_ for _ in ()).throw(OSError('SECRET'))
        with self.assertRaises(self.m.CatalogError):
            self.m.collect(c, self.namespace)

    def test_namespace_oid_is_required_positive_and_strict_integer(self):
        for value in (0, -1, True, '12345', 2**32):
            with self.assertRaises(self.m.CatalogError):
                self.m.collect(self.connection(dict(self.context, namespace_oid=value)), self.namespace)
    def test_text_limits_and_invalid_utf8_fail_closed(self):
        for value in ('x' * 16385, '\ud800', 'x\x00y'):
            row = dict(self.m.EXAMPLES['functions'], namespace=self.namespace, source=value)
            groups = [[] for _ in range(6)]; groups[4] = [(row,)]
            with self.assertRaises(self.m.CatalogError):
                self.m.collect(self.connection(groups=groups), self.namespace)
    def test_bool_integer_and_array_types_do_not_coerce(self):
        for group, key, value in [('columns', 'position', True), ('tables', 'row_security', 0),
                                  ('constraints', 'columns', [1]), ('constraints', 'columns', ['x'] * 33)]:
            row = dict(self.m.EXAMPLES[group], namespace=self.namespace, **{key: value})
            groups = [[] for _ in range(6)]; groups[list(self.m.QUERIES).index(group)] = [(row,)]
            with self.assertRaises(self.m.CatalogError):
                self.m.collect(self.connection(groups=groups), self.namespace)
    def test_total_result_budget_rejects_not_truncates(self):
        groups = [[] for _ in range(6)]
        groups[2] = [(dict(self.m.EXAMPLES['constraints'], namespace=self.namespace,
                          name='check_' + str(i), definition='x' * 16000),) for i in range(40)]
        with self.assertRaises(self.m.CatalogError):
            self.m.collect(self.connection(groups=groups), self.namespace)
    def test_fixed_sql_has_server_side_limits(self):
        for group, query in self.m.QUERIES.items():
            self.assertTrue(query.endswith('LIMIT ' + str(self.m.LIMITS[group] + 1)))
        self.assertIn('16385', self.m.QUERIES['functions'])
        self.assertIn('pg_catalog.pg_namespace', self.m.CONTEXT)
    def test_ci_fixture_is_new_scoped_without_workflow_changes(self):
        import ast
        path = ROOT / 'backend/tests/test_pg_catalog_evidence_postgres.py'
        text = path.read_text()
        ast.parse(text)
        for required in ('GITHUB_ACTIONS', 'GITHUB_REPOSITORY', '127.0.0.1', 'software_lifecycle_ci',
                         'slc_ci', 'uuid.uuid4().hex', 'nspowner', 'timeout=90',
                         "'0030_private_upload_sessions'", 'SET LOCAL search_path=pg_catalog'):
            self.assertIn(required, text)
        for excluded in ('command.stamp(', 'create_all(', 'GRANT ', 'REVOKE ', 'CREATE ROLE', 'docker run'):
            self.assertNotIn(excluded, text)

    def test_idle_connection_cannot_masquerade_as_one_readonly_transaction(self):
        c = self.connection(); c.info.transaction_status = Status.IDLE
        with self.assertRaises(self.m.CatalogError):
            self.m.collect(c, self.namespace)
        self.assertEqual(c.c.calls, [])
    def test_transaction_must_still_be_intrans_at_return(self):
        c = self.connection()
        def close():
            c.c.closed = True
            c.info.transaction_status = Status.IDLE
        c.c.close = close
        with self.assertRaises(self.m.CatalogError):
            self.m.collect(c, self.namespace)
    def test_ci_target_guard_rejects_all_pg_environment_overrides(self):
        import ast
        source = ast.parse((ROOT / 'backend/tests/test_pg_catalog_evidence_postgres.py').read_text())
        nodes = [n for n in source.body if isinstance(n, ast.FunctionDef) and n.name in ('ci_url', 'reject_pg_environment')]
        env = {'GITHUB_ACTIONS': 'true', 'CI': 'true', 'GITHUB_REPOSITORY': 'Wang106/SoftwareLifeCycle',
               'TEST_POSTGRES_URL': 'synthetic'}
        url = SimpleNamespace(drivername='postgresql+psycopg', host='127.0.0.1', port=5432,
                              database='software_lifecycle_ci', username='slc_ci', password='synthetic', query={})
        scope = {'os': SimpleNamespace(environ=env), 'make_url': lambda raw: url}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<fixture-guard>', 'exec'), scope)
        self.assertIs(scope['ci_url'](), url)
        for key in ('PGHOSTADDR', 'PGSERVICE', 'PGOPTIONS', 'PGPASSFILE', 'PGHOST'):
            env[key] = 'override'
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                scope['ci_url']()
            del env[key]
    def test_each_fixture_connection_checks_pg_environment_first(self):
        import ast
        source = ast.parse((ROOT / 'backend/tests/test_pg_catalog_evidence_postgres.py').read_text())
        function = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'observe')
        first = function.body[0]
        self.assertIsInstance(first, ast.Expr)
        self.assertEqual(first.value.func.id, 'reject_pg_environment')


if __name__ == '__main__':
    unittest.main()
