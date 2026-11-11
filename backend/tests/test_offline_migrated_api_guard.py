"""Synthetic guard transport contracts. No Docker, database or SQL is run."""
import copy
from contextlib import ExitStack
from enum import IntEnum
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import offline_migration_database_rehearsal as joint
import offline_pg_catalog_evidence as catalog
import offline_pg_guard_contracts as comparator

if importlib.util.find_spec('offline_migrated_api_guard'):
    import offline_migrated_api_guard as m
else:
    m = None

COMMIT = 'a' * 40
NETNS = 'net:[123]'
OPTIONS = ('-c default_transaction_read_only=on -c statement_timeout=5000 '
           '-c lock_timeout=1000 -c idle_in_transaction_session_timeout=15000')


def observation():
    facts = json.loads((ROOT / 'deploy/offline/migration-schema-0029.json').read_text())['facts']
    groups = {key: [] for key in catalog.LIMITS}
    for name in catalog.FUNCTIONS:
        groups['functions'].append(dict(namespace='public', name=name,
            identity_arguments='', result='trigger', language='plpgsql', security_definer=False,
            body_sha256=facts['function:' + name]['body_sha256'], body_bytes=100))
    for name in catalog.TRIGGERS:
        fact = facts['trigger:' + name]
        groups['triggers'].append(dict(namespace='public', table=fact['table'], name=name,
            function_namespace='public', function_name=fact['function'], function_arguments='',
            type_bits=27, enabled='O', internal=False, constraint=False, argument_count=0,
            argument_bytes=0, has_when=False, definition='PRIVATE_RAW_TRIGGER_DEFINITION'))
    return dict(format='slc-pg16-catalog-observation-v2', status='CATALOG_COLLECTED_NOT_ACCEPTANCE',
        namespace='public', namespace_oid=2200, server_version_num=160015,
        database_verified=False, complete_schema_verified=False, transaction_completed=False,
        observations=groups)


class Status(IntEnum):
    INTRANS = 2


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []
    def execute(self, sql, parameters=None):
        c = self.connection
        c.events.append(('sql', sql, parameters))
        if c.failure == 'execute': raise RuntimeError('PRIVATE_SQL_FAILURE')
        if sql == catalog.CONTEXT:
            self.rows = [(dict(server_version_num=160015, read_only=True,
                isolation='repeatable read', search_path='pg_catalog', statement_timeout_ms=5000,
                lock_timeout_ms=1000, idle_timeout_ms=15000, namespace_oid=2200),)]
        elif sql in catalog.QUERIES.values():
            group = next(key for key, value in catalog.QUERIES.items() if value == sql)
            self.rows = [(row,) for row in c.groups[group]]
    def fetchmany(self, maximum):
        return self.rows[:maximum]
    def close(self):
        self.connection.events.append(('cursor_close',))
        if self.connection.failure == 'cursor_close': raise RuntimeError('PRIVATE_CURSOR_FAILURE')


class Connection:
    def __init__(self, failure=None):
        self.events = []
        self.failure = failure
        self.info = SimpleNamespace(transaction_status=Status.INTRANS)
        self.groups = observation()['observations']
        migration = (ROOT / 'backend/alembic/versions/0029_changeover_batch_history.py').read_text()
        for row in self.groups['functions']:
            row['source'] = re.search(r'CREATE FUNCTION ' + row['name'] + r'\(\).*?\$\$(.*?)\$\$',
                                      migration, re.S)[1]
            assert hashlib.sha256(row['source'].encode()).hexdigest() == row.pop('body_sha256')
            row.pop('body_bytes')
    def cursor(self): return Cursor(self)
    def rollback(self):
        self.events.append(('rollback',))
        if self.failure == 'rollback': raise RuntimeError('PRIVATE_ROLLBACK_FAILURE')
    def close(self):
        self.events.append(('close',))
        if self.failure == 'close': raise RuntimeError('PRIVATE_CLOSE_FAILURE')


class GuardTransportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(m, 'bounded migrated guard transport is not implemented')
        self.budget = joint.builder.Budget(joint.time.monotonic())
        self.envelope = dict(format='slc-migrated-api-guard-observation-v1', observation=observation(),
                             rollback_completed=True, connection_closed=True)

    def raw(self): return json.dumps(self.envelope).encode()

    def prepare(self):
        def git(args, **kwargs):
            path = args[-1].split(':', 1)[1]
            return (ROOT / path).read_bytes()
        with patch.object(joint.builder.migration, 'bounded_command', side_effect=git):
            return m.prepare(COMMIT, self.budget)

    def execute(self, program=None, failure=None, env=None, uid=65532, netns=NETNS, interfaces=None):
        connection = Connection(failure)
        calls = []
        def connect(**kwargs):
            calls.append(kwargs)
            if failure == 'connect': raise RuntimeError('PRIVATE_CONNECT_FAILURE')
            if failure == 'interrupt': raise KeyboardInterrupt()
            if failure == 'exit': raise SystemExit(7)
            return connection
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(sys.modules, {'psycopg': SimpleNamespace(connect=connect)}), \
             patch.dict(os.environ, env if env is not None else {'PGCONNECT_TIMEOUT':'5', 'PGOPTIONS':OPTIONS}, clear=True), \
             patch('os.getuid', return_value=uid), patch('os.geteuid', return_value=uid), \
             patch('os.getgid', return_value=uid), patch('os.getegid', return_value=uid), \
             patch('os.readlink', return_value=netns), \
             patch('os.listdir', return_value=['lo'] if interfaces is None else interfaces), \
             patch.object(sys, 'argv', ['-c', NETNS]), patch.object(sys, 'stdout', stdout), \
             patch.object(sys, 'stderr', stderr):
            try:
                exec(program if program is not None else self.prepare(), {'__name__':'__main__'})
                code = 0
            except SystemExit as error:
                code = error.code
        return code, stdout.getvalue().encode(), stderr.getvalue(), calls, connection

    def test_no_cli_or_import_time_execution(self):
        self.assertFalse(hasattr(m, 'main'))
        source = (ROOT / 'scripts/offline_migrated_api_guard.py').read_text()
        with patch.object(joint.builder.migration, 'bounded_command', side_effect=AssertionError()), \
             patch.object(joint.builder.migration, 'read_at', side_effect=AssertionError()):
            namespace = {'__name__':'guard_import_test', '__file__':str(ROOT / 'scripts/offline_migrated_api_guard.py')}
            exec(compile(source, 'guard_import_test', 'exec'), namespace)

    def test_expected_checks_are_exact_pure_and_independent(self):
        expected = [{'check':kind + ':' + name, 'matched':True}
                    for kind, names in [('function', catalog.FUNCTIONS), ('trigger', catalog.TRIGGERS)] for name in names]
        self.assertEqual(m.expected_checks(), expected)
        first = m.expected_checks(); first[0]['matched'] = False
        self.assertEqual(m.expected_checks(), expected)

    def test_prepare_binds_all_five_sources_and_remaining_budget(self):
        calls = []
        def git(args, **kwargs):
            calls.append((args, kwargs))
            return (ROOT / args[-1].split(':', 1)[1]).read_bytes()
        with patch.object(joint.builder.migration, 'bounded_command', side_effect=git), \
             patch.object(self.budget, 'reserve', wraps=self.budget.reserve) as reserve:
            program = m.prepare(COMMIT, self.budget)
        expected = {'scripts/offline_migrated_api_guard.py', 'scripts/offline_pg_catalog_evidence.py',
                    'scripts/offline_pg_guard_contracts.py', 'scripts/offline_migration_schema_evidence.py',
                    'deploy/offline/migration-schema-0029.json'}
        self.assertEqual({args[-1].split(':', 1)[1] for args, _ in calls}, expected)
        self.assertIsInstance(program, str)
        self.assertTrue(all(call.args == (1330,) for call in reserve.call_args_list))
        for args, kwargs in calls:
            self.assertEqual(args[0], '/usr/bin/git')
            self.assertIn('--no-replace-objects', args)
            self.assertIn('--no-lazy-fetch', args)
            self.assertEqual(kwargs['env']['GIT_CONFIG_GLOBAL'], '/dev/null')
            self.assertLessEqual(kwargs['timeout'], 20)
            self.assertEqual(len(kwargs['pass_fds']), 1)

    def test_prepare_rejects_changed_source(self):
        with patch.object(joint.builder.migration, 'bounded_command', return_value=b'changed'):
            with self.assertRaises(m.Blocked): m.prepare(COMMIT, self.budget)

    def test_prepare_rejects_noncanonical_import(self):
        for module in (m, catalog, comparator, comparator.schema):
            with self.subTest(module=module.__name__), patch.object(module, '__file__', '/tmp/shadow.py'):
                with self.assertRaises(m.Blocked): self.prepare()

    def test_prepare_rejects_bad_arguments_and_exhausted_budget(self):
        for commit in ('main', 'a'*39, None, True):
            with self.subTest(commit=commit), self.assertRaises(m.Blocked): m.prepare(commit, self.budget)
        for budget in (None, object()):
            with self.assertRaises(m.Blocked): m.prepare(COMMIT, budget)
        self.budget.deadline = joint.time.monotonic() + 1359
        with self.assertRaises(m.Blocked): self.prepare()

    def test_prepare_preserves_host_control_exceptions(self):
        for error in (KeyboardInterrupt(), SystemExit(7)):
            with patch.object(joint.builder.migration, 'bounded_command', side_effect=error):
                with self.assertRaises(type(error)): m.prepare(COMMIT, self.budget)

    def test_program_uses_verified_collector_bytes_without_reopening(self):
        program = self.prepare()
        with patch.object(catalog, 'collect', side_effect=AssertionError()), \
             patch.object(joint.builder.migration, 'read_at', side_effect=AssertionError()):
            code, raw, stderr, calls, connection = self.execute(program)
        self.assertEqual((code, stderr), (0, ''))
        self.assertEqual(m.parse_and_check(raw)['checks'], m.expected_checks())

    def test_bootstrap_uses_fixed_target_and_explicit_transaction(self):
        code, raw, stderr, calls, connection = self.execute()
        self.assertEqual((code, stderr), (0, ''))
        self.assertEqual(len(calls), 1)
        config = calls[0]
        for key, value in dict(host='127.0.0.1', hostaddr='127.0.0.1', port=5432,
            dbname='slc_migration', user='postgres', connect_timeout=5, passfile='/dev/null',
            password='', options=OPTIONS, sslmode='disable', gssencmode='disable', autocommit=True).items():
            self.assertEqual(config[key], value)
        sqls = [event[1] for event in connection.events if event[0]=='sql']
        self.assertEqual(sqls[:5], ['BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY',
            'SET LOCAL search_path = pg_catalog', 'SET LOCAL statement_timeout = 5000',
            'SET LOCAL lock_timeout = 1000', 'SET LOCAL idle_in_transaction_session_timeout = 15000'])
        self.assertEqual(connection.events[-2:], [('rollback',), ('close',)])
        envelope = json.loads(raw)
        self.assertIs(envelope['observation']['transaction_completed'], False)
        self.assertIs(envelope['rollback_completed'], True)
        self.assertIs(envelope['connection_closed'], True)
        self.assertNotIn('source', envelope['observation']['observations']['functions'][0])
        self.assertNotIn('PRIVATE', json.dumps(m.parse_and_check(raw)))

    def test_bootstrap_rejects_pg_environment_overrides(self):
        for key in ('PGSERVICE', 'PGSERVICEFILE', 'PGHOST', 'PGHOSTADDR', 'PGPORT', 'PGDATABASE',
                    'PGUSER', 'PGPASSWORD', 'PGPASSFILE', 'PGSSLCERT', 'PGSSLKEY', 'PGOPTIONSX'):
            with self.subTest(key=key):
                code, raw, stderr, calls, _ = self.execute(env={'PGCONNECT_TIMEOUT':'5', 'PGOPTIONS':OPTIONS, key:'PRIVATE'})
                self.assertEqual((code, raw, stderr, calls), (2, b'', '', []))
        for env in ({}, {'PGCONNECT_TIMEOUT':'6','PGOPTIONS':OPTIONS}, {'PGCONNECT_TIMEOUT':'5','PGOPTIONS':'evil'}):
            code, raw, stderr, calls, _ = self.execute(env=env)
            self.assertEqual((code, raw, stderr, calls), (2, b'', '', []))

    def test_bootstrap_ignores_database_url_and_requires_namespace_uid_loopback(self):
        code, raw, _, calls, _ = self.execute(env={'PGCONNECT_TIMEOUT':'5','PGOPTIONS':OPTIONS,
                                                 'DATABASE_URL':'postgresql://PRIVATE@remote/db'})
        self.assertEqual(code, 0); self.assertEqual(calls[0]['host'], '127.0.0.1')
        for kwargs in ({'uid':0}, {'netns':'net:[999]'}, {'interfaces':['lo','eth0']}):
            code, raw, stderr, calls, _ = self.execute(**kwargs)
            self.assertEqual((code, raw, stderr, calls), (2, b'', '', []))

    def test_bootstrap_failures_never_emit_success_or_private_errors(self):
        for failure in ('connect', 'execute', 'cursor_close', 'rollback', 'close'):
            with self.subTest(failure=failure):
                code, raw, stderr, calls, connection = self.execute(failure=failure)
                self.assertEqual((code, raw, stderr), (2, b'', ''))
                if failure != 'connect': self.assertEqual(connection.events[-2:], [('rollback',), ('close',)])

    def test_parse_returns_only_nine_matched_checks_and_same_identity(self):
        receipt = m.parse_and_check(self.raw())
        self.assertEqual(receipt, dict(namespace_oid=2200, server_version_num=160015, checks=m.expected_checks()))
        self.assertEqual(m.checked_pair(receipt, copy.deepcopy(receipt)), m.expected_checks())

    def test_parse_rejects_wrong_fields_types_namespace_version_and_completion(self):
        variants = [dict(self.envelope, extra=True), dict(self.envelope, rollback_completed=False),
                    dict(self.envelope, connection_closed=1), dict(self.envelope, format='wrong')]
        for key, value in [('namespace','other'), ('namespace_oid',True), ('namespace_oid',0),
                           ('server_version_num',160014), ('server_version_num',True),
                           ('database_verified',True), ('complete_schema_verified',True),
                           ('transaction_completed',True)]:
            item = copy.deepcopy(self.envelope); item['observation'][key]=value; variants.append(item)
        for item in variants:
            with self.subTest(item=item), self.assertRaises(m.Blocked): m.parse_and_check(json.dumps(item).encode())

    def test_parse_rejects_mismatch_missing_duplicate_and_unknown_facts(self):
        for mutation in ('hash','trigger','missing','duplicate','unknown'):
            item = copy.deepcopy(self.envelope); groups = item['observation']['observations']
            if mutation=='hash': groups['functions'][0]['body_sha256']='0'*64
            if mutation=='trigger': groups['triggers'][0]['type_bits']=19
            if mutation=='missing': groups['functions'].pop()
            if mutation=='duplicate': groups['functions'].append(copy.deepcopy(groups['functions'][0]))
            if mutation=='unknown': groups['functions'][0]['extra']='PRIVATE'
            with self.subTest(mutation=mutation), self.assertRaises(m.Blocked): m.parse_and_check(json.dumps(item).encode())

    def test_parse_rejects_duplicate_keys_float_nan_utf8_depth_and_oversize(self):
        bad = [b'', b'{}', b'{"a":1,"a":2}', b'{"a":1.0}', b'{"a":NaN}', b'\xff',
               b'['*100+b'0'+b']'*100, b' '*524289, self.raw().decode(), bytearray(self.raw()),
               b'{"a":"\\ud800"}', b'{"a":-1}', b'{"a":18446744073709551616}']
        for raw in bad:
            with self.subTest(kind=type(raw), length=len(raw)), self.assertRaises(m.Blocked): m.parse_and_check(raw)

    def test_parse_accepts_private_definition_above_http_limit_but_not_field_limit(self):
        self.envelope['observation']['observations']['triggers'][0]['definition']='x'*12000
        self.assertGreater(len(self.raw()), 4096)
        self.assertEqual(m.parse_and_check(self.raw())['checks'], m.expected_checks())
        self.envelope['observation']['observations']['triggers'][0]['definition']='x'*16385
        with self.assertRaises(m.Blocked): m.parse_and_check(self.raw())

    def test_parser_controls_propagate_and_errors_are_redacted(self):
        for error in (KeyboardInterrupt(), SystemExit(7)):
            with patch.object(comparator, 'check_observation', side_effect=error):
                with self.assertRaises(type(error)): m.parse_and_check(self.raw())
        with patch.object(comparator, 'check_observation', side_effect=RuntimeError('PRIVATE')):
            with self.assertRaises(m.Blocked) as caught: m.parse_and_check(self.raw())
        self.assertNotIn('PRIVATE', str(caught.exception))

    def test_pair_rejects_oid_version_check_changes_and_forged_types(self):
        before = m.parse_and_check(self.raw())
        variants = [dict(before, namespace_oid=2201), dict(before, server_version_num=160014),
                    dict(before, namespace_oid=True), dict(before, extra=True), dict(before, checks=[])]
        changed = copy.deepcopy(before); changed['checks'][0]['matched']=1; variants.append(changed)
        for after in variants:
            with self.subTest(after=after), self.assertRaises(m.Blocked): m.checked_pair(before, after)


    def test_prepare_caps_escaped_program_before_any_runtime(self):
        payload = b'#' + b'\x00' * 20000
        path = 'scripts/offline_pg_catalog_evidence.py'
        original = joint.builder.migration.read_at
        def read(fd, name, limit): return payload if name == path else original(fd, name, limit)
        def git(args, **kwargs):
            name = args[-1].split(':', 1)[1]
            return payload if name == path else (ROOT / name).read_bytes()
        with patch.object(joint.builder.migration, 'read_at', side_effect=read), \
             patch.object(joint.builder.migration, 'bounded_command', side_effect=git):
            with self.assertRaises(m.Blocked): m.prepare(COMMIT, self.budget)
        self.assertLessEqual(len(self.prepare().encode('utf-8')), 65536)

    def test_prepare_checks_each_file_not_only_collector(self):
        for changed in m.SOURCES:
            def git(args, **kwargs):
                path = args[-1].split(':', 1)[1]
                return b'PRIVATE_CHANGED_SOURCE' if path == changed else (ROOT / path).read_bytes()
            with self.subTest(path=changed), patch.object(joint.builder.migration, 'bounded_command', side_effect=git):
                with self.assertRaises(m.Blocked) as caught: m.prepare(COMMIT, self.budget)
            self.assertEqual(str(caught.exception), 'API_GUARD_SOURCE_REJECTED')

    def test_prepare_detects_deadline_change_and_reserves_before_io(self):
        def changed(args, **kwargs):
            self.budget.deadline += 1
            return (ROOT / args[-1].split(':', 1)[1]).read_bytes()
        with patch.object(joint.builder.migration, 'bounded_command', side_effect=changed):
            with self.assertRaises(m.Blocked): m.prepare(COMMIT, self.budget)
        self.budget.deadline = joint.time.monotonic() + 1359
        with patch.object(joint.builder.migration, 'bounded_command', side_effect=AssertionError()) as git:
            with self.assertRaises(m.Blocked): m.prepare(COMMIT, self.budget)
        git.assert_not_called()

    def test_prepare_file_failures_are_redacted_and_controls_preserved(self):
        def git(args, **kwargs): return (ROOT / args[-1].split(':', 1)[1]).read_bytes()
        with patch.object(joint.builder.migration, 'bounded_command', side_effect=git):
            for error in (OSError('PRIVATE_FILE_ERROR'), KeyboardInterrupt(), SystemExit(7)):
                with patch.object(joint.builder.migration, 'read_at', side_effect=error):
                    with self.assertRaises(m.Blocked if isinstance(error, Exception) else type(error)) as caught:
                        m.prepare(COMMIT, self.budget)
                self.assertNotIn('PRIVATE', str(caught.exception))

    def test_prepare_rejects_symlink_hardlink_and_oversize_real_fd_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in m.SOURCES:
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            paths = [(m, '__file__', root / 'scripts/offline_migrated_api_guard.py'),
                     (catalog, '__file__', root / 'scripts/offline_pg_catalog_evidence.py'),
                     (comparator, '__file__', root / 'scripts/offline_pg_guard_contracts.py'),
                     (comparator.schema, '__file__', root / 'scripts/offline_migration_schema_evidence.py')]
            def git(args, **kwargs): return (root / args[-1].split(':', 1)[1]).read_bytes()
            target = root / 'scripts/offline_pg_catalog_evidence.py'
            backup = target.read_bytes()
            with ExitStack() as stack:
                stack.enter_context(patch.object(m, 'ROOT', root))
                stack.enter_context(patch.object(comparator.schema, 'MANIFEST_PATH', root / 'deploy/offline/migration-schema-0029.json'))
                for module, attr, path in paths: stack.enter_context(patch.object(module, attr, str(path)))
                stack.enter_context(patch.object(joint.builder.migration, 'bounded_command', side_effect=git))
                for kind in ('symlink', 'hardlink', 'oversize'):
                    target.unlink()
                    other = root / kind; other.write_bytes(backup)
                    if kind == 'symlink': target.symlink_to(other)
                    elif kind == 'hardlink': os.link(other, target)
                    else: target.write_bytes(b'x' * 65537)
                    with self.subTest(kind=kind), self.assertRaises(m.Blocked): m.prepare(COMMIT, self.budget)

    def test_prepare_rejects_changed_manifest_even_when_git_matches(self):
        original = joint.builder.migration.read_at
        def changed_read(fd, path, limit):
            raw = original(fd, path, limit)
            return raw + b' ' if path.endswith('migration-schema-0029.json') else raw
        def git(args, **kwargs):
            path = args[-1].split(':', 1)[1]
            raw = (ROOT / path).read_bytes()
            return raw + b' ' if path.endswith('migration-schema-0029.json') else raw
        with patch.object(joint.builder.migration, 'bounded_command', side_effect=git), \
             patch.object(joint.builder.migration, 'read_at', side_effect=changed_read):
            with self.assertRaises(m.Blocked): m.prepare(COMMIT, self.budget)

    def test_bootstrap_caps_full_envelope_after_cleanup_and_suppresses_controls(self):
        program = self.prepare()
        real_dumps = json.dumps
        def dumps(value, **kwargs):
            if type(value) is dict and value.get('format') == m.FORMAT: return 'x' * 524289
            return real_dumps(value, **kwargs)
        with patch.object(json, 'dumps', side_effect=dumps):
            code, raw, stderr, _, connection = self.execute(program)
        self.assertEqual((code, raw, stderr), (2, b'', ''))
        self.assertEqual(connection.events[-2:], [('rollback',), ('close',)])
        for failure in ('interrupt', 'exit'):
            code, raw, stderr, _, _ = self.execute(program, failure=failure)
            self.assertEqual((code, raw, stderr), (2, b'', ''))

    def test_bootstrap_success_output_occurs_strictly_after_close(self):
        program = self.prepare()
        events = []
        original_close = Connection.close
        def close(connection):
            events.append('close')
            return original_close(connection)
        real_dumps = json.dumps
        def dumps(value, **kwargs):
            if type(value) is dict and value.get('format') == m.FORMAT: events.append('serialize_envelope')
            return real_dumps(value, **kwargs)
        with patch.object(Connection, 'close', close), patch.object(json, 'dumps', side_effect=dumps):
            code, raw, stderr, _, _ = self.execute(program)
        self.assertEqual((code, stderr), (0, ''))
        self.assertEqual(events, ['close', 'serialize_envelope'])
        self.assertIs(json.loads(raw)['connection_closed'], True)

    def test_parser_requires_actual_exact_comparator_result(self):
        result = comparator.check_observation(self.envelope['observation'], 'public')
        variants = [dict(result, status='UNKNOWN'), dict(result, checks=result['checks'][:-1]),
                    dict(result, checks=result['checks'] + result['checks'][:1]),
                    dict(result, database_verified=True), dict(result, extra=True)]
        changed = copy.deepcopy(result); changed['checks'][0]['matched'] = 1; variants.append(changed)
        changed = copy.deepcopy(result); changed['checks'][0]['matched'] = False; variants.append(changed)
        for item in variants:
            with self.subTest(item=item), patch.object(comparator, 'check_observation', return_value=item):
                with self.assertRaises(m.Blocked): m.parse_and_check(self.raw())

    def test_private_raw_definitions_never_survive_receipts_or_rejections(self):
        for matched in (True, False):
            item = copy.deepcopy(self.envelope)
            item['observation']['observations']['triggers'][0]['definition'] = 'PRIVATE_SENSITIVE_LITERAL'
            if not matched: item['observation']['observations']['triggers'][0]['argument_bytes'] = 1
            raw = json.dumps(item).encode()
            if matched:
                result = m.parse_and_check(raw)
                self.assertNotIn('PRIVATE', json.dumps(result))
                self.assertNotIn('PRIVATE', json.dumps(m.checked_pair(result, result)))
            else:
                with self.assertRaises(m.Blocked) as caught: m.parse_and_check(raw)
                self.assertNotIn('PRIVATE', str(caught.exception))


if __name__ == '__main__': unittest.main()
