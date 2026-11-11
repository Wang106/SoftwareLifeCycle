"""Mock-only log retention contracts; never invoke Docker or emit real logs."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
try:
    import offline_log_rotation_rehearsal as r
except ModuleNotFoundError:
    r = None

TOKEN = 'b' * 32
CID = 'a' * 64
IMAGE = 'sha256:' + 'c' * 64
COMMIT = 'd' * 40


class Contracts(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(r, 'synthetic log rehearsal capability missing')

    def test_default_help_and_invalid_args_never_execute(self):
        for args, code in (([], 2), (['--help'], 0), (['--run', 'SECRET'], 2)):
            with self.subTest(args=args), patch.object(r, 'run_rehearsal') as run:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(r.main(args), code)
                run.assert_not_called()
                self.assertNotIn('SECRET', out.getvalue())

    def test_policy_matches_both_existing_compose_services(self):
        r.verify_policy()
        real = r.preflight.compose
        for key, value in (('driver', 'json-file'), ('options', {'max-size': '1m'})):
            def altered(*args):
                result = real(*args)
                result['services']['web']['logging'][key] = value
                return result
            with patch.object(r.preflight, 'compose', altered), self.assertRaises(r.Blocked):
                r.verify_policy()

    def test_line_sizes_fixed_streams_and_generation_bound(self):
        self.assertEqual(r.LINE_COUNT * r.LINE_BYTES, 64 * 1024**2)
        for n in (0, 1, 123, r.LINE_COUNT - 1):
            self.assertEqual(len(r.line(TOKEN, n)), r.LINE_BYTES)
            self.assertEqual(r.line(TOKEN, n), r.line(TOKEN, n))
        for token, n in (('bad', 0), (TOKEN, True), (TOKEN, -1), (TOKEN, r.LINE_COUNT)):
            with self.assertRaises(r.Blocked):
                r.line(token, n)

    def test_seed_requires_exact_both_streams_and_no_extra(self):
        out, err = (r.marker(TOKEN, stream, 'BEGIN') for stream in ('O', 'E'))
        self.assertTrue(r.seed_visible(0, out, err, TOKEN))
        self.assertFalse(r.seed_visible(0, b'', b'', TOKEN))
        self.assertFalse(r.seed_visible(0, out, b'', TOKEN))
        for code, a, b in ((1, out, err), (0, out, out), (0, out + b'x', err)):
            with self.assertRaises(r.Blocked):
                r.seed_visible(code, a, b, TOKEN)

    def retained(self, stream, count=3):
        parity = 0 if stream == 'O' else 1
        return b''.join(r.line(TOKEN, n) for n in range(r.LINE_COUNT - 2 * count + parity,
                       r.LINE_COUNT, 2)) + r.marker(TOKEN, stream, 'END')

    def test_retained_suffix_requires_end_and_oldest_eviction(self):
        a, b = self.retained('O'), self.retained('E')
        result = r.verify_logs(0, a, b, TOKEN)
        self.assertEqual(result, {'stdout_retained_lines': 3, 'stderr_retained_lines': 3,
                                 'oldest_markers_absent': True, 'latest_markers_present': True})
        for code, out, err in ((1, a, b), (0, a, a), (0, a, b[:-1]),
                               (0, r.marker(TOKEN, 'O', 'BEGIN') + a, b),
                               (0, a + b'x', b), (0, a, b''),
                               (0, a.replace(b':O:', b':E:', 1), b)):
            with self.subTest(code=code, length=len(out)), self.assertRaises(r.Blocked):
                r.verify_logs(code, out, err, TOKEN)

    def test_corrupt_gap_duplicate_and_foreign_token_rejected(self):
        good = self.retained('O')
        bad = (good[0:100] + b'x' + good[101:], good[r.LINE_BYTES:],
               good[:r.LINE_BYTES] + good, good.replace(TOKEN.encode(), b'f' * 32),
               good[:r.LINE_BYTES] + good[2*r.LINE_BYTES:])
        # Removing the oldest retained complete line is a permissible newer suffix.
        self.assertEqual(r.verify_logs(0, bad[1], self.retained('E'), TOKEN)['stdout_retained_lines'], 2)
        for value in (bad[0], *bad[2:]):
            with self.assertRaises(r.Blocked):
                r.verify_logs(0, value, self.retained('E'), TOKEN)

    def test_strict_inspect_document_rejects_duplicate_and_large_json(self):
        for value in (b'{"x":1,"x":2}', b'[]' + b' ' * 65536, b'NaN', b'\xff'):
            with self.assertRaises(r.Blocked):
                r.document(value)


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(r, 'synthetic log rehearsal capability missing')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calls = []
        self.state = 'created'
        self.bad = None
        self.fail_create = False
        self.container = r.Container(self.root, self.child, TOKEN, IMAGE, COMMIT, {})

    def identity(self):
        c = self.container
        return {'Id': CID, 'Image': IMAGE, 'Name': '/' + c.name,
                'Path': '/usr/local/bin/python', 'Args': c.program_args,
                'Config': {'Image': IMAGE, 'Labels': {r.LABEL: TOKEN,
                           'org.opencontainers.image.revision': COMMIT},
                           'User': '65532:65532', 'WorkingDir': '/app',
                           'Entrypoint': ['/usr/local/bin/python'], 'Cmd': c.program_args,
                           'Env': [k + '=' + v for k, v in c.environment.items()],
                           'Tty': False, 'OpenStdin': False, 'Volumes': None,
                           'Healthcheck': {'Test': ['NONE']}},
                'HostConfig': c.required_host() | {'Binds': None, 'PortBindings': {},
                             'Mounts': [], 'CapAdd': None},
                'Mounts': [], 'NetworkSettings': {'Ports': {}, 'Networks': {'none': {
                    'IPAddress': '', 'GlobalIPv6Address': '', 'Gateway': ''}}},
                'State': {'Status': self.state, 'Running': self.state == 'running',
                          'Paused': False, 'Restarting': False, 'Dead': False,
                          'OOMKilled': False, 'ExitCode': 0, 'Error': ''}}

    def child(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if args[0] == 'create':
            self.container.cidfile.write_text(CID + '\n')
            return (1 if self.fail_create else 0), CID.encode() + b'\n', b''
        if args[:2] == ['container', 'inspect']:
            value = self.identity()
            if self.bad:
                self.bad(value)
            return 0, json.dumps([value]).encode(), b''
        if args[0] == 'start':
            self.state = 'running'
        if args[0] in ('start', 'rm', 'kill'):
            return 0, CID.encode() + b'\n', b''
        raise AssertionError(args)

    def test_create_has_fixed_isolation_policy_and_cid_only_targets(self):
        self.container.create()
        args = self.calls[0][0]
        for option in ('--pull=never', '--network=none', '--read-only', '--user=65532:65532',
                       '--log-driver=local', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                       '--restart=no', '--no-healthcheck'):
            self.assertIn(option, args)
        self.assertEqual([args[i+1] for i, a in enumerate(args) if a == '--log-opt'],
                         ['max-size=10m', 'max-file=3', 'compress=true', 'mode=blocking'])
        self.assertNotIn('--rm', args)
        self.assertNotIn('--tty', args)
        self.container.trigger()
        self.container.cleanup()
        self.assertTrue(self.container.cleaned)
        for args, _ in self.calls[1:]:
            self.assertEqual(args[-1], CID)

    def test_policy_identity_and_isolation_drift_prevents_start_and_remove(self):
        mutations = [lambda d: d.update(Id='e'*64),
                     lambda d: d['HostConfig']['LogConfig']['Config'].update({'max-file': '4'}),
                     lambda d: d['Config'].update(Tty=True),
                     lambda d: d['Config']['Labels'].update({r.LABEL: 'wrong'}),
                     lambda d: d['HostConfig'].update(NetworkMode='host'),
                     lambda d: d.update(Mounts=[{'Type': 'bind', 'Destination': '/x'}]),
                     lambda d: d['HostConfig'].update(Privileged=True),
                     lambda d: d['Config'].update(Env=['SECRET=x'])]
        for change in mutations:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as root:
                self.container = r.Container(Path(root), self.child, TOKEN, IMAGE, COMMIT, {})
                self.calls = []; self.bad = change
                with self.assertRaises(r.Blocked): self.container.create()
                with self.assertRaises(r.Blocked): self.container.cleanup()
                self.assertFalse(any(a[0] in ('start', 'rm') for a, _ in self.calls))

    def test_failed_create_with_known_identity_removed_once_without_start(self):
        self.fail_create = True
        with self.assertRaises(r.Blocked): self.container.create()
        self.container.cleanup(); self.container.cleanup()
        self.assertEqual(sum(a[0] == 'rm' for a, _ in self.calls), 1)
        self.assertFalse(any(a[0] == 'start' for a, _ in self.calls))

    def test_cleanup_without_cid_never_looks_up_name(self):
        self.container.attempted = True
        with self.assertRaises(r.Blocked): self.container.cleanup()
        self.assertEqual(self.calls, [])

    def test_changed_or_symlink_cid_rejected(self):
        self.container.cidfile.write_text(CID)
        self.container.record_cid()
        self.container.cidfile.write_text('f'*64)
        with self.assertRaises(r.Blocked): self.container.record_cid()
        self.container.cidfile.unlink()
        target = self.root / 'other'; target.write_text(CID)
        self.container.cidfile.symlink_to(target)
        with self.assertRaises(r.Blocked): self.container.record_cid()

    def test_trigger_only_once_and_requires_running_identity(self):
        self.container.create(); self.container.trigger()
        with self.assertRaises(r.Blocked): self.container.trigger()
        self.assertEqual(sum(a[0] == 'kill' for a, _ in self.calls), 1)

    def test_exit_check_rejects_nonzero_oom_or_running(self):
        self.container.create(); self.state = 'exited'
        self.container.inspect('exited')
        for field, value in (('ExitCode', 1), ('OOMKilled', True), ('Running', True)):
            self.bad = lambda d: d['State'].update({field: value})
            with self.assertRaises(r.Blocked): self.container.inspect('exited')


class Orchestration(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(r, 'synthetic log rehearsal capability missing')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'owned'
        self.root.mkdir()
        self.calls = []
        self.phase_fail = None
        self.remove_fail = False
        self.seed_missing = False
        self.clock = 100.
        self.container = None
        original = r.Container
        def factory(*args):
            self.container = original(*args)
            return self.container
        for name, value in [('Container', factory), ('capture', self.capture),
                            ('verify_policy', lambda: None)]:
            patcher = patch.object(r, name, value); patcher.start(); self.addCleanup(patcher.stop)
        for target, name, value in ((r.startup, 'prepare_runtime', lambda *a: ({}, '/fixed/docker')),
                                    (r.startup, 'verify_image', lambda *a: {}),
                                    (r.tempfile, 'mkdtemp', lambda **k: str(self.root)),
                                    (r.uuid, 'uuid4', lambda: types.SimpleNamespace(hex=TOKEN)),
                                    (r.time, 'monotonic', lambda: self.clock),
                                    (r.time, 'sleep', lambda seconds: None)):
            patcher = patch.object(target, name, value); patcher.start(); self.addCleanup(patcher.stop)
        self.state = 'created'

    def identity(self):
        fixture = object.__new__(Lifecycle)
        fixture.container = self.container
        fixture.state = self.state
        return fixture.identity()

    def capture(self, args, **kwargs):
        self.assertEqual(args[:2], ['/fixed/docker', '--host=unix:///var/run/docker.sock'])
        args = args[2:]; self.calls.append((args, kwargs))
        if args[0] == self.phase_fail:
            raise r.Blocked('COMMAND_FAILED')
        if args[0] == 'info':
            return 0, b'{"OSType":"linux","Architecture":"amd64"}', b''
        if args[:2] == ['image', 'inspect']:
            return 0, b'[]', b''
        if args[0] == 'create':
            Path(args[args.index('--cidfile') + 1]).write_text(CID)
            return 0, CID.encode(), b''
        if args[:2] == ['container', 'inspect']:
            return 0, json.dumps([self.identity()]).encode(), b''
        if args[0] == 'start':
            self.state = 'running'
        elif args[0] == 'wait':
            self.state = 'exited'
            return 0, b'0\n', b''
        elif args[0] == 'logs':
            if self.state == 'running':
                return (0, b'', b'') if self.seed_missing else (0, r.marker(TOKEN, 'O', 'BEGIN'),
                                                              r.marker(TOKEN, 'E', 'BEGIN'))
            fixture = object.__new__(Contracts)
            return 0, fixture.retained('O'), fixture.retained('E')
        elif args[0] == 'rm' and self.remove_fail:
            return 1, b'', b'SECRET'
        return 0, CID.encode(), b''

    def test_full_mock_run_exact_commands_and_safe_result(self):
        result, code = r.run_rehearsal(IMAGE, COMMIT)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], r.SUCCESS)
        self.assertTrue(result['container_removed'])
        for key in ('hard_disk_bound_verified', 'compression_measured', 'physical_rotation_files_verified',
                    'restart_retention_verified', 'company_acceptance'):
            self.assertIs(result[key], False)
        logs = [(args, kw) for args, kw in self.calls if args[0] == 'logs']
        self.assertEqual(len(logs), 2)
        self.assertTrue(all(args == ['logs', CID] for args, _ in logs))
        self.assertEqual(logs[-1][1]['limit'], r.LOG_LIMIT)
        self.assertFalse(self.root.exists())

    def test_no_retry_or_trigger_on_missing_seed(self):
        self.seed_missing = True
        result, code = r.run_rehearsal(IMAGE, COMMIT)
        self.assertEqual((code, result['reason']), (2, 'SEED_TIMEOUT'))
        self.assertEqual(sum(a[0] == 'logs' for a, _ in self.calls), 20)
        self.assertFalse(any(a[0] == 'kill' for a, _ in self.calls))
        self.assertEqual(sum(a[0] == 'create' for a, _ in self.calls), 1)
        self.assertTrue(result['container_removed'])

    def test_cleanup_uncertainty_keeps_custody_and_original_error(self):
        self.phase_fail, self.remove_fail = 'wait', True
        result, code = r.run_rehearsal(IMAGE, COMMIT)
        self.assertEqual((code, result['reason'], result['cleanup_reason']),
                         (2, 'COMMAND_FAILED', 'CLEANUP_UNCERTAIN'))
        self.assertFalse(result['container_removed'])
        self.assertTrue((self.root / 'custody.json').exists())
        self.assertEqual(sum(a[0] == 'rm' for a, _ in self.calls), 1)
        self.assertNotIn('SECRET', json.dumps(result))

    def test_single_original_deadline_retains_cleanup_reserve(self):
        original = self.capture
        def delayed(args, **kwargs):
            if args[2] == 'wait':
                self.clock = 315  # Work deadline 310, original total deadline 340.
            return original(args, **kwargs)
        with patch.object(r, 'capture', delayed):
            result, code = r.run_rehearsal(IMAGE, COMMIT)
        self.assertEqual((code, result['reason']), (2, 'REHEARSAL_TIMEOUT'))
        self.assertTrue(result['container_removed'])
        self.assertFalse(any(a[0] == 'logs' and kw['limit'] == r.LOG_LIMIT for a, kw in self.calls))
        self.assertLessEqual(max(kw['timeout'] for a, kw in self.calls if a[0] == 'rm'), 25)

    def test_invalid_inputs_do_not_prepare_runtime(self):
        for image, commit in (('tag:latest', COMMIT), (IMAGE, 'main'), (IMAGE, True)):
            with self.assertRaises(r.Blocked): r.run_rehearsal(image, commit)
        self.assertEqual(self.calls, [])

    def test_create_without_cid_keeps_custody_without_cleanup_lookup(self):
        original = self.capture
        def missing(args, **kwargs):
            result = original(args, **kwargs)
            if args[2] == 'create': self.container.cidfile.unlink()
            return result
        with patch.object(r, 'capture', missing):
            result, code = r.run_rehearsal(IMAGE, COMMIT)
        self.assertEqual((code, result['reason']), (2, 'CREATE_ID_UNCERTAIN'))
        self.assertEqual(result['cleanup_reason'], 'CLEANUP_UNCERTAIN')
        self.assertTrue((self.root / 'custody.json').exists())
        self.assertFalse(any(a[0] in ('rm', 'start') for a, _ in self.calls))

    def test_main_restores_signal_after_interrupt_without_error_details(self):
        previous = object()
        with (patch.object(r, 'run_rehearsal', side_effect=KeyboardInterrupt('SECRET')),
                patch.object(r.signal, 'getsignal', return_value=previous),
                patch.object(r.signal, 'signal') as install,
                contextlib.redirect_stdout(io.StringIO()) as output):
            self.assertEqual(r.main(['--run', '--image-id', IMAGE, '--source-commit', COMMIT]), 2)
        self.assertEqual(install.call_args.args, (r.signal.SIGTERM, previous))
        self.assertNotIn('SECRET', output.getvalue())


class GeneratorAndCapture(unittest.TestCase):
    def test_generator_matches_bounded_parser_with_all_io_mocked(self):
        self.assertIsNotNone(r)
        callbacks, records = {}, {1: [], 2: []}
        counts, totals = {1: 0, 2: 0}, {1: 0, 2: 0}
        def write(fd, data):
            counts[fd] += 1; totals[fd] += len(data)
            if counts[fd] <= 2 or len(data) != r.LINE_BYTES:
                records[fd].append(data)
            return len(data)
        fake_signal = types.SimpleNamespace(SIGUSR1=10, SIGALRM=14,
                      signal=lambda sig, callback: callbacks.update({sig: callback}),
                      alarm=lambda seconds: self.assertEqual(seconds, 120))
        fake_time = types.SimpleNamespace(monotonic=lambda: 0,
                                         sleep=lambda _: callbacks[10](None, None))
        fake_sys = types.SimpleNamespace(argv=['generator', TOKEN], exit=lambda code: self.fail(str(code)))
        with patch.dict(sys.modules, {'os': types.SimpleNamespace(write=write), 'signal': fake_signal,
                                     'sys': fake_sys, 'time': fake_time}):
            exec(compile(r.GENERATOR, '<mock-generator>', 'exec'), {})
        for fd, stream, n in ((1, 'O', 0), (2, 'E', 1)):
            self.assertEqual(counts[fd], r.LINE_COUNT//2 + 2)
            self.assertEqual(records[fd], [r.marker(TOKEN, stream, 'BEGIN'), r.line(TOKEN, n),
                                          r.marker(TOKEN, stream, 'END')])
            self.assertEqual(totals[fd], r.LINE_COUNT//2*r.LINE_BYTES + len(r.marker(TOKEN, stream, 'BEGIN'))
                             + len(r.marker(TOKEN, stream, 'END')))

    def test_capture_bounds_checked_before_any_process(self):
        with patch.object(r.subprocess, 'Popen') as popen:
            for kwargs in ({'limit': True}, {'limit': r.LOG_LIMIT+1}, {'timeout': float('nan')},
                           {'timeout': float('inf')}, {'timeout': 0}, {'timeout': 241}):
                with self.assertRaises(r.Blocked): r.capture(['never'], env={}, **kwargs)
            popen.assert_not_called()

    def fake_capture(self, out, err, limit, *, clock=None, wait_error=None):
        chunks = {11: [out, b''], 12: [err, b'']}
        stdout, stderr = Mock(), Mock()
        stdout.fileno.return_value, stderr.fileno.return_value = 11, 12
        process = Mock(stdout=stdout, stderr=stderr)
        process.wait.return_value = 0
        if wait_error: process.wait.side_effect = [wait_error, 0]
        process.poll.return_value = None
        entries = {}
        selector = Mock()
        selector.__enter__ = Mock(return_value=selector)
        selector.__exit__ = Mock(return_value=False)
        def register(stream, event, target):
            entries[stream] = types.SimpleNamespace(fileobj=stream, data=target)
        selector.register.side_effect = register
        selector.unregister.side_effect = lambda stream: entries.pop(stream)
        selector.get_map.side_effect = lambda: entries
        selector.select.side_effect = lambda seconds: [(entry, 1) for entry in list(entries.values())]
        def read(fd, size):
            self.assertGreater(size, 0)
            block = chunks[fd].pop(0)
            if len(block) > size:
                chunks[fd].insert(0, block[size:]); block = block[:size]
            return block
        with (patch.object(r.subprocess, 'Popen', return_value=process) as popen,
                patch.object(r.selectors, 'DefaultSelector', return_value=selector),
                patch.object(r.os, 'set_blocking'), patch.object(r.os, 'read', read),
                patch.object(r.time, 'monotonic', side_effect=clock or (lambda: 0))):
            try:
                return r.capture(['synthetic'], env={}, limit=limit, timeout=1)
            finally:
                self.assertEqual(popen.call_args.kwargs['stdin'], r.subprocess.DEVNULL)
                stdout.close.assert_called_once(); stderr.close.assert_called_once()

    def test_capture_dual_pipes_exact_limit_overflow_and_timeout_all_mocked(self):
        self.assertEqual(self.fake_capture(b'123', b'45', 5), (0, b'123', b'45'))
        with self.assertRaisesRegex(r.Blocked, '^COMMAND_OUTPUT_LIMIT$'):
            self.fake_capture(b'123', b'456', 5)
        with self.assertRaisesRegex(r.Blocked, '^COMMAND_TIMEOUT$'):
            self.fake_capture(b'', b'', 5, clock=[0, 2])
        with self.assertRaisesRegex(r.Blocked, '^COMMAND_TIMEOUT$'):
            self.fake_capture(b'', b'', 5, wait_error=r.subprocess.TimeoutExpired('synthetic', 1))


if __name__ == '__main__':
    unittest.main()
