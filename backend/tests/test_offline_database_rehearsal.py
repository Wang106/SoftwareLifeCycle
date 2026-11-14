"""Mock-only contracts. No Docker, psql, network or database execution."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import offline_database_rehearsal as rehearsal
import offline_database_readiness as checker


def baseline():
    value = {'format': checker.EVIDENCE_FORMAT, 'server_version_num': 160015}
    value.update({key: False for key in checker.FALSE_FIELDS})
    value.update({key: True for key in checker.TRUE_FIELDS})
    value.update({key: 0 for key in checker.ZERO_FIELDS})
    value.update({key: 1 for key in checker.ONE_FIELDS + checker.MIGRATION_COUNTS})
    # Fabricated PUBLIC defaults; never a claim that PostgreSQL was run.
    value.update(database_temp=True, table_write_count=1, column_write_count=17)
    return value


def payload(value):
    return json.dumps(value).encode()


class ResultContracts(unittest.TestCase):
    def test_opt_in_is_required_without_commands(self):
        with patch.object(rehearsal, 'run_rehearsal') as run, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(rehearsal.main([]), 2)
        run.assert_not_called()
        self.assertEqual(json.loads(out.getvalue())['reason'], 'RUN_REQUIRED')

    def test_unknown_arguments_never_echo_targets(self):
        with patch.object(rehearsal, 'run_rehearsal') as run, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(rehearsal.main(['--run', '--url', 'SECRET']), 2)
        run.assert_not_called()
        self.assertNotIn('SECRET', out.getvalue())

    def test_help_has_no_side_effect(self):
        with patch.object(rehearsal, 'run_rehearsal') as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rehearsal.main(['--help']), 0)
        run.assert_not_called()

    def test_nonzero_psql_is_collector_error_even_with_valid_json(self):
        for code in (-9, 1, 2):
            with self.subTest(code=code), self.assertRaisesRegex(rehearsal.Blocked, '^COLLECTOR_ERROR$'):
                rehearsal.collect_document(code, payload(baseline()))

    def test_collector_requires_one_bounded_strict_document(self):
        raw = payload(baseline())
        for bad in (b'', raw + raw, raw[:-1] + b',"format":"x"}', b'null', b'\xff',
                    raw.replace(b'160015', b'1.60015e5'), raw + b' ' * checker.MAX_BYTES):
            with self.subTest(bad=bad[:30]), self.assertRaises(rehearsal.Blocked):
                rehearsal.collect_document(0, bad)
        self.assertEqual(rehearsal.collect_document(0, raw), baseline())

    def test_baseline_requires_mismatch_without_revoking_public(self):
        rehearsal.assert_case('baseline', baseline(), baseline())
        value = baseline(); value['database_temp'] = False
        with self.assertRaises(rehearsal.Blocked):
            rehearsal.assert_case('baseline', value, value)

    def test_targeted_write_deltas_cannot_be_hidden_by_public_baseline(self):
        for name, changes in [('table_write', {'table_write_count': 2, 'column_write_count': 19}),
                              ('column_write', {'table_write_count': 1, 'column_write_count': 18})]:
            value = baseline(); value.update(changes)
            rehearsal.assert_case(name, value, baseline())
            with self.assertRaises(rehearsal.Blocked):
                rehearsal.assert_case(name, baseline(), baseline())

    def test_membership_owner_and_every_dangerous_flag(self):
        changes = {'membership': {'role_membership_count': 1},
                   'owner': {'owned_object_count': 1, 'table_write_count': 2, 'column_write_count': 19}}
        changes.update({key: {key: True} for key in rehearsal.ROLE_FLAGS})
        changes['role_superuser'].update(database_create=True, schema_create_count=4,
                                         table_write_count=100, column_write_count=1000)
        for name, delta in changes.items():
            with self.subTest(name=name):
                value = baseline(); value.update(delta)
                rehearsal.assert_case(name, value, baseline())
                with self.assertRaises(rehearsal.Blocked):
                    rehearsal.assert_case(name, baseline(), baseline())

    def test_wrong_and_multiple_heads_need_exact_counts(self):
        for name, counts in [('wrong_head', (1, 0)), ('multiple_heads', (2, 1))]:
            value = baseline(); value.update(zip(checker.MIGRATION_COUNTS, counts))
            rehearsal.assert_case(name, value, baseline())
            with self.assertRaises(rehearsal.Blocked):
                rehearsal.assert_case(name, baseline(), baseline())

    def test_view_and_expression_partial_indexes_must_not_read_versions(self):
        for name in ('migration_view', 'expression_index', 'partial_index'):
            value = baseline(); value.update(migration_table_supported=False,
                migration_select_permitted=False, migration_row_count=None,
                migration_expected_head_count=None)
            if name == 'migration_view': value['unsupported_relation_count'] = 1
            rehearsal.assert_case(name, value, baseline())
            with self.assertRaises(rehearsal.Blocked):
                rehearsal.assert_case(name, baseline(), baseline())

    def test_case_does_not_hide_unrelated_field_regressions(self):
        value = baseline(); value.update(role_membership_count=1, migration_row_count=0,
                                         migration_expected_head_count=0)
        with self.assertRaises(rehearsal.Blocked):
            rehearsal.assert_case('membership', value, baseline())

    def test_baseline_must_observe_system_public_write_privileges(self):
        value = baseline(); value.update(table_write_count=0, column_write_count=0)
        with self.assertRaises(rehearsal.Blocked):
            rehearsal.assert_case('baseline', value, value)

    def test_independent_checker_exact_receipt_and_return_code(self):
        value = baseline(); raw = payload(checker.check_document(value))
        rehearsal.verify_checker(1, raw, value)
        for code, bad in ((0, raw), (2, raw), (1, raw + raw), (1, payload({'status': 'CHECKLIST_MISMATCH'}))):
            with self.subTest(code=code), self.assertRaises(rehearsal.Blocked):
                rehearsal.verify_checker(code, bad, value)

    def test_bool_integer_alias_in_checker_receipt_is_rejected(self):
        value = checker.check_document(baseline()); value['checks'] = True
        with self.assertRaises(rehearsal.Blocked):
            rehearsal.verify_checker(1, payload(value), baseline())

    def test_fixture_has_no_public_revokes_or_passwords(self):
        for case in rehearsal.CASES:
            sql = rehearsal.fixture_sql(case)
            self.assertIn('NOLOGIN', sql)
            self.assertNotIn('REVOKE', sql)
            self.assertNotIn('PASSWORD', sql)
            self.assertNotIn('ALTER ROLE', sql)
            if case != 'missing_table': self.assertIn('VARCHAR(64)', sql)
        self.assertIn('PRIMARY KEY', rehearsal.fixture_sql('baseline'))
        self.assertIn('0030_private_upload_sessions', rehearsal.fixture_sql('baseline'))

    def test_unknown_case_never_becomes_sql(self):
        with self.assertRaises(rehearsal.Blocked):
            rehearsal.fixture_sql("x'; SECRET")

    def test_psql_is_fresh_unix_socket_and_changes_session_authorization(self):
        args = rehearsal.psql_args('a' * 64, 'baseline')
        self.assertIn('--no-psqlrc', args)
        self.assertIn('--set=ON_ERROR_STOP=1', args)
        self.assertIn('--host=/var/run/postgresql', args)
        self.assertIn('--no-password', args)
        self.assertNotIn('-h', args)
        script = rehearsal.collector_sql('baseline')
        self.assertTrue(script.startswith('SET SESSION AUTHORIZATION slc_baseline;\n'))
        self.assertNotRegex(script, r'(?m)^SET ROLE')
        self.assertTrue(script.endswith((ROOT / 'deploy/offline/database-readiness.sql').read_text()))


class LifecycleContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calls = []
        self.cid = 'a' * 64
        self.container = rehearsal.Container(self.root, self.child, 'b' * 32)
        self.fail = None
        self.bad_identity = False

    def identity(self):
        return {'Id': self.cid, 'Image': rehearsal.IMAGE_ID,
                'Name': '/' + self.container.name,
                'Config': {'Image': rehearsal.IMAGE, 'Labels': {rehearsal.LABEL: self.container.token}},
                'HostConfig': {'NetworkMode': 'none', 'PortBindings': {}, 'PublishAllPorts': False,
                               'Binds': None, 'Privileged': False, 'ReadonlyRootfs': True,
                               'Tmpfs': rehearsal.TMPFS},
                'Mounts': []}

    def child(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if args[0] == 'create':
            self.container.cidfile.write_text(self.cid)
            if self.fail == 'create': return 1, b''
            return 0, (self.cid + '\n').encode()
        if args[0:2] == ['container', 'inspect']:
            data = self.identity()
            if self.bad_identity: data['Config']['Labels'] = {}
            return 0, payload([data])
        if args[0] == 'start':
            return (1 if self.fail == 'start' else 0), b''
        if args[0] == 'rm':
            return (1 if self.fail == 'cleanup' else 0), self.cid.encode()
        raise AssertionError(args)

    def test_create_records_full_id_and_identity_before_start(self):
        self.container.create()
        self.assertEqual(self.container.cid, self.cid)
        self.assertEqual([a[0][0] for a in self.calls], ['create', 'container', 'start'])
        self.container.cleanup()
        self.assertEqual(self.calls[-1][0], ['rm', '--force', self.cid])

    def test_create_only_fixed_image_network_and_no_external_inputs(self):
        self.container.create()
        args = self.calls[0][0]
        self.assertIn(rehearsal.IMAGE, args)
        self.assertIn('--network=none', args)
        self.assertIn('--pull=never', args)
        self.assertIn('--log-driver=none', args)
        self.assertIn('--read-only', args)
        self.assertIn('--user=postgres', args)
        self.assertNotIn('--publish', args)
        self.assertNotIn('--volume', args)
        self.assertNotIn('--privileged', args)
        self.assertIn('listen_addresses=', args)

    def test_unknown_create_without_cid_never_cleans_by_name(self):
        def failed(args, **kwargs):
            self.calls.append((args, kwargs))
            return 1, b''
        self.container.child = failed
        with self.assertRaises(rehearsal.Blocked): self.container.create()
        with self.assertRaises(rehearsal.Blocked): self.container.cleanup()
        self.assertFalse(any(a[0][0] == 'rm' for a in self.calls))

    def test_failed_create_with_known_owned_cid_can_only_clean_that_id(self):
        self.fail = 'create'
        with self.assertRaises(rehearsal.Blocked): self.container.create()
        self.container.cleanup()
        self.assertEqual(self.calls[-1][0], ['rm', '--force', self.cid])
        self.assertNotIn('start', [a[0][0] for a in self.calls])

    def test_wrong_label_never_starts_or_removes(self):
        self.bad_identity = True
        with self.assertRaises(rehearsal.Blocked): self.container.create()
        with self.assertRaises(rehearsal.Blocked): self.container.cleanup()
        self.assertNotIn('start', [a[0][0] for a in self.calls])
        self.assertNotIn('rm', [a[0][0] for a in self.calls])

    def test_start_failure_cleans_owned_container_once(self):
        self.fail = 'start'
        with self.assertRaises(rehearsal.Blocked): self.container.create()
        self.container.cleanup()
        self.assertEqual(sum(a[0][0] == 'rm' for a in self.calls), 1)

    def test_cleanup_failure_is_not_success_and_is_not_retried(self):
        self.container.create(); self.fail = 'cleanup'
        with self.assertRaisesRegex(rehearsal.Blocked, '^CLEANUP_UNCERTAIN$'): self.container.cleanup()
        with self.assertRaises(rehearsal.Blocked): self.container.cleanup()
        self.assertEqual(sum(a[0][0] == 'rm' for a in self.calls), 1)

    def test_cid_symlink_and_truncated_cid_rejected(self):
        for content in ('abc', 'a' * 63, 'A' * 64, 'a' * 64 + '\nextra'):
            self.container.cidfile.write_text(content)
            with self.assertRaises(rehearsal.Blocked): self.container.record_cid()
        self.container.cidfile.unlink()
        target = self.root / 'target'; target.write_text(self.cid)
        self.container.cidfile.symlink_to(target)
        with self.assertRaises(rehearsal.Blocked): self.container.record_cid()

    def test_container_security_identity_changes_rejected(self):
        for field, value in [('NetworkMode', 'host'), ('PortBindings', {'5432/tcp': [{}]}),
                             ('PublishAllPorts', True), ('Binds', ['/host:/data']),
                             ('Privileged', True), ('ReadonlyRootfs', False), ('Tmpfs', {})]:
            data = self.identity(); data['HostConfig'][field] = value
            self.container.cid = self.cid
            with self.subTest(field=field), self.assertRaises(rehearsal.Blocked):
                self.container.verify_identity(payload([data]))


def case_document(case):
    value = baseline()
    changes = {
        'table_write': {'table_write_count': 2, 'column_write_count': 19},
        'column_write': {'column_write_count': 18},
        'membership': {'role_membership_count': 1},
        'owner': {'owned_object_count': 1, 'table_write_count': 2, 'column_write_count': 19},
        'role_superuser': {'role_superuser': True, 'database_create': True,
                           'schema_create_count': 4, 'table_write_count': 100, 'column_write_count': 1000},
        'role_create_db': {'role_create_db': True},
        'role_create_role': {'role_create_role': True},
        'role_replication': {'role_replication': True},
        'role_bypass_rls': {'role_bypass_rls': True},
        'wrong_head': {'migration_expected_head_count': 0},
        'multiple_heads': {'migration_row_count': 2},
        'sequence_write': {'sequence_write_count': 1},
        'routine_execute': {'routine_execute_count': 1},
        'extra_schema': {'unexpected_schema_count': 1},
        'unsupported_type': {'unsupported_type_count': 2},
    }
    if case in ('migration_view', 'expression_index', 'partial_index', 'no_select', 'missing_table'):
        value.update(migration_select_permitted=False, migration_row_count=None,
                     migration_expected_head_count=None)
        if case != 'no_select': value['migration_table_supported'] = False
        if case == 'missing_table': value['migration_table_present'] = False
        if case == 'migration_view': value['unsupported_relation_count'] = 1
    value.update(changes.get(case, {}))
    return value


class OrchestrationContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'run'
        self.root.mkdir()
        self.calls = []
        self.cid = 'a' * 64
        self.fail = None
        self.case = None
        self.cidfile = None

    def child(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if args[0] == 'git': return 0, b'1' * 40 + b'\n'
        if args[0] == sys.executable:
            self.assertIn('-I', args)
            self.assertEqual(args[-2], '--evidence')
            value = checker.check_bytes(Path(args[-1]).read_bytes())
            if self.fail == 'checker': return 0, payload(value)
            return 1, payload(value)
        self.assertEqual(args[:3], ['/usr/bin/docker', '--context', 'default'])
        args = args[3:]
        if args[:2] == ['context', 'inspect']:
            host = 'tcp://SECRET' if self.fail == 'remote' else 'unix:///var/run/docker.sock'
            return 0, payload([{'Endpoints': {'docker': {'Host': host}}}])
        if args[0] == 'info':
            return 0, payload({'OSType': 'linux', 'Architecture': 'amd64', 'DockerRootDir': '/var/lib/docker'})
        if args[0] == 'pull':
            if self.fail == 'pull': return 1, b'SECRET'
            return 0, b''
        if args[:2] == ['image', 'inspect']:
            return 0, payload([{'Id': 'bad' if self.fail == 'image' else rehearsal.IMAGE_ID,
                'Os': 'linux', 'Architecture': 'amd64', 'RepoDigests': [rehearsal.IMAGE]}])
        if args[0] == 'create':
            self.cidfile = Path(args[args.index('--cidfile') + 1])
            self.name = args[args.index('--name') + 1]
            self.token = args[args.index('--label') + 1].split('=', 1)[1]
            if self.fail == 'create_unknown': return 1, b''
            self.cidfile.write_text(self.cid)
            return 0, self.cid.encode()
        if args[:2] == ['container', 'inspect']:
            return 0, payload([{'Id': self.cid, 'Image': rehearsal.IMAGE_ID, 'Name': '/' + self.name,
                'Config': {'Image': rehearsal.IMAGE, 'Labels': {rehearsal.LABEL: self.token}},
                'HostConfig': {'NetworkMode': 'none', 'PortBindings': {}, 'PublishAllPorts': False,
                              'Binds': None, 'Privileged': False, 'ReadonlyRootfs': True, 'Tmpfs': rehearsal.TMPFS},
                'Mounts': []}])
        if args[0] == 'start': return 0, b''
        if args[0] == 'rm': return (1 if self.fail == 'cleanup' else 0), self.cid.encode()
        if args[0] == 'exec' and 'sh' in args:
            return (1 if self.fail == 'startup' else 0), b''
        if args[0] == 'exec' and 'psql' in args:
            script = kwargs['input'].decode()
            if script.startswith('SET SESSION AUTHORIZATION'):
                self.case = script.split(';', 1)[0].split('slc_', 1)[1]
                if self.fail == 'collector_timeout': raise rehearsal.Blocked('COMMAND_TIMEOUT')
                if self.fail == 'interrupt': raise KeyboardInterrupt()
                if self.fail == 'generic': raise OSError('SECRET')
                if self.fail == 'collector_exit': return 1, payload(case_document(self.case))
                if self.fail == 'collector_json': return 0, b'SECRET'
                value = case_document(self.case)
                if self.fail == 'wrong_fields': value['transaction_read_only'] = False
                return 0, payload(value)
            if self.fail == 'fixture': return 1, b'SECRET'
            return 0, b''
        raise AssertionError(args)

    def run_mock(self):
        with patch.object(rehearsal.tempfile, 'mkdtemp', return_value=str(self.root)), \
             patch.object(rehearsal, 'host_environment', return_value={'PATH': '/usr/bin:/bin'}), \
             patch.object(rehearsal.shutil, 'which', return_value='/usr/bin/docker'), \
             patch.object(rehearsal.shutil, 'disk_usage') as disk, \
             patch.object(rehearsal, 'run_child', side_effect=self.child), \
             patch.object(rehearsal.time, 'sleep'), patch.dict(rehearsal.os.environ, {}, clear=True):
            disk.return_value.free = rehearsal.MIN_FREE
            return rehearsal.run_rehearsal()

    def operation_count(self, name):
        return sum(len(args) > 3 and args[0] == '/usr/bin/docker' and args[3] == name
                   for args, _ in self.calls)

    def test_full_mock_cases_and_independent_checker_before_success(self):
        report, code = self.run_mock()
        self.assertEqual((code, report['status']), (0, rehearsal.SUCCESS))
        self.assertEqual(report['cases_passed'], 21)
        self.assertEqual(report['checklist_mismatches'], 21)
        self.assertTrue(report['container_removed'])
        self.assertEqual(self.operation_count('create'), 1)
        self.assertEqual(self.operation_count('rm'), 1)
        self.assertEqual(sum(args[0] == sys.executable for args, _ in self.calls), 21)
        self.assertFalse(self.root.exists())

    def test_remote_daemon_rejected_before_pull(self):
        self.fail = 'remote'; report, code = self.run_mock()
        self.assertEqual(code, 2)
        self.assertEqual(report['reason'], 'LOCAL_DOCKER_REQUIRED')
        self.assertEqual(self.operation_count('pull'), 0)
        self.assertNotIn('SECRET', json.dumps(report))

    def test_pull_failure_is_not_retried(self):
        self.fail = 'pull'; report, code = self.run_mock()
        self.assertEqual(code, 2)
        self.assertEqual(self.operation_count('pull'), 1)
        self.assertEqual(self.operation_count('create'), 0)

    def test_image_mismatch_does_not_create_container(self):
        self.fail = 'image'; report, code = self.run_mock()
        self.assertEqual(code, 2)
        self.assertEqual(self.operation_count('create'), 0)

    def test_unknown_create_keeps_private_custody_without_cleanup(self):
        self.fail = 'create_unknown'; report, code = self.run_mock()
        self.assertEqual((code, report['reason']), (2, 'CLEANUP_UNCERTAIN'))
        self.assertEqual(self.operation_count('rm'), 0)
        self.assertTrue((self.root / 'custody.json').is_file())

    def test_startup_polling_is_bounded_and_cleanup_runs(self):
        self.fail = 'startup'; report, code = self.run_mock()
        self.assertEqual((code, report['reason']), (2, 'STARTUP_TIMEOUT'))
        self.assertEqual(self.operation_count('exec'), 60)
        self.assertEqual(self.operation_count('rm'), 1)

    def test_fixture_failure_does_not_collect_or_retry(self):
        self.fail = 'fixture'; report, code = self.run_mock()
        self.assertEqual((code, report['cases_passed']), (2, 0))
        self.assertIsNone(self.case)
        self.assertEqual(self.operation_count('rm'), 1)

    def test_psql_nonzero_is_collector_failure_not_expected_mismatch(self):
        self.fail = 'collector_exit'; report, code = self.run_mock()
        self.assertEqual((code, report['reason']), (2, 'COLLECTOR_ERROR'))
        self.assertEqual(report['cases_passed'], 0)
        self.assertEqual(self.operation_count('rm'), 1)

    def test_collector_timeout_is_not_success(self):
        self.fail = 'collector_timeout'; report, code = self.run_mock()
        self.assertEqual((code, report['reason']), (2, 'COLLECTOR_ERROR'))
        self.assertEqual(self.operation_count('rm'), 1)

    def test_interruption_still_attempts_owned_cleanup(self):
        self.fail = 'interrupt'; report, code = self.run_mock()
        self.assertEqual(code, 2)
        self.assertEqual(self.operation_count('rm'), 1)

    def test_malformed_collector_output_does_not_run_checker(self):
        self.fail = 'collector_json'; report, code = self.run_mock()
        self.assertEqual(code, 2)
        self.assertFalse(any(args[0] == sys.executable for args, _ in self.calls))
        self.assertNotIn('SECRET', json.dumps(report))

    def test_wrong_fields_do_not_count_case_as_passed(self):
        self.fail = 'wrong_fields'; report, code = self.run_mock()
        self.assertEqual((code, report['cases_passed']), (2, 0))

    def test_wrong_checker_exit_blocks(self):
        self.fail = 'checker'; report, code = self.run_mock()
        self.assertEqual((code, report['reason']), (2, 'CHECKER_ERROR'))
        self.assertEqual(report['cases_passed'], 0)

    def test_failed_cleanup_overrides_all_passed_cases_and_preserves_state(self):
        self.fail = 'cleanup'; report, code = self.run_mock()
        self.assertEqual((code, report['reason']), (2, 'CLEANUP_UNCERTAIN'))
        self.assertEqual(report['cases_passed'], 21)
        self.assertEqual(self.operation_count('rm'), 1)
        self.assertTrue(self.root.exists())

    def test_raw_exception_not_disclosed(self):
        self.fail = 'generic'; report, code = self.run_mock()
        self.assertEqual(code, 2)
        self.assertNotIn('SECRET', json.dumps(report))


class StaticContracts(unittest.TestCase):
    def test_image_is_verified_immutable_official_linux_amd64(self):
        self.assertEqual(rehearsal.IMAGE, 'postgres@sha256:5983db9a9c6ad225a48a46cfe2e03e6680b1826662befd0465eb05b34cb1c64e')
        self.assertEqual(rehearsal.IMAGE_ID, 'sha256:cadebe7c08430c896edac883fa92f8de2c36e330805e770fbee8a7eae13f144f')

    def test_image_identity_tampering_rejected(self):
        image = {'Id': rehearsal.IMAGE_ID, 'Os': 'linux', 'Architecture': 'amd64', 'RepoDigests': [rehearsal.IMAGE]}
        rehearsal.verify_image(payload([image]))
        for field, value in [('Id', 'sha256:' + '0' * 64), ('Architecture', 'arm64'), ('Os', 'windows'), ('RepoDigests', [])]:
            bad = dict(image); bad[field] = value
            with self.subTest(field=field), self.assertRaises(rehearsal.Blocked): rehearsal.verify_image(payload([bad]))

    def test_host_overrides_are_rejected_without_daemon_or_download(self):
        for key in rehearsal.FORBIDDEN_ENV:
            with patch.dict(rehearsal.os.environ, {key: 'SECRET'}, clear=True), self.assertRaises(rehearsal.Blocked):
                rehearsal.host_environment(ROOT)

    def test_runner_hides_stderr_and_enforces_output_and_time_limits(self):
        # Only local Python children; never Docker or database processes.
        env = {'PATH': '/usr/bin:/bin'}
        with self.assertRaisesRegex(rehearsal.Blocked, '^COMMAND_OUTPUT_LIMIT$'):
            rehearsal.run_child([sys.executable, '-c', 'print("x" * 20000)'], env=env, limit=100, timeout=5)
        with self.assertRaisesRegex(rehearsal.Blocked, '^COMMAND_TIMEOUT$'):
            rehearsal.run_child([sys.executable, '-c', 'import time; time.sleep(10)'], env=env, timeout=.05)
        code, out = rehearsal.run_child([sys.executable, '-c', 'import sys; print("SECRET", file=sys.stderr); print("ok")'], env=env)
        self.assertEqual((code, out), (0, b'ok\n'))

    def test_manual_workflow_is_separate_and_minimal(self):
        text = (ROOT / '.github/workflows/offline-database-rehearsal.yml').read_text()
        self.assertIn('workflow_dispatch:', text)
        self.assertIn('contents: read', text)
        self.assertIn('runs-on: ubuntu-24.04', text)
        self.assertIn('timeout-minutes: 30', text)
        self.assertIn('cancel-in-progress: false', text)
        self.assertIn('actions/checkout@11d5960a326750d5838078e36cf38b85af677262', text)
        self.assertIn('persist-credentials: false', text)
        self.assertIn('offline_database_rehearsal.py --run', text)
        for prohibited in ('pull_request:', 'push:', 'schedule:', 'workflow_call:', 'upload-artifact',
                           'actions/cache', 'setup-python', 'self-hosted', 'docker logs', 'services:'):
            self.assertNotIn(prohibited, text)


if __name__ == '__main__':
    unittest.main()
