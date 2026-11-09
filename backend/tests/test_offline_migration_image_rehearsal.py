"""Synthetic contracts only: no downloads, Docker, Alembic or database execution."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import tarfile
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.find_spec('offline_migration_image_rehearsal')
if SPEC:
    import offline_migration_image_rehearsal as rehearsal
else:
    rehearsal = None
COMMIT = 'a' * 40
IMAGE = 'sha256:' + 'b' * 64


class MigrationImageTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(rehearsal, 'independent migration image rehearsal is missing')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_cli_needs_explicit_run_and_exact_commit(self):
        for argv in ([], ['--run'], ['--expected-commit', COMMIT], ['--run', '--expected-commit', 'main'],
                     ['--run', '--expected-commit', COMMIT, '--database-url', 'PRIVATE']):
            with self.subTest(argv=argv), patch.object(rehearsal, 'run', side_effect=AssertionError('must not execute')), \
                 patch('sys.stderr', new_callable=io.StringIO) as error:
                self.assertEqual(rehearsal.main(argv), 2)
                self.assertNotIn('PRIVATE', error.getvalue())

    def test_strict_receipts_reject_aliases_duplicates_and_numbers(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}', b'{"a":1.5}', b'[]'):
            with self.subTest(raw=raw), self.assertRaises(rehearsal.Blocked): rehearsal.document(raw)
        self.assertFalse(rehearsal.exact({'a': True}, {'a': 1}))

    def test_prepared_receipt_is_completion_not_manifest_existence(self):
        value = rehearsal.input_receipt(COMMIT, 'c' * 64, prepared=True)
        self.assertEqual(rehearsal.validate_input_receipt(value, COMMIT, prepared=True), 'c' * 64)
        for changed in ({'status': 'MIGRATION_INPUTS_VERIFIED_NOT_EXECUTED'}, {'source_commit': 'd' * 40},
                        {'migration_count': True}, {'image_built': True}, {'extra': 'PRIVATE'},
                        {'manifest_sha256': 'x' * 64}, {'database_connected': 0}):
            with self.subTest(changed=changed), self.assertRaises(rehearsal.Blocked):
                rehearsal.validate_input_receipt(value | changed, COMMIT, prepared=True)

    def image(self):
        return [{'Id': IMAGE, 'Os': 'linux', 'Architecture': 'amd64', 'Variant': '', 'Config': {
            'Labels': {'org.opencontainers.image.revision': COMMIT}, 'User': '65532:65532',
            'WorkingDir': '/app', 'Entrypoint': ['/bin/false'], 'Cmd': [], 'Volumes': None,
            'Healthcheck': None, 'OnBuild': [], 'ExposedPorts': None,
            'Env': ['PATH=/usr/local/bin:/usr/bin:/bin', 'LANG=C.UTF-8', 'PYTHON_VERSION=3.12.14']}}]

    def test_image_schema_is_separate_fail_closed_and_typed(self):
        self.assertEqual(rehearsal.verify_image(self.image(), IMAGE, COMMIT)['PYTHON_VERSION'], '3.12.14')
        for key, value in [('User', '0'), ('WorkingDir', '/'), ('Entrypoint', ['alembic']),
                           ('Cmd', ['current']), ('Volumes', {'/data': {}}), ('OnBuild', ['RUN x']),
                           ('ExposedPorts', {'5432/tcp': {}}), ('Healthcheck', {'Test': ['CMD', 'x']}),
                           ('Env', ['PYTHON_VERSION=3.12.14', 'DATABASE_URL=PRIVATE']),
                           ('Env', ['PYTHON_VERSION=3.12.14', 'PYTHON_VERSION=3.12.14'])]:
            data = self.image(); data[0]['Config'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(rehearsal.Blocked):
                rehearsal.verify_image(data, IMAGE, COMMIT)
        for key, value in [('Id', 'sha256:' + 'c' * 64), ('Architecture', 'arm64'), ('Variant', 'v8')]:
            data = self.image(); data[0][key] = value
            with self.subTest(key=key), self.assertRaises(rehearsal.Blocked): rehearsal.verify_image(data, IMAGE, COMMIT)

    def test_budget_is_shared_and_reserves_cleanup_before_start(self):
        with patch.object(rehearsal.time, 'monotonic', return_value=100):
            budget = rehearsal.Budget(100)
            self.assertEqual(budget.allowance(1800, 500), 1800)
        with patch.object(rehearsal.time, 'monotonic', return_value=3350):
            with self.assertRaises(rehearsal.Blocked): budget.allowance(10, 50)
        for stamp in ('0', '-1', 'PRIVATE', str(101 * 10**9), str(1)):
            with patch.object(rehearsal.time, 'monotonic_ns', return_value=4000 * 10**9), \
                 patch.dict(os.environ, {'MIGRATION_REHEARSAL_STARTED_NS': stamp}, clear=True), \
                 self.assertRaises(rehearsal.Blocked): rehearsal.Budget.from_environment()

    def test_build_sources_include_new_driver_workflow_and_transitive_fetch_tools(self):
        self.assertTrue({'scripts/offline_migration_image_rehearsal.py',
                         '.github/workflows/offline-migration-image-rehearsal.yml',
                         'scripts/offline_image_rehearsal.py', 'scripts/offline_image_bundle.py',
                         'scripts/offline_readonly_preflight.py', 'scripts/offline_npm_artifacts.py',
                         'scripts/offline_npm_inventory.py'} <= rehearsal.BUILD_SOURCES)
        self.assertNotIn('frontend/package-lock.json', rehearsal.BUILD_SOURCES)

    def test_download_only_uses_reviewed_thirty_wheels(self):
        sources = {name: (ROOT / name).read_bytes() for name in rehearsal.migration.FIXED_SOURCES}
        inventory = json.loads(sources['backend/offline-python-wheelhouse.json'])
        with patch.dict(os.environ, {}, clear=True), patch.object(rehearsal.fetcher, 'fetch') as fetch:
            rehearsal.acquire_wheels(inventory, self.root)
        self.assertEqual(fetch.call_count, 30)
        self.assertTrue(all(call.args[2] == 'sha256' for call in fetch.call_args_list))
        self.assertEqual({call.args[0]['filename'] for call in fetch.call_args_list},
                         {item['filename'] for item in inventory['artifacts']})

    def test_download_failure_does_not_retry(self):
        inventory = json.loads((ROOT / 'backend/offline-python-wheelhouse.json').read_bytes())
        with patch.dict(os.environ, {}, clear=True), patch.object(rehearsal.fetcher, 'fetch', side_effect=ValueError('PRIVATE')) as fetch:
            with self.assertRaises(Exception): rehearsal.acquire_wheels(inventory, self.root)
        self.assertLessEqual(fetch.call_count, 4)

    def test_probe_is_dependency_and_static_source_only(self):
        text = rehearsal.PROBE
        self.assertIn('psycopg.pq.__impl__', text)
        self.assertIn('importlib.metadata.version', text)
        self.assertIn('compile(', text)
        self.assertIn('ast.parse(', text)
        self.assertNotIn('import app', text)
        self.assertNotIn('runpy', text)
        for forbidden in ('upgrade', 'downgrade', 'create_engine', 'alembic.command', 'socket.connect', 'sqlalchemy.text'):
            self.assertNotIn(forbidden, text)

    def test_container_commands_are_fixed_and_isolated(self):
        container = rehearsal.Container(self.root, lambda *_a, **_k: (0, b''), IMAGE, COMMIT,
                                         self.image()[0]['Config']['Env'], 'default', {})
        args = container.create_args()
        for value in ('--network=none', '--pull=never', '--read-only', '--user=65532:65532',
                      '--cap-drop=ALL', '--security-opt=no-new-privileges', '--log-driver=none', '--restart=no'):
            self.assertIn(value, args)
        self.assertEqual(args[-1], IMAGE)
        self.assertNotIn('--entrypoint', args)
        self.assertFalse(any(value.startswith(('--publish', '--volume', '--mount', '--env-file')) for value in args))

    def test_probe_expected_files_excludes_context_only_material(self):
        sources = {'backend/app/a.py': b'x=1', 'backend/alembic/env.py': b'x=2',
                   'backend/alembic/versions/0001_a.py': b'x=3', 'backend/alembic.ini': b'[alembic]',
                   'backend/requirements.txt': b'x', 'scripts/offline_migration_context.py': b'x'}
        inventory = json.loads((ROOT / 'backend/offline-python-wheelhouse.json').read_bytes())
        expected = rehearsal.probe_expectations(sources, inventory)
        self.assertEqual(set(expected['files']), {'app/a.py', 'alembic/env.py', 'alembic/versions/0001_a.py', 'alembic.ini'})
        self.assertEqual(len(expected['versions']), 30)

    def test_workflow_is_manual_standard_readonly_bounded_without_upload(self):
        text = (ROOT / '.github/workflows/offline-migration-image-rehearsal.yml').read_text()
        for required in ('workflow_dispatch:', 'contents: read', 'runs-on: ubuntu-24.04',
                         'timeout-minutes: 60', 'cancel-in-progress: false', 'persist-credentials: false'):
            self.assertIn(required, text)
        for forbidden in ('pull_request:', 'push:', 'schedule:', 'upload-artifact', 'cache:', 'setup-python',
                          'npm ', 'services:', 'secrets.', 'self-hosted'):
            self.assertNotIn(forbidden, text)

    def test_main_does_not_leak_error_or_publish_success_after_failure(self):
        with patch.object(rehearsal, 'run', side_effect=ValueError('PRIVATE')), \
             patch('sys.stderr', new_callable=io.StringIO) as error, patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(rehearsal.main(['--run', '--expected-commit', COMMIT]), 2)
            self.assertEqual(output.getvalue(), '')
            self.assertNotIn('PRIVATE', error.getvalue())

    def test_source_snapshot_failure_prevents_every_external_stage(self):
        with patch.object(rehearsal, 'source_child', side_effect=rehearsal.Blocked('SOURCE_REJECTED')), \
             patch.object(rehearsal, 'host') as host, patch.object(rehearsal, 'acquire_wheels') as acquire:
            with self.assertRaises(rehearsal.Blocked): rehearsal.run(COMMIT, root=self.root)
            host.assert_not_called(); acquire.assert_not_called()


    def test_acquisition_has_separate_bounded_child_not_unbounded_pool_wait(self):
        inventory = json.loads((ROOT / 'backend/offline-python-wheelhouse.json').read_bytes())
        with patch.object(rehearsal, 'command', return_value=(0, b'')) as child:
            rehearsal.acquire_child(inventory, self.root, {'PATH': '/usr/bin:/bin'}, 123)
        args = child.call_args.args[0]
        self.assertEqual(args[:4], [sys.executable, '-I', '-B', '-c'])
        self.assertEqual(json.loads(args[-2]), inventory)
        self.assertEqual(child.call_args.kwargs['timeout'], 123)
        for result in ((1, b''), (0, b'PRIVATE')):
            with patch.object(rehearsal, 'command', return_value=result), self.assertRaises(rehearsal.Blocked):
                rehearsal.acquire_child(inventory, self.root, {}, 10)

    def test_bounded_command_real_synthetic_children_without_network(self):
        env = {'PATH': '/usr/bin:/bin'}
        code, raw = rehearsal.command([sys.executable, '-I', '-B', '-c', "print('ok'); raise SystemExit(7)"],
                                      env=env, timeout=5)
        self.assertEqual((code, raw), (7, b'ok\n'))
        for text, options in (("print('x'*5000)", {'limit': 1024, 'timeout': 5}),
                              ('import time; time.sleep(2)', {'timeout': .05})):
            with self.subTest(text=text), self.assertRaises(rehearsal.Blocked):
                rehearsal.command([sys.executable, '-I', '-B', '-c', text], env=env, **options)

    def context_fixture(self):
        from test_offline_migration_context import MigrationInputsTests
        helper = MigrationInputsTests(); helper.setUp()
        self.addCleanup(helper.doCleanups)
        return helper.prepare()

    def test_build_snapshot_contains_only_exact_verified_context_bytes(self):
        path, receipt = self.context_fixture()
        target = self.root / 'input.tar'
        digest = rehearsal.build_snapshot(path, COMMIT, receipt['manifest_sha256'], target)
        self.assertEqual(digest, hashlib.sha256(target.read_bytes()).hexdigest())
        manifest = json.loads((path / rehearsal.migration.MANIFEST).read_bytes())
        with tarfile.open(target, 'r:') as archive:
            self.assertEqual(set(archive.getnames()), set(manifest['files']) | {rehearsal.migration.MANIFEST})
            self.assertTrue(all(item.isfile() and item.uid == item.gid == item.mtime == 0 for item in archive.getmembers()))
            for item in archive.getmembers():
                self.assertEqual(archive.extractfile(item).read(), (path / item.name).read_bytes())
        with self.assertRaises(FileExistsError):
            rehearsal.build_snapshot(path, COMMIT, receipt['manifest_sha256'], target)

    def test_build_snapshot_rejects_changes_and_preserves_partial_output(self):
        path, receipt = self.context_fixture()
        target = self.root / 'input.tar'
        original = rehearsal.migration.read_at
        def changed(fd, name, limit):
            value = original(fd, name, limit)
            if name == 'app/main.py': return value + b'changed'
            return value
        # Keep the first full verify real; alter the copy's bytes only.
        verified = rehearsal.migration.verify
        calls = [0]
        def validate(*args):
            calls[0] += 1
            return verified(*args)
        with patch.object(rehearsal.migration, 'verify', side_effect=validate), \
             patch.object(rehearsal.migration, 'read_at', side_effect=changed), self.assertRaises(Exception):
            rehearsal.build_snapshot(path, COMMIT, receipt['manifest_sha256'], target)
        self.assertFalse(target.exists())
        with patch.object(rehearsal, 'MAX_TAR', 1), self.assertRaises(rehearsal.Blocked):
            rehearsal.build_snapshot(path, COMMIT, receipt['manifest_sha256'], target)
        self.assertTrue(target.exists())

    def container_fixture(self, kind='default', change=None, failure=None):
        state = {'exited': False, 'removed': False, 'calls': []}
        cid = 'c' * 64
        expected = {'files': {'app/a.py': {}}, 'versions': {}}
        def inspection(container):
            data = {'Id': cid, 'Image': IMAGE, 'Name': '/' + container.name, 'Path': container.entrypoint,
                    'Args': container.args, 'Config': {'Image': IMAGE, 'Labels': {
                        rehearsal.LABEL: container.token, 'org.opencontainers.image.revision': COMMIT},
                        'User': '65532:65532', 'WorkingDir': '/app', 'Entrypoint': [container.entrypoint],
                        'Cmd': container.args, 'Volumes': None, 'ExposedPorts': None,
                        'Healthcheck': {'Test': ['NONE']},
                        'Env': [key + '=' + value for key, value in container.env.items()]},
                    'HostConfig': {'NetworkMode': 'none', 'PublishAllPorts': False, 'Privileged': False,
                        'ReadonlyRootfs': True, 'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges'],
                        'Tmpfs': rehearsal.TMPFS, 'LogConfig': {'Type': 'none', 'Config': {}},
                        'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0}, 'PidMode': '',
                        'IpcMode': 'private', 'CgroupnsMode': 'private', 'Memory': 536870912,
                        'MemorySwap': 536870912, 'NanoCpus': 1000000000, 'PidsLimit': 64, 'ShmSize': 8388608},
                    'Mounts': [], 'NetworkSettings': {'Ports': None, 'Networks': {'none': {
                        'IPAddress': '', 'GlobalIPv6Address': '', 'Gateway': ''}}},
                    'State': {'Status': 'exited' if state['exited'] else 'created', 'Running': False,
                        'Paused': False, 'Restarting': False, 'Dead': False, 'OOMKilled': False,
                        'ExitCode': 1 if kind == 'default' else 0, 'Error': ''}}
            if change: change(data, state)
            return json.dumps([data]).encode()
        def child(args, **kwargs):
            state['calls'].append(args)
            if args[0] == 'create':
                if failure != 'missing_cid': container.cidfile.write_text(cid + '\n')
                if failure in ('create_uncertain', 'missing_cid'): raise rehearsal.Blocked('COMMAND_TIMEOUT_UNCERTAIN')
                return 0, (cid + '\n').encode()
            if args[:2] == ['container', 'inspect']: return 0, inspection(container)
            if args[0] == 'start':
                state['exited'] = True
                if failure == 'start_interrupt': raise KeyboardInterrupt()
                if kind == 'default': return 1, b''
                raw = {'status': 'MIGRATION_DEPENDENCIES_AND_SOURCE_VERIFIED', 'wheel_count': 30,
                       'migration_count': 29, 'source_file_count': 1, 'database_connected': False,
                       'migrations_executed': False}
                if failure == 'probe_alias': raw['database_connected'] = 0
                return 0, json.dumps(raw).encode()
            if args[:2] == ['rm', '--force']:
                if failure == 'remove_uncertain': raise rehearsal.Blocked('COMMAND_TIMEOUT_UNCERTAIN')
                state['removed'] = True
                return 0, (cid + '\n').encode()
            raise AssertionError(args)
        container = rehearsal.Container(self.root, child, IMAGE, COMMIT, self.image()[0]['Config']['Env'], kind, expected)
        return container, child, state

    def test_real_container_control_flow_with_all_docker_calls_mocked(self):
        for kind in ('default', 'dependencies'):
            container, child, state = self.container_fixture(kind)
            container.execute(); container.cleanup(child)
            self.assertTrue(container.cleaned and state['removed'])
            self.assertEqual(sum(args[0] == 'create' for args in state['calls']), 1)
            self.assertEqual(sum(args[0] == 'start' for args in state['calls']), 1)
            self.assertEqual([args for args in state['calls'] if args[0] == 'rm'], [['rm', '--force', 'c' * 64]])

    def test_container_identity_or_isolation_changes_stop_before_start_and_removal(self):
        mutations = [lambda d, s: d['Config'].update(Image='untrusted'),
                     lambda d, s: d['HostConfig'].update(NetworkMode='bridge'),
                     lambda d, s: d['HostConfig'].update(Memory=True),
                     lambda d, s: d['Config']['Labels'].update({rehearsal.LABEL: 'other'}),
                     lambda d, s: d.update(Mounts=[{'Type': 'bind', 'Destination': '/tmp'}]),
                     lambda d, s: d['Config']['Env'].append('DATABASE_URL=PRIVATE')]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                old = self.root; self.root = Path(directory)
                try:
                    container, child, state = self.container_fixture(change=mutation)
                    with self.assertRaises(rehearsal.Blocked): container.execute()
                    with self.assertRaises(rehearsal.Blocked): container.cleanup(child)
                    self.assertFalse(any(args[0] in ('start', 'rm') for args in state['calls']))
                finally: self.root = old

    def test_default_requires_actual_exit_one_without_oom_or_daemon_error(self):
        mutations = [lambda d, s: d['State'].update(ExitCode=0) if s['exited'] else None,
                     lambda d, s: d['State'].update(ExitCode=True) if s['exited'] else None,
                     lambda d, s: d['State'].update(OOMKilled=True) if s['exited'] else None,
                     lambda d, s: d['State'].update(Error='PRIVATE') if s['exited'] else None,
                     lambda d, s: d['State'].update(Status='created') if s['exited'] else None]
        for mutation in mutations:
            with tempfile.TemporaryDirectory() as directory:
                old = self.root; self.root = Path(directory)
                try:
                    container, child, state = self.container_fixture(change=mutation)
                    with self.assertRaises(rehearsal.Blocked): container.execute()
                    container.cleanup(child)
                    self.assertTrue(state['removed'])
                finally: self.root = old

    def test_uncertain_create_interrupt_and_cleanup_never_retry(self):
        for failure in ('create_uncertain', 'missing_cid', 'start_interrupt', 'remove_uncertain', 'probe_alias'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                old = self.root; self.root = Path(directory)
                try:
                    container, child, state = self.container_fixture('dependencies', failure=failure)
                    if failure == 'remove_uncertain': container.execute()
                    else:
                        with self.assertRaises((Exception, KeyboardInterrupt)): container.execute()
                    if failure in ('missing_cid', 'remove_uncertain'):
                        with self.assertRaises(rehearsal.Blocked): container.cleanup(child)
                    else:
                        container.cleanup(child)
                        self.assertTrue(container.cleaned)
                    if failure == 'missing_cid': self.assertFalse(any(args[0] == 'rm' for args in state['calls']))
                    if failure == 'remove_uncertain':
                        with self.assertRaises(rehearsal.Blocked): container.cleanup(child)
                    self.assertLessEqual(sum(args[0] == 'create' for args in state['calls']), 1)
                    self.assertLessEqual(sum(args[0] == 'start' for args in state['calls']), 1)
                    self.assertLessEqual(sum(args[0] == 'rm' for args in state['calls']), 1)
                    self.assertTrue((self.root / 'dependencies-custody.json').exists())
                finally: self.root = old

    def run_fixture(self, *, prepared=None, verified=None, command_change=None, container_failure=None):
        from contextlib import ExitStack
        stack = ExitStack(); self.addCleanup(stack.close)
        sources = {'backend/app/a.py': b'pass'}
        inventory = json.loads((ROOT / 'backend/offline-python-wheelhouse.json').read_bytes())
        digest = 'd' * 64; calls = []
        prepared = prepared if prepared is not None else rehearsal.input_receipt(COMMIT, digest, prepared=True)
        verified = verified if verified is not None else rehearsal.input_receipt(COMMIT, digest, prepared=False)
        stack.enter_context(patch.dict(os.environ, {}, clear=True))
        stack.enter_context(patch.object(rehearsal, 'source_child', return_value=(inventory, rehearsal.probe_expectations(sources, inventory))))
        stack.enter_context(patch.object(rehearsal, 'host', return_value=(['docker'], {})))
        acquire = stack.enter_context(patch.object(rehearsal, 'acquire_child'))
        contexts = stack.enter_context(patch.object(rehearsal, 'context_child', side_effect=[prepared, verified]))
        def snapshot(context, commit, value, target, env, timeout):
            target.write_bytes(b'synthetic validated tar')
            return hashlib.sha256(target.read_bytes()).hexdigest()
        snapshots = stack.enter_context(patch.object(rehearsal, 'build_snapshot_child', side_effect=snapshot))
        def command(args, **kwargs):
            calls.append(args)
            if command_change:
                changed = command_change(args, kwargs)
                if changed is not None: return changed
            if args[1] == 'pull': return 0, b''
            if args[1:3] == ['image', 'inspect']:
                if args[3] == rehearsal.migration.BASE:
                    return 0, json.dumps([{'Id': rehearsal.migration.BASE_CONFIG, 'Os': 'linux', 'Architecture': 'amd64'}]).encode()
                return 0, json.dumps(self.image()).encode()
            if args[1] == 'build':
                self.assertEqual(kwargs['stdin'].read(), b'synthetic validated tar')
                Path(args[args.index('--iidfile') + 1]).write_text(IMAGE + '\n')
                return 0, b''
            raise AssertionError(args)
        commands = stack.enter_context(patch.object(rehearsal, 'command', side_effect=command))
        containers = []
        class FakeContainer:
            def __init__(self, *args): self.cleaned = False; self.kind = args[-2]; containers.append(self)
            def execute(self):
                if container_failure == 'execute': raise KeyboardInterrupt()
            def cleanup(self, _child):
                if container_failure == 'cleanup': raise rehearsal.Blocked('CLEANUP_UNCERTAIN')
                self.cleaned = True
        stack.enter_context(patch.object(rehearsal, 'Container', FakeContainer))
        return acquire, contexts, snapshots, commands, calls, containers

    def test_complete_mock_run_prepares_verifies_builds_and_smokes_only_migration(self):
        acquire, contexts, snapshots, commands, calls, containers = self.run_fixture()
        result = rehearsal.run(COMMIT, root=self.root)
        self.assertEqual(result['status'], rehearsal.SUCCESS)
        self.assertEqual(result['containers_removed'], 2)
        self.assertFalse(result['database_connected']); self.assertFalse(result['migrations_executed'])
        self.assertEqual(acquire.call_count, 1); self.assertEqual(contexts.call_count, 2)
        self.assertEqual(contexts.call_args_list[1].args[0][-1], 'd' * 64)
        self.assertEqual(snapshots.call_count, 1)
        build = next(args for args in calls if args[1] == 'build')
        self.assertEqual(build[-1], '-')
        for value in ('--network=none', '--pull=false', '--no-cache', '--platform=linux/amd64', 'SOURCE_COMMIT=' + COMMIT):
            self.assertIn(value, build)
        self.assertFalse(any(value in ('save', 'load', 'push', 'compose', 'prune') for args in calls for value in args))
        self.assertEqual([container.kind for container in containers], ['default', 'dependencies'])

    def test_failed_prepare_or_independent_verify_never_builds(self):
        for name, change in [('prepared', {'status': 'MIGRATION_INPUTS_VERIFIED_NOT_EXECUTED'}),
                             ('prepared', {'database_connected': 0}), ('verified', {'manifest_sha256': 'e' * 64}),
                             ('verified', {'image_built': True})]:
            with self.subTest(name=name, change=change), tempfile.TemporaryDirectory() as directory:
                value = rehearsal.input_receipt(COMMIT, 'd' * 64, prepared=name == 'prepared') | change
                fixture = self.run_fixture(**{name: value})
                with self.assertRaises(rehearsal.Blocked): rehearsal.run(COMMIT, root=Path(directory))
                fixture[2].assert_not_called(); fixture[3].assert_not_called()
                self.assertEqual(fixture[-1], [])
                # Close patches before the next independent run.
                self.doCleanups()

    def test_build_failure_and_input_mutation_never_create_container(self):
        for mode in ('build_failure', 'mutated_archive', 'wrong_base'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                def changed(args, kwargs):
                    if args[1] == 'build':
                        if mode == 'build_failure': return 2, b'PRIVATE'
                        if mode == 'mutated_archive': (Path(directory) / 'build-context.tar').write_bytes(b'changed')
                    if mode == 'wrong_base' and args[1:3] == ['image', 'inspect']:
                        return 0, json.dumps([{'Id': IMAGE, 'Os': 'linux', 'Architecture': 'amd64'}]).encode()
                fixture = self.run_fixture(command_change=changed)
                with self.assertRaises(Exception): rehearsal.run(COMMIT, root=Path(directory))
                self.assertEqual(fixture[-1], [])
                self.doCleanups()

    def test_runtime_interrupt_cleanup_failure_never_return_success(self):
        for mode in ('execute', 'cleanup'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                fixture = self.run_fixture(container_failure=mode)
                with self.assertRaises((rehearsal.Blocked, KeyboardInterrupt)):
                    rehearsal.run(COMMIT, root=Path(directory))
                self.assertEqual(len(fixture[-1]), 1)
                if mode == 'execute': self.assertTrue(fixture[-1][0].cleaned)
                self.doCleanups()

    def test_main_restores_sigterm_on_exception_and_install_failure(self):
        for error in (ValueError('PRIVATE'), KeyboardInterrupt()):
            with patch.object(rehearsal.signal, 'getsignal', return_value='old'), \
                 patch.object(rehearsal.signal, 'signal') as handler, \
                 patch.object(rehearsal, 'run', side_effect=error), patch('sys.stderr', new_callable=io.StringIO):
                self.assertEqual(rehearsal.main(['--run', '--expected-commit', COMMIT]), 2)
                self.assertEqual(handler.call_args.args, (rehearsal.signal.SIGTERM, 'old'))
        with patch.object(rehearsal.signal, 'getsignal', return_value='old'), \
             patch.object(rehearsal.signal, 'signal', side_effect=[ValueError('PRIVATE'), None]) as handler, \
             patch.object(rehearsal, 'run') as run, patch('sys.stderr', new_callable=io.StringIO):
            self.assertEqual(rehearsal.main(['--run', '--expected-commit', COMMIT]), 2)
            run.assert_not_called()
            self.assertEqual(handler.call_args.args, (rehearsal.signal.SIGTERM, 'old'))


    def test_host_rejects_overrides_proxy_wrong_platform_space_and_missing_tools(self):
        cases = [({'DOCKER_HOST': ''}, {}, 'HOST_OVERRIDE_REJECTED'),
                 ({'HTTPS_PROXY': 'PRIVATE'}, {}, None),
                 ({}, {'platform': 'arm64'}, 'HOST_PLATFORM_REJECTED'),
                 ({}, {'space': 1}, 'HOST_SPACE_REQUIRED'),
                 ({}, {'docker': None}, 'EXISTING_DOCKER_REQUIRED')]
        for environment, options, reason in cases:
            with self.subTest(environment=environment, options=options), \
                 patch.dict(os.environ, environment, clear=True), \
                 patch.object(rehearsal.platform, 'machine', return_value=options.get('platform', 'x86_64')), \
                 patch.object(rehearsal.shutil, 'disk_usage', return_value=SimpleNamespace(free=options.get('space', rehearsal.MIN_FREE))), \
                 patch.object(rehearsal.shutil, 'which', return_value=options.get('docker', '/usr/bin/docker')), \
                 patch.object(rehearsal, 'command') as child:
                with self.assertRaises(Exception) as error: rehearsal.host(self.root, rehearsal.Budget(rehearsal.time.monotonic()))
                if reason: self.assertEqual(str(error.exception), reason)
                child.assert_not_called()

    def test_host_uses_local_socket_private_credentials_and_existing_build_capabilities(self):
        calls = []
        def child(args, **kwargs):
            calls.append((args, kwargs))
            if 'info' in args:
                return 0, json.dumps({'OSType': 'linux', 'Architecture': 'amd64', 'DockerRootDir': '/var/lib/docker'}).encode()
            if 'version' in args: return 0, b'{}'
            return 0, b'      --iidfile string\n      --network string\n      --platform string\n      --pull\n      --no-cache\n'
        with patch.dict(os.environ, {}, clear=True), patch.object(rehearsal.shutil, 'which', return_value='/usr/bin/docker'), \
             patch.object(rehearsal.shutil, 'disk_usage', return_value=SimpleNamespace(free=rehearsal.MIN_FREE)), \
             patch.object(rehearsal, 'command', side_effect=child):
            prefix, env = rehearsal.host(self.root, rehearsal.Budget(rehearsal.time.monotonic()))
        self.assertEqual(prefix, ['/usr/bin/docker', '--host=unix:///var/run/docker.sock'])
        self.assertEqual(set(env), {'PATH', 'HOME', 'DOCKER_CONFIG', 'DOCKER_BUILDKIT', 'LANG', 'PIP_CONFIG_FILE'})
        self.assertEqual(list(Path(env['DOCKER_CONFIG']).iterdir()), [])
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(args[:2] == prefix for args, _ in calls))

    def test_budget_expiring_before_runtime_does_not_create_and_never_extend_shared_deadline(self):
        fixture = self.run_fixture()
        original = rehearsal.Budget.reserve
        def reserve(budget, seconds):
            if seconds == 430: raise rehearsal.Blocked('BUDGET_EXHAUSTED')
            return original(budget, seconds)
        with patch.object(rehearsal.Budget, 'reserve', reserve), self.assertRaises(rehearsal.Blocked):
            rehearsal.run(COMMIT, root=self.root)
        self.assertEqual(fixture[-1], [])

    def test_real_local_git_source_binding_without_fetch_or_executing_source(self):
        from contextlib import ExitStack
        from test_offline_migration_context import MigrationInputsTests
        sources = MigrationInputsTests().sources()
        for name in rehearsal.BUILD_SOURCES: sources[name] = (ROOT / name).read_bytes()
        repo = self.root / 'repository'; repo.mkdir()
        for name, raw in sources.items():
            path = repo / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(self.root), 'GIT_CONFIG_NOSYSTEM': '1',
               'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0'}
        def git(*args):
            return subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', *args],
                                  cwd=repo, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, check=True).stdout
        git('init', '-q'); git('add', '.')
        git('-c', 'user.name=synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'synthetic')
        commit = git('rev-parse', 'HEAD').decode().strip()
        with ExitStack() as stack:
            stack.enter_context(patch.object(rehearsal, 'ROOT', repo))
            for name in rehearsal.BUILD_SOURCES:
                if name.startswith('scripts/'):
                    module = sys.modules[Path(name).stem]
                    stack.enter_context(patch.object(module, '__file__', str(repo / name)))
            result, inventory = rehearsal.source_inputs(commit)
            self.assertEqual(len(inventory['artifacts']), 30)
            self.assertEqual(result['backend/alembic/env.py'], sources['backend/alembic/env.py'])
            (repo / 'scripts/offline_image_rehearsal.py').write_bytes(b'raise RuntimeError("must never execute")')
            with self.assertRaises(Exception): rehearsal.source_inputs(commit)


    def test_source_stage_has_shared_bounded_process_before_host_or_download(self):
        self.assertTrue(hasattr(rehearsal, 'source_child'), 'source stage needs an aggregate bounded child')
        with patch.object(rehearsal, 'source_child', side_effect=rehearsal.Blocked('COMMAND_TIMEOUT_UNCERTAIN')) as source, \
             patch.object(rehearsal, 'host') as host, patch.object(rehearsal, 'acquire_child') as acquire:
            with self.assertRaises(rehearsal.Blocked): rehearsal.run(COMMIT, root=self.root)
            self.assertEqual(source.call_count, 1)
            self.assertGreater(source.call_args.args[-1], 0)
            self.assertLessEqual(source.call_args.args[-1], 600)
            host.assert_not_called(); acquire.assert_not_called()

    def test_build_snapshot_stage_has_shared_bounded_process_before_pull(self):
        self.assertTrue(hasattr(rehearsal, 'build_snapshot_child'), 'snapshot stage needs an aggregate bounded child')
        fixture = self.run_fixture()
        with patch.object(rehearsal, 'build_snapshot_child', side_effect=rehearsal.Blocked('COMMAND_TIMEOUT_UNCERTAIN')) as snapshot:
            with self.assertRaises(rehearsal.Blocked): rehearsal.run(COMMIT, root=self.root)
            self.assertEqual(snapshot.call_count, 1)
            self.assertGreater(snapshot.call_args.args[-1], 0)
            self.assertLessEqual(snapshot.call_args.args[-1], 180)
            fixture[3].assert_not_called()
            self.assertEqual(fixture[-1], [])


    def source_receipt_fixture(self):
        from test_offline_migration_context import MigrationInputsTests
        sources = MigrationInputsTests().sources()
        inventory = json.loads(sources['backend/offline-python-wheelhouse.json'])
        with patch.object(rehearsal, 'source_inputs', return_value=(sources, inventory)):
            return rehearsal.source_report(COMMIT)

    def execute_fixed_worker(self, args, **kwargs):
        self.assertEqual(args[:4], [sys.executable, '-I', '-B', '-c'])
        self.assertLessEqual(kwargs['timeout'], 600)
        output = io.StringIO()
        with patch.object(sys, 'argv', ['-c', *args[5:]]), patch('sys.stdout', output):
            exec(compile(args[4], '<fixed-worker>', 'exec'), {})
        return 0, output.getvalue().encode()

    def test_source_child_program_and_complete_strict_report(self):
        value = self.source_receipt_fixture()
        with patch.object(rehearsal, 'source_report', return_value=value), \
             patch.object(rehearsal, 'command', side_effect=self.execute_fixed_worker) as child:
            inventory, expected = rehearsal.source_child(COMMIT, {'PATH': '/usr/bin:/bin'}, 77)
        self.assertEqual(inventory, value['inventory']); self.assertEqual(expected, value['expected'])
        self.assertEqual(child.call_count, 1)
        self.assertEqual(child.call_args.kwargs['timeout'], 77)

    def test_source_child_rejects_incomplete_wrong_nested_types_and_tampering(self):
        original = self.source_receipt_fixture()
        mutations = [lambda v: v.update(source_commit='b' * 40), lambda v: v.update(extra='PRIVATE'),
                     lambda v: v.update(requirements=[]), lambda v: v['expected'].update(extra=False),
                     lambda v: v['expected']['versions'].update(alembic='other'),
                     lambda v: v['expected']['files'].pop('alembic/env.py'),
                     lambda v: v['expected']['files']['app/core/config.py'].update(size=True),
                     lambda v: v['expected']['files']['app/core/config.py'].update(sha256='x' * 64),
                     lambda v: v['expected']['files'].update({'../private': {'size': 0, 'sha256': 'a' * 64}}),
                     lambda v: v['inventory']['artifacts'].pop()]
        for mutation in mutations:
            value = copy.deepcopy(original); mutation(value)
            with self.subTest(mutation=mutation), patch.object(rehearsal, 'command', return_value=(0, json.dumps(value).encode())), \
                 self.assertRaises(Exception): rehearsal.source_child(COMMIT, {}, 77)
        for result in ((2, b'{}'), (0, b'{}'), (0, b'x' * 65537)):
            with patch.object(rehearsal, 'command', return_value=result), self.assertRaises(rehearsal.Blocked):
                rehearsal.source_child(COMMIT, {}, 77)

    def test_build_snapshot_child_program_real_synthetic_tar_and_exact_receipt(self):
        context, receipt = self.context_fixture(); target = self.root / 'worker.tar'
        with patch.object(rehearsal, 'command', side_effect=self.execute_fixed_worker) as child:
            digest = rehearsal.build_snapshot_child(context, COMMIT, receipt['manifest_sha256'], target, {}, 90)
        self.assertEqual(digest, hashlib.sha256(target.read_bytes()).hexdigest())
        self.assertEqual(child.call_count, 1)
        self.assertEqual(child.call_args.kwargs['timeout'], 90)

    def test_build_snapshot_child_never_uses_existing_tar_after_failure_or_wrong_receipt(self):
        target = self.root / 'partial.tar'; target.write_bytes(b'partial')
        correct = {'source_commit': COMMIT, 'context_manifest_sha256': 'd' * 64, 'build_context_sha256': 'e' * 64}
        for code, value in ((2, correct), (0, correct | {'source_commit': 'b' * 40}),
                            (0, correct | {'context_manifest_sha256': 'c' * 64}),
                            (0, correct | {'build_context_sha256': True}), (0, correct | {'extra': 0})):
            with patch.object(rehearsal, 'command', return_value=(code, json.dumps(value).encode())) as child, \
                 self.assertRaises(rehearsal.Blocked):
                rehearsal.build_snapshot_child(self.root / 'context', COMMIT, 'd' * 64, target, {}, 90)
            self.assertEqual(child.call_count, 1)
            self.assertEqual(target.read_bytes(), b'partial')

    def test_fd_hash_checks_deadline_between_and_after_reads(self):
        self.assertEqual(rehearsal.bounded_digest(io.BytesIO(b'abc'), 1), hashlib.sha256(b'abc').hexdigest())
        now = [100.0]
        class SlowRead(io.BytesIO):
            def read(self, size):
                result = super().read(size); now[0] += 2; return result
        with patch.object(rehearsal.time, 'monotonic', side_effect=lambda: now[0]), self.assertRaises(rehearsal.Blocked):
            rehearsal.bounded_digest(SlowRead(b'abc'), 1)
        with patch.object(rehearsal, 'MAX_TAR', 2), self.assertRaises(rehearsal.Blocked):
            rehearsal.bounded_digest(io.BytesIO(b'abc'), 1)

    def test_build_hash_timeout_never_starts_or_returns_success(self):
        for stage in ('before', 'after'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                fixture = self.run_fixture()
                calls = [0]; original = rehearsal.bounded_digest
                def digest(stream, timeout):
                    calls[0] += 1
                    if calls[0] == (1 if stage == 'before' else 2): raise rehearsal.Blocked('HASH_TIMEOUT')
                    return original(stream, timeout)
                with patch.object(rehearsal, 'bounded_digest', side_effect=digest), self.assertRaises(rehearsal.Blocked):
                    rehearsal.run(COMMIT, root=Path(directory))
                self.assertEqual(fixture[-1], [])
                self.assertEqual(sum(args[1] == 'build' for args in fixture[-2]), 0 if stage == 'before' else 1)
                self.doCleanups()


if __name__ == '__main__':
    unittest.main()
