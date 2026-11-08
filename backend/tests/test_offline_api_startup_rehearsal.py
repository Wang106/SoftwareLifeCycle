"""Mock-only API startup contracts; never start Docker, an API or a database."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import offline_api_startup_rehearsal as rehearsal

IMAGE = 'sha256:' + 'a' * 64
COMMIT = 'b' * 40
CID = 'c' * 64
TOKEN = 'd' * 32


def raw(value):
    return json.dumps(value).encode()


def image_document():
    return [{'Id': IMAGE, 'Os': 'linux', 'Architecture': 'amd64',
             'Config': {'User': '65532:65532', 'WorkingDir': '/app',
                        'Entrypoint': ['/bin/false'], 'Cmd': [], 'Volumes': None,
                        'Healthcheck': None, 'OnBuild': None,
                        'Labels': {'org.opencontainers.image.revision': COMMIT},
                        'Env': ['PATH=/usr/local/bin:/usr/bin:/bin', 'PYTHON_VERSION=3.12.14']}}]


def container_document(container, running=False):
    return [{'Id': CID, 'Image': IMAGE, 'Name': '/' + container.name,
             'Path': '/usr/local/bin/python', 'Args': rehearsal.UVICORN_ARGS,
             'Config': {'Image': IMAGE, 'Labels': {rehearsal.LABEL: TOKEN,
                         'org.opencontainers.image.revision': COMMIT},
                        'User': '65532:65532', 'WorkingDir': '/app',
                        'Entrypoint': ['/usr/local/bin/python'], 'Cmd': rehearsal.UVICORN_ARGS,
                        'Env': [key + '=' + value for key, value in container.environment.items()],
                        'Volumes': None, 'Healthcheck': {'Test': ['NONE']}},
             'HostConfig': {'NetworkMode': 'none', 'PortBindings': {}, 'PublishAllPorts': False,
                            'Binds': None, 'Mounts': None, 'VolumesFrom': None,
                            'Privileged': False, 'ReadonlyRootfs': True,
                            'CapAdd': None, 'CapDrop': ['ALL'],
                            'SecurityOpt': ['no-new-privileges'],
                            'Tmpfs': rehearsal.TMPFS, 'LogConfig': {'Type': 'none', 'Config': {}},
                            'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0},
                            'PidMode': '', 'IpcMode': 'private', 'CgroupnsMode': 'private',
                            'Devices': [], 'DeviceRequests': None, 'DeviceCgroupRules': None,
                            'Memory': 536870912, 'MemorySwap': 536870912,
                            'NanoCpus': 1000000000, 'PidsLimit': 64, 'ShmSize': 8388608},
             'Mounts': [], 'NetworkSettings': {'Ports': {}, 'Networks': {'none': {'IPAddress': '',
                                             'GlobalIPv6Address': '', 'Gateway': ''}}},
             'State': {'Running': running, 'Paused': False, 'Restarting': False,
                       'Dead': False, 'OOMKilled': False, 'Status': 'running' if running else 'created',
                       'Pid': 12345 if running else 0}}]


class InterfaceTests(unittest.TestCase):
    def test_default_and_help_never_execute(self):
        for args, expected in (([], 2), (['--help'], 0)):
            with patch.object(rehearsal, 'run_rehearsal') as run, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(rehearsal.main(args), expected)
            run.assert_not_called()

    def test_arguments_are_closed_and_do_not_echo_inputs(self):
        valid = ['--run', '--image-id', IMAGE, '--source-commit', COMMIT]
        for args in (['--run'], valid + ['--url', 'PRIVATE'], valid + ['--run'],
                     ['--image-id', IMAGE, '--source-commit', COMMIT],
                     ['--run', '--image-id', 'PRIVATE', '--source-commit', COMMIT]):
            with self.subTest(args=args), patch.object(rehearsal, 'run_rehearsal') as run, \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(rehearsal.main(args), 2)
            run.assert_not_called()
            self.assertNotIn('PRIVATE', output.getvalue())

    def test_exact_image_and_source_are_passed_once(self):
        with patch.object(rehearsal, 'run_rehearsal', return_value=({'status': 'BLOCKED'}, 2)) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rehearsal.main(['--run', '--image-id', IMAGE, '--source-commit', COMMIT]), 2)
        run.assert_called_once_with(IMAGE, COMMIT)

    def test_image_consistency_does_not_claim_provenance_authentication(self):
        env = rehearsal.verify_image(raw(image_document()), IMAGE, COMMIT)
        self.assertEqual(env['PYTHON_VERSION'], '3.12.14')
        self.assertIn('not authenticate', rehearsal.LIMITATIONS)
        self.assertIn('database', rehearsal.LIMITATIONS)

    def test_unsafe_or_mismatched_images_rejected(self):
        changes = [('Id', 'sha256:' + 'e' * 64), ('Architecture', 'arm64'), ('Os', 'windows')]
        for key, value in changes:
            document = image_document(); document[0][key] = value
            with self.subTest(key=key), self.assertRaises(rehearsal.Blocked):
                rehearsal.verify_image(raw(document), IMAGE, COMMIT)
        for key, value in [('User', '0'), ('WorkingDir', '/'), ('Entrypoint', ['/bin/sh']),
                           ('Cmd', ['PRIVATE']), ('Volumes', {'/data': {}}),
                           ('Env', ['DATABASE_URL=PRIVATE']), ('Env', ['PATH=/bin', 'PATH=/usr/bin']),
                           ('Healthcheck', {'Test': ['CMD', 'PRIVATE']}), ('OnBuild', ['RUN PRIVATE'])]:
            document = image_document(); document[0]['Config'][key] = value
            with self.subTest(key=key), self.assertRaises(rehearsal.Blocked):
                rehearsal.verify_image(raw(document), IMAGE, COMMIT)
        document = image_document(); document[0]['Config']['Labels']['org.opencontainers.image.revision'] = 'e' * 40
        with self.assertRaises(rehearsal.Blocked):
            rehearsal.verify_image(raw(document), IMAGE, COMMIT)

    def test_json_is_bounded_strict_and_typed(self):
        for value in (b'', b'NaN', b'Infinity', b'1.0', b'1e9999', b'{"a":1,"a":2}',
                      b'\xff', b'{}{}', b' ' * 65537):
            with self.subTest(value=value[:20]), self.assertRaises(rehearsal.Blocked):
                rehearsal.document(value)
        self.assertFalse(rehearsal.exact(True, 1))


class ContainerTests(unittest.TestCase):
    def make(self, root, child=lambda *_args, **_kwargs: None):
        return rehearsal.Container(root, child, TOKEN, IMAGE, COMMIT,
                                   rehearsal.verify_image(raw(image_document()), IMAGE, COMMIT))

    def test_create_command_is_fixed_isolated_and_no_external_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            container = self.make(Path(tmp))
            args = container.create_args()
        for expected in ['--network=none', '--pull=never', '--read-only', '--user=65532:65532',
                         '--cap-drop=ALL', '--security-opt=no-new-privileges', '--log-driver=none',
                         '--pids-limit=64', '--memory=512m', '--cpus=1', '--no-healthcheck']:
            self.assertIn(expected, args)
        self.assertNotIn('--publish', args)
        self.assertNotIn('--volume', args)
        self.assertEqual(args[-len(rehearsal.UVICORN_ARGS)-1], IMAGE)
        self.assertEqual(args[-len(rehearsal.UVICORN_ARGS):], rehearsal.UVICORN_ARGS)
        self.assertIn('DATABASE_URL=postgresql+psycopg://slc_unavailable@127.0.0.1:5432/slc_unavailable', args)

    def test_inspect_rejects_changed_identity_and_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            container = self.make(Path(tmp)); container.cid = CID
            container.verify_identity(raw(container_document(container)))
            for path, value in [(('Id',), 'e' * 64), (('Image',), 'sha256:' + 'e' * 64),
                (('Config', 'Labels', rehearsal.LABEL), 'e' * 32),
                (('Config', 'Env'), ['DATABASE_URL=PRIVATE']), (('Config', 'User'), '0'),
                (('HostConfig', 'NetworkMode'), 'host'), (('HostConfig', 'ReadonlyRootfs'), False),
                (('HostConfig', 'Privileged'), True), (('HostConfig', 'PortBindings'), {'8000/tcp': [{}]}),
                (('HostConfig', 'Binds'), ['/PRIVATE:/app']), (('HostConfig', 'Memory'), 0),
                (('HostConfig', 'LogConfig', 'Type'), 'json-file'),
                (('HostConfig', 'SecurityOpt'), []), (('HostConfig', 'CapAdd'), ['SYS_ADMIN']),
                (('HostConfig', 'VolumesFrom'), ['PRIVATE']),
                (('Mounts',), [{'Type': 'bind', 'Destination': '/tmp'}]),
                (('NetworkSettings', 'Networks'), {'bridge': {}})]:
                document = container_document(container); node = document[0]
                for part in path[:-1]: node = node[part]
                node[path[-1]] = value
                with self.subTest(path=path), self.assertRaises(rehearsal.Blocked):
                    container.verify_identity(raw(document))

    def test_pid_and_running_state_must_remain_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            container = self.make(Path(tmp)); container.cid = CID
            container.verify_identity(raw(container_document(container, True)), running=True)
            changed = container_document(container, True); changed[0]['State']['Pid'] += 1
            with self.assertRaises(rehearsal.Blocked): container.verify_identity(raw(changed), running=True)
            with self.assertRaises(rehearsal.Blocked): container.verify_identity(raw(container_document(container)), running=True)

    def test_cidfile_requires_stable_regular_full_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            container = self.make(Path(tmp))
            container.cidfile.write_text(CID + '\n'); container.record_cid()
            self.assertEqual(container.cid, CID)
            container.cidfile.write_text('e' * 64)
            with self.assertRaises(rehearsal.Blocked): container.record_cid()

    def test_symlink_and_missing_cid_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            container = self.make(Path(tmp))
            with self.assertRaises(rehearsal.Blocked): container.record_cid()
            target = Path(tmp) / 'other'; target.write_text(CID)
            container.cidfile.symlink_to(target)
            with self.assertRaises(rehearsal.Blocked): container.record_cid()


class ProbeTests(unittest.TestCase):
    def test_exact_receipts_required_for_every_probe(self):
        for name in rehearsal.CASES:
            expected = {'case': name, 'passed': True}
            rehearsal.verify_probe(name, 0, raw(expected))
            for code, value in [(1, raw(expected)), (0, raw({'case': name, 'passed': 1})),
                                (0, raw(expected | {'extra': 'PRIVATE'})), (0, b'{}'),
                                (0, raw({'case': 'PRIVATE', 'passed': True}))]:
                with self.subTest(name=name, code=code), self.assertRaises(rehearsal.Blocked):
                    rehearsal.verify_probe(name, code, value)

    def test_probe_program_is_stdlib_no_proxy_no_redirect_no_application_import(self):
        text = rehearsal.PROBE_PROGRAM
        self.assertIn('http.client.HTTPConnection', text)
        self.assertIn("'127.0.0.1', 8000", text)
        self.assertNotIn('urllib', text)
        self.assertNotIn('import app', text)
        self.assertNotIn('requests', text)
        self.assertIn('4097', text)
        self.assertIn('object_pairs_hook', text)

    def test_process_probe_checks_pid1_uid_and_listeners(self):
        text = rehearsal.PROCESS_PROGRAM
        for value in ('/proc/1/cmdline', '/proc/1/status', '/proc/net/tcp', '/proc/net/tcp6', '65532'):
            self.assertIn(value, text)

    def http_probe(self, name, *, status=None, payload=None, headers=None, error=None):
        method, path, expected_status, expected_payload, private = rehearsal.CASES[name]
        body = raw(expected_payload) if payload is None else payload
        pairs = [('content-type', 'application/json'), ('content-length', str(len(body)))]
        if private:
            pairs += [('cache-control', 'private, no-store'), ('pragma', 'no-cache'),
                      ('vary', 'Authorization'), ('www-authenticate', 'Bearer')]
        response = Mock(status=expected_status if status is None else status)
        response.getheaders.return_value = pairs if headers is None else headers
        response.read.return_value = body
        connection = Mock()
        connection.getresponse.return_value = response
        if error: connection.getresponse.side_effect = error
        code = 0
        with patch('http.client.HTTPConnection', return_value=connection) as ctor, \
                patch.object(sys, 'argv', ['probe', name]), contextlib.redirect_stdout(io.StringIO()) as output:
            try: exec(compile(rehearsal.PROBE_PROGRAM, '<synthetic-probe>', 'exec'), {})
            except SystemExit as exc: code = exc.code
        ctor.assert_called_once_with('127.0.0.1', 8000, timeout=2)
        self.assertEqual(connection.request.call_args.args[:2], (method, path))
        connection.close.assert_called_once()
        return code, output.getvalue(), response

    def test_real_probe_program_validates_all_synthetic_http_cases(self):
        for name in rehearsal.CASES:
            with self.subTest(name=name):
                code, value, response = self.http_probe(name)
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(value), {'case': name, 'passed': True})
                response.read.assert_called_once_with(4097)

    def test_real_probe_program_rejects_status_json_and_lengths(self):
        for delta in ({'status': 302}, {'status': 200.0}, {'payload': b'{}'},
                      {'payload': b'{"status":"ok","version":"0.18.50","status":"ok"}'},
                      {'payload': b'{"status":"ok","version":NaN}'}, {'payload': b'\xff'},
                      {'payload': b' ' * 4097}, {'error': TimeoutError('PRIVATE')}):
            with self.subTest(delta=delta):
                code, output, _ = self.http_probe('live', **delta)
                self.assertEqual((code, output), (2, ''))

    def test_real_probe_program_rejects_unsafe_or_incomplete_headers(self):
        value = raw(rehearsal.CASES['identity_disabled'][3])
        base = [('content-type', 'application/json'), ('content-length', str(len(value))),
                ('cache-control', 'private, no-store'), ('pragma', 'no-cache'),
                ('vary', 'Authorization'), ('www-authenticate', 'Bearer')]
        invalid = [base + [('content-type', 'application/json')], base + [('location', 'PRIVATE')],
                   base + [('content-encoding', 'gzip')], base + [('transfer-encoding', 'chunked')]]
        invalid += [base[:i] + base[i+1:] for i in range(len(base))]
        invalid += [[(key, 'PRIVATE' if key == selected else val) for key, val in base]
                    for selected, _ in base]
        for headers in invalid:
            with self.subTest(headers=headers):
                code, output, _ = self.http_probe('identity_disabled', headers=headers)
                self.assertEqual((code, output), (2, ''))

    def process_probe(self, changes=None):
        files = {'/proc/1/cmdline': b'\0'.join(value.encode() for value in
                 ['/usr/local/bin/python', *rehearsal.UVICORN_ARGS]) + b'\0',
                 '/proc/1/status': b'Uid:\t65532 65532 65532 65532\nGid:\t65532 65532 65532 65532\n'
                 b'CapInh: 0\nCapPrm: 0\nCapEff: 0\nCapBnd: 0\nCapAmb: 0\nNoNewPrivs: 1\nSeccomp: 2\n',
                 '/proc/net/tcp': b'header\n0: 0100007F:1F40 00000000:0000 0A\n',
                 '/proc/net/tcp6': b'header\n'}
        files.update(changes or {})
        code = 0
        with patch('builtins.open', side_effect=lambda path, *_: io.BytesIO(files[path])), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            try: exec(compile(rehearsal.PROCESS_PROGRAM, '<synthetic-process>', 'exec'), {})
            except SystemExit as exc: code = exc.code
        return code, output.getvalue()

    def test_real_process_program_checks_synthetic_proc_files(self):
        code, value = self.process_probe()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(value), {'process': 'pid1_uvicorn', 'loopback_only': True, 'nonroot': True})

    def test_real_process_program_rejects_other_processes_and_listeners(self):
        for delta in ({'/proc/1/cmdline': b'sleep\x00600\x00'},
                      {'/proc/1/status': b'Uid: 0 0 0 0\n'},
                      {'/proc/net/tcp': b'header\n'},
                      {'/proc/net/tcp': b'header\n0: 00000000:1F40 00000000:0000 0A\n'},
                      {'/proc/net/tcp': b'header\n0: 0100007F:1F40 00000000:0000 0A\n'
                       b'1: 0100007F:1538 00000000:0000 0A\n'},
                      {'/proc/net/tcp6': b'header\n0: 00000000000000000000000001000000:1F40 0:0 0A\n'},
                      {'/proc/net/tcp': b' ' * 65537}):
            with self.subTest(delta=delta): self.assertEqual(self.process_probe(delta), (2, ''))


class LifecycleTests(unittest.TestCase):
    def simulate(self, parent, failure=None):
        root = parent / 'run'; root.mkdir()
        calls = []
        model = rehearsal.Container(root, None, TOKEN, IMAGE, COMMIT,
                                    rehearsal.verify_image(raw(image_document()), IMAGE, COMMIT))
        running = False
        def child(args, **kwargs):
            nonlocal running
            self.assertEqual(args[:2], ['/usr/bin/docker', '--host=unix:///var/run/docker.sock'])
            command = args[2:]; calls.append(command)
            if command[0] == 'info': return 0, raw({'OSType': 'linux', 'Architecture': 'amd64'})
            if command[:2] == ['image', 'inspect']: return 0, raw(image_document())
            if command[0] == 'create':
                if failure == 'missing_cid': return 1, b'PRIVATE'
                model.cidfile.write_text(CID + '\n')
                if failure == 'create_exception': raise TimeoutError('PRIVATE')
                return (1 if failure == 'create_failed' else 0), CID.encode()
            if command[:2] == ['container', 'inspect']:
                value = container_document(model, running)
                if failure == 'wrong_owner': value[0]['Config']['Labels'][rehearsal.LABEL] = 'e' * 32
                return 0, raw(value)
            if command[0] == 'start':
                if failure == 'start_failed': return 1, b'PRIVATE'
                running = True
                return 0, CID.encode()
            if command[0] == 'exec':
                if failure == 'interrupted': raise KeyboardInterrupt()
                if command[-1] == rehearsal.PROCESS_PROGRAM:
                    if failure == 'process_wrong': return 0, raw({'process': 'PRIVATE'})
                    if failure == 'process_unready': return 2, b''
                    return 0, raw({'process': 'pid1_uvicorn', 'loopback_only': True, 'nonroot': True})
                name = command[-1]
                if failure == 'probe_wrong': return 0, raw({'case': name, 'passed': False})
                return 0, raw({'case': name, 'passed': True})
            if command[:2] == ['rm', '--force']:
                if failure == 'cleanup_uncertain': return 1, b'PRIVATE'
                return 0, CID.encode()
            self.fail('unexpected command: ' + repr(command[:2]))
        with patch.object(rehearsal.tempfile, 'mkdtemp', return_value=str(root)), \
                patch.object(rehearsal, 'prepare_runtime', return_value=({'PATH': '/usr/bin'}, '/usr/bin/docker')), \
                patch.object(rehearsal, 'run_child', side_effect=child), \
                patch.object(rehearsal.uuid, 'uuid4', return_value=Mock(hex=TOKEN)), \
                patch.object(rehearsal.time, 'sleep'):
            result, code = rehearsal.run_rehearsal(IMAGE, COMMIT)
        return result, code, calls, root

    def test_success_is_narrow_and_removes_only_owned_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, code, calls, root = self.simulate(Path(tmp))
            self.assertFalse(root.exists())
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], rehearsal.SUCCESS)
        self.assertFalse(result['database_ready'])
        self.assertTrue(result['container_removed'])
        self.assertEqual(result['cases_passed'], len(rehearsal.CASES))
        self.assertEqual([call for call in calls if call[0] == 'rm'], [['rm', '--force', CID]])
        self.assertEqual(sum(call[0] == 'create' for call in calls), 1)
        self.assertEqual(sum(call[0] == 'start' for call in calls), 1)
        self.assertFalse(any(call[0] in ('pull', 'build', 'load', 'logs', 'prune', 'network', 'volume') for call in calls))

    def test_each_confirmed_failure_cleans_without_mutation_retries(self):
        for failure in ('create_exception', 'create_failed', 'start_failed', 'process_wrong',
                        'process_unready', 'probe_wrong', 'interrupted'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                result, code, calls, root = self.simulate(Path(tmp), failure)
                self.assertEqual(code, 2)
                self.assertEqual(result['status'], 'BLOCKED')
                self.assertTrue(result['container_removed'])
                self.assertFalse(root.exists())
                self.assertEqual(sum(call[0] == 'create' for call in calls), 1)
                self.assertEqual([call for call in calls if call[0] == 'rm'], [['rm', '--force', CID]])
                self.assertNotIn('PRIVATE', json.dumps(result))

    def test_uncertain_create_or_wrong_owner_preserves_state_without_removal(self):
        for failure in ('missing_cid', 'wrong_owner'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                result, code, calls, root = self.simulate(Path(tmp), failure)
                self.assertEqual((code, result['reason']), (2, 'CLEANUP_UNCERTAIN'))
                self.assertFalse(result['container_removed'])
                self.assertTrue((root / 'custody.json').exists())
                self.assertFalse(any(call[0] == 'rm' for call in calls))

    def test_uncertain_cleanup_is_not_retried_and_preserves_custody(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, code, calls, root = self.simulate(Path(tmp), 'cleanup_uncertain')
            self.assertEqual((code, result['reason']), (2, 'CLEANUP_UNCERTAIN'))
            self.assertTrue((root / 'custody.json').exists())
            self.assertTrue((root / 'container.cid').exists())
            self.assertEqual([call for call in calls if call[0] == 'rm'], [['rm', '--force', CID]])
            self.assertFalse(result['container_removed'])

    def test_invalid_programmatic_inputs_never_prepare_runtime(self):
        for image_id, commit in [('PRIVATE', COMMIT), (IMAGE, 'PRIVATE'), (IMAGE, True)]:
            with patch.object(rehearsal, 'prepare_runtime') as prepare, self.assertRaises(rehearsal.Blocked):
                rehearsal.run_rehearsal(image_id, commit)
            prepare.assert_not_called()


class HostTests(unittest.TestCase):
    def test_inherited_daemon_overrides_rejected_before_commands(self):
        for key in rehearsal.FORBIDDEN_HOST_ENV:
            with tempfile.TemporaryDirectory() as tmp, patch.dict(rehearsal.os.environ, {key: 'PRIVATE'}, clear=True), \
                    patch.object(rehearsal, 'run_child') as run, self.assertRaisesRegex(rehearsal.Blocked, 'HOST_OVERRIDE_REJECTED'):
                rehearsal.prepare_runtime(Path(tmp), COMMIT)
            run.assert_not_called()

    def test_source_mismatch_dirty_checkout_and_missing_docker_block(self):
        for responses, reason in [([(0, b'e' * 40 + b'\n')], 'SOURCE_MISMATCH'),
                                  ([(0, (COMMIT + '\n').encode()), (0, b'M PRIVATE')], 'CHECKOUT_DIRTY'),
                                  ([(0, (COMMIT + '\n').encode()), (0, b'')], 'EXISTING_DOCKER_REQUIRED')]:
            with tempfile.TemporaryDirectory() as tmp, patch.dict(rehearsal.os.environ, {}, clear=True), \
                    patch.object(rehearsal.platform, 'system', return_value='Linux'), \
                    patch.object(rehearsal.platform, 'machine', return_value='x86_64'), \
                    patch.object(rehearsal.shutil, 'disk_usage', return_value=Mock(free=2**40)), \
                    patch.object(rehearsal.shutil, 'which', return_value=None), \
                    patch.object(rehearsal, 'run_child', side_effect=responses) as run, \
                    self.assertRaisesRegex(rehearsal.Blocked, reason):
                rehearsal.prepare_runtime(Path(tmp), COMMIT)
            self.assertTrue(all(call.args[0][0] == 'git' for call in run.call_args_list))

    def test_host_environment_is_scrubbed_and_git_hooks_disabled(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(rehearsal.os.environ, {'PRIVATE': 'SECRET'}, clear=True), \
                patch.object(rehearsal.platform, 'system', return_value='Linux'), \
                patch.object(rehearsal.platform, 'machine', return_value='x86_64'), \
                patch.object(rehearsal.shutil, 'disk_usage', return_value=Mock(free=2**40)), \
                patch.object(rehearsal.shutil, 'which', return_value='/usr/bin/docker'), \
                patch.object(rehearsal, 'run_child', side_effect=[(0, (COMMIT + '\n').encode()), (0, b'')]) as run:
            env, docker = rehearsal.prepare_runtime(Path(tmp), COMMIT)
            self.assertEqual(set(env), {'PATH', 'HOME', 'DOCKER_CONFIG', 'LANG', 'LC_ALL'})
            self.assertEqual(docker, '/usr/bin/docker')
            for call in run.call_args_list:
                self.assertIn('core.fsmonitor=false', call.args[0])
                self.assertIn('core.hooksPath=/dev/null', call.args[0])

    def test_probe_constants_match_current_application_contract(self):
        self.assertIn('APP_VERSION = "0.18.50"', (ROOT / 'backend/app/main.py').read_text())
        self.assertIn('required_db_revision: str = "0029_changeover_batch_history"',
                      (ROOT / 'backend/app/core/config.py').read_text())
        self.assertNotIn('alembic', ' '.join(rehearsal.UVICORN_ARGS))
        self.assertNotIn('entrypoint.sh', ' '.join(rehearsal.UVICORN_ARGS))


if __name__ == '__main__':
    unittest.main()
