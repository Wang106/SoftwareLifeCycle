"""No Docker, database, downloads or installed wheels in these regressions."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.find_spec('offline_migration_context')
if SPEC:
    import offline_migration_context as migration
else:
    migration = None

COMMIT = 'a' * 40


class MigrationInputsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(migration, 'offline migration input preparation is missing')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def sources(self):
        result = {}
        for path in (ROOT / 'backend/app').rglob('*'):
            if path.is_file() and path.suffix in {'.py', '.json'}:
                result[path.relative_to(ROOT).as_posix()] = path.read_bytes()
        for name in migration.FIXED_SOURCES:
            result[name] = (ROOT / name).read_bytes()
        for path in (ROOT / 'backend/alembic/versions').glob('*.py'):
            result[path.relative_to(ROOT).as_posix()] = path.read_bytes()
        return result

    def synthetic_wheels(self, sources):
        manifest = json.loads(sources['backend/offline-python-wheelhouse.json'])
        directory = self.root / 'wheelhouse'
        directory.mkdir()
        for item in manifest['artifacts']:
            raw = ('synthetic: ' + item['filename']).encode()
            (directory / item['filename']).write_bytes(raw)
            item['sha256'] = hashlib.sha256(raw).hexdigest()
            item['size_bytes'] = len(raw)
        sources['backend/offline-python-wheelhouse.json'] = json.dumps(manifest).encode()
        sources['backend/requirements-linux-cp312.lock'] = migration.wheels.lock_text(manifest).encode()
        return directory

    def prepare(self, sources=None, destination=None):
        sources = sources or self.sources()
        wheelhouse = self.synthetic_wheels(sources)
        destination = destination or self.root / 'context'
        with patch.object(migration, 'snapshot', return_value=sources), \
             patch.object(migration.wheels, 'metadata'), \
             patch.object(migration, 'verify_wheel_closure', return_value={
                 'status': 'OFFLINE_PIP_CLOSURE_VERIFIED', 'wheel_count': 30,
                 'closure_report_sha256': 'b' * 64,
                 'limitations': 'synthetic test'}) as closure:
            result = migration.prepare(ROOT, COMMIT, wheelhouse, destination)
        self.assertEqual(closure.call_count, 1)
        return destination, result

    def test_prepare_preserves_all_bytes_and_separately_verifies(self):
        path, result = self.prepare()
        self.assertEqual(result['status'], 'MIGRATION_INPUTS_PREPARED_NOT_EXECUTED')
        self.assertFalse(result['database_connected'])
        self.assertFalse(result['image_built'])
        self.assertEqual(result['migration_count'], 29)
        with patch.object(migration.wheels, 'metadata'), \
             patch.object(migration.wheels, 'pip_closure', side_effect=AssertionError('verify must not run pip')):
            verified = migration.verify(path, COMMIT, result['manifest_sha256'])
        self.assertEqual(verified['status'], 'MIGRATION_INPUTS_VERIFIED_NOT_EXECUTED')
        self.assertEqual((path / 'alembic/env.py').read_bytes(), (ROOT / 'backend/alembic/env.py').read_bytes())
        self.assertEqual(len(list((path / 'alembic/versions').glob('*.py'))), 29)
        self.assertFalse((path / 'entrypoint.sh').exists())

    def test_chain_is_ast_only_and_exact(self):
        sources = self.sources()
        self.assertEqual(migration.validate_sources(sources)['migration_count'], 29)
        key = 'backend/alembic/versions/0001_core_and_snapshot.py'
        sources[key] = b"raise RuntimeError('must never execute')\n" + sources[key]
        self.assertEqual(migration.validate_sources(sources)['migration_count'], 29)

    def test_missing_required_sources_rejected(self):
        for name in migration.FIXED_SOURCES | {'backend/alembic/versions/0001_core_and_snapshot.py'}:
            with self.subTest(name=name):
                sources = self.sources(); sources.pop(name)
                with self.assertRaises(migration.Blocked):
                    migration.validate_sources(sources)

    def test_chain_faults_rejected(self):
        key = 'backend/alembic/versions/0002_change_testing.py'
        for raw in (
            b"revision='0002_change_testing'; down_revision=None; branch_labels=None; depends_on=None",
            b"revision='0002_change_testing'; down_revision='missing'; branch_labels=None; depends_on=None",
            b"revision='0002_change_testing'; down_revision='0002_change_testing'; branch_labels=None; depends_on=None",
            b"revision='0001_core_and_snapshot'; down_revision=None; branch_labels=None; depends_on=None",
            b"revision=compute(); down_revision='0001_core_and_snapshot'; branch_labels=None; depends_on=None",
            b"revision='0002_change_testing'; revision='0002_change_testing'; down_revision='0001_core_and_snapshot'; branch_labels=None; depends_on=None",
            b"revision='0002_change_testing'; down_revision='0001_core_and_snapshot'; branch_labels=('branch',); depends_on=None",
            b"revision='0002_change_testing'; down_revision='0001_core_and_snapshot'; branch_labels=None; depends_on='0001_core_and_snapshot'",
            b"invalid ( syntax",
        ):
            with self.subTest(raw=raw):
                sources = self.sources(); sources[key] = raw
                with self.assertRaises(migration.Blocked): migration.validate_sources(sources)

    def test_source_paths_modes_and_bounds(self):
        for name in ('backend/app/../bad.py', 'backend/app/.env', 'backend/app/secret.py',
                     'backend/app/auth.json', '/backend/app/a.py', 'backend/app/a\\b.py',
                     'backend/alembic/versions/unexpected.py'):
            with self.subTest(name=name):
                sources = self.sources(); sources[name] = b'x'
                with self.assertRaises(migration.Blocked): migration.validate_sources(sources)
        sources = self.sources(); sources['backend/app/main.py'] = b'x' * (migration.MAX_SOURCE_FILE + 1)
        with self.assertRaises(migration.Blocked): migration.validate_sources(sources)
        with patch.object(migration, 'MAX_SOURCE_TOTAL', 1):
            with self.assertRaises(migration.Blocked): migration.validate_sources(self.sources())
        with patch.object(migration, 'MAX_SOURCE_FILES', 1):
            with self.assertRaises(migration.Blocked): migration.validate_sources(self.sources())

    def test_base_head_and_lock_mismatch(self):
        for name, old, new in (
            ('backend/app/core/config.py', b'0029_changeover_batch_history', b'0028_deployment_actual_guard'),
            ('deploy/offline/base-images.json', b'linux/amd64', b'linux/arm64'),
            ('backend/requirements-linux-cp312.lock', b'alembic==', b'alembic>='),
        ):
            with self.subTest(name=name):
                sources = self.sources(); sources[name] = sources[name].replace(old, new)
                with self.assertRaises(migration.Blocked): migration.validate_sources(sources)

    def test_existing_destination_is_preserved(self):
        destination = self.root / 'context'; destination.mkdir()
        sentinel = destination / 'sentinel'; sentinel.write_text('preserve')
        sources = self.sources(); wheelhouse = self.synthetic_wheels(sources)
        with patch.object(migration, 'snapshot', return_value=sources), patch.object(migration.wheels, 'metadata'):
            with self.assertRaises(migration.Blocked): migration.prepare(ROOT, COMMIT, wheelhouse, destination)
        self.assertEqual(sentinel.read_text(), 'preserve')

    def test_missing_wheelhouse_does_not_create_output(self):
        with patch.object(migration, 'snapshot', return_value=self.sources()):
            with self.assertRaises(migration.Blocked):
                migration.prepare(ROOT, COMMIT, self.root / 'absent', self.root / 'context')
        self.assertFalse((self.root / 'context').exists())

    def test_symlink_traversal_and_special_inputs_rejected(self):
        regular = self.root / 'file'; regular.write_bytes(b'x')
        linked = self.root / 'linked'; linked.symlink_to(regular)
        fifo = self.root / 'fifo'; os.mkfifo(fifo)
        hard = self.root / 'hard'; os.link(regular, hard)
        for path in (linked, fifo, hard, self.root / '..' / self.root.name / 'file'):
            with self.subTest(path=path), self.assertRaises(migration.Blocked):
                migration.safe_read(path, 100)
        alias = self.root / 'alias'; alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(migration.Blocked): migration.safe_read(alias / 'file', 100)

    def test_modified_missing_extra_files_and_dirs_rejected(self):
        path, receipt = self.prepare()
        target = path / 'app/main.py'; raw = target.read_bytes()
        for change in ('modified', 'missing', 'extra', 'extra_directory', 'symlink'):
            with self.subTest(change=change):
                if change == 'modified': target.write_bytes(raw + b'x')
                elif change == 'missing': target.unlink()
                elif change == 'extra': (path / 'extra').write_bytes(b'x')
                elif change == 'extra_directory': (path / 'extra').mkdir()
                else: target.unlink(); target.symlink_to(ROOT / 'backend/app/main.py')
                with self.assertRaises(migration.Blocked): migration.verify(path, COMMIT, receipt['manifest_sha256'])
                if target.is_symlink(): target.unlink()
                if not target.exists() or target.read_bytes() != raw: target.write_bytes(raw)
                if (path / 'extra').is_file(): (path / 'extra').unlink()
                elif (path / 'extra').is_dir(): (path / 'extra').rmdir()

    def test_wrong_trusted_expectations_rejected(self):
        path, receipt = self.prepare()
        for commit, digest in (('b' * 40, receipt['manifest_sha256']), (COMMIT, 'b' * 64),
                               ('a', receipt['manifest_sha256']), (COMMIT, 'x' * 64)):
            with self.subTest(commit=commit, digest=digest), self.assertRaises(migration.Blocked):
                migration.verify(path, commit, digest)

    def test_manifest_rejects_extra_fields_duplicate_and_wrong_types(self):
        path, receipt = self.prepare()
        target = path / migration.MANIFEST
        original = json.loads(target.read_bytes())
        variants = []
        for key, value in (('extra', 1), ('migration_count', True), ('source_commit', 'b' * 40),
                           ('database_connected', True), ('files', [])):
            candidate = copy.deepcopy(original); candidate[key] = value
            variants.append(migration.canonical(candidate))
        variants.extend((b'{"format":1,"format":2}', b'{"format":NaN}', b'\xff'))
        for raw in variants:
            with self.subTest(raw=raw[:70]):
                target.write_bytes(raw)
                with self.assertRaises(migration.Blocked):
                    migration.verify(path, COMMIT, hashlib.sha256(raw).hexdigest())

    def test_failure_never_cleans_destination(self):
        sources = self.sources(); wheelhouse = self.synthetic_wheels(sources)
        destination = self.root / 'context'
        with patch.object(migration, 'snapshot', return_value=sources), \
             patch.object(migration.wheels, 'metadata'), \
             patch.object(migration, 'write_file', side_effect=OSError('PRIVATE')):
            with self.assertRaises(migration.Blocked): migration.prepare(ROOT, COMMIT, wheelhouse, destination)
        self.assertTrue(destination.is_dir())

    def test_closure_failure_never_returns_success(self):
        sources = self.sources(); wheelhouse = self.synthetic_wheels(sources)
        with patch.object(migration, 'snapshot', return_value=sources), \
             patch.object(migration.wheels, 'metadata'), \
             patch.object(migration, 'verify_wheel_closure', side_effect=ValueError('PRIVATE')):
            with self.assertRaises(migration.Blocked): migration.prepare(ROOT, COMMIT, wheelhouse, self.root / 'context')
        self.assertTrue((self.root / 'context').is_dir())
        self.assertFalse((self.root / 'context' / migration.MANIFEST).exists())

    def test_cli_errors_do_not_disclose_paths_or_exception_text(self):
        output = io.StringIO()
        with patch.object(migration, 'prepare', side_effect=OSError('PRIVATE_SECRET')), patch('sys.stderr', output):
            self.assertEqual(migration.main(['prepare', '--repository', '/PRIVATE', '--expected-commit', COMMIT,
                                            '--wheelhouse', '/PRIVATE_WHEELS', '--destination', '/PRIVATE_DEST']), 2)
        self.assertEqual(output.getvalue(), 'MIGRATION_INPUTS_BLOCKED\n')

    def test_confined_checker_uses_trusted_code_and_finite_limits(self):
        response = b'{"status":"OFFLINE_PIP_CLOSURE_VERIFIED"}'
        with patch.object(migration, 'bounded_command', return_value=response) as command:
            migration.verify_wheel_closure(self.root, (ROOT / 'scripts/offline_python_wheelhouse.py').read_bytes(),
                                           (ROOT / 'scripts/offline_migration_context.py').read_bytes())
        args, kw = command.call_args
        self.assertEqual(args[0][1:3], ['-I', '-B'])
        self.assertEqual(args[0][3], '-c')
        self.assertEqual(Path(args[0][5]), ROOT / 'scripts')
        self.assertIn('m.check_wheels_only', args[0][4])
        self.assertTrue(kw['confined'])
        self.assertEqual(kw['limit'], 65536)
        self.assertEqual(kw['timeout'], 150)
        self.assertNotIn('DATABASE_URL', kw['env'])
        with patch.object(migration, 'bounded_command') as command:
            with self.assertRaises(migration.Blocked): migration.verify_wheel_closure(self.root, b'changed', b'changed')
            command.assert_not_called()

    def test_child_limits_never_expand_existing_limits(self):
        with patch.object(migration.resource, 'getrlimit', return_value=(100, 200)), \
             patch.object(migration.resource, 'setrlimit') as limits:
            migration.child_limits()
        self.assertEqual(len(limits.call_args_list), 3)
        for call in limits.call_args_list:
            self.assertLessEqual(call.args[1][0], 100)
            self.assertLessEqual(call.args[1][1], 200)

    def test_bounded_command_rejects_stdout_stderr_nonzero_and_timeout(self):
        cases = [("print('x'*2000)", 10, 2),
                 ("import sys;sys.stderr.write('x'*2000)", 10, 2),
                 ("raise SystemExit(7)", 100, 2),
                 ("import time;time.sleep(5)", 100, .05)]
        for program, limit, timeout in cases:
            with self.subTest(program=program), self.assertRaises(migration.Blocked):
                migration.bounded_command([sys.executable, '-I', '-c', program], env={}, limit=limit, timeout=timeout)
        self.assertEqual(migration.bounded_command([sys.executable, '-I', '-c', "print('ok')"], env={}), b'ok\n')

    def test_git_command_is_local_bounded_and_sanitized(self):
        with patch.object(migration, 'bounded_command', return_value=b'x') as command:
            self.assertEqual(migration.git_read(123, ['rev-parse', 'HEAD'], 128), b'x')
        args, kw = command.call_args
        for value in ('--no-lazy-fetch', '--no-replace-objects', 'core.fsmonitor=false', 'core.hooksPath=/dev/null'):
            self.assertIn(value, args[0])
        self.assertEqual(kw['limit'], 128)
        self.assertEqual(kw['pass_fds'], (123,))
        self.assertNotIn('GITHUB_TOKEN', kw['env'])

    def test_snapshot_rejects_dirty_wrong_head_filter_and_invalid_mode(self):
        for issue in ('dirty', 'head', 'filter', 'mode', 'oversize'):
            def command(fd, args, limit=migration.MAX_GIT_OUTPUT):
                if args[0] == 'config': return b'filter.bad.clean\nevil\0' if issue == 'filter' else b''
                if args[0] == 'rev-parse': return (('b' if issue == 'head' else 'a') * 40).encode()
                if args[0] == 'status': return b' M x' if issue == 'dirty' else b''
                if args[0] == 'ls-tree': return b'120000 blob ' + b'c'*40 + b'\tbackend/app/main.py\0'
                raise AssertionError('no additional command expected')
            with self.subTest(issue=issue), patch.object(migration, 'git_read', side_effect=command):
                with self.assertRaises((migration.Blocked, OSError)):
                    migration.snapshot(self.root, COMMIT)

    def test_short_write_and_close_failure_preserve_partial_output(self):
        class BrokenStream:
            def __init__(self, fd, fail): self.fd, self.fail = fd, fail
            def __enter__(self): return self
            def write(self, data): return len(data) - 1 if self.fail == 'short' else os.write(self.fd, data)
            def flush(self): pass
            def fileno(self): return self.fd
            def __exit__(self, *args):
                os.close(self.fd)
                if self.fail == 'close': raise OSError('uncertain close')
        for failure in ('short', 'close'):
            with self.subTest(failure=failure):
                with migration.wheels.directory(self.root) as fd, \
                     patch.object(migration.os, 'fdopen', side_effect=lambda descriptor, mode: BrokenStream(descriptor, failure)):
                    with self.assertRaises((migration.Blocked, OSError)):
                        migration.write_file(fd, failure, b'input')
                self.assertTrue((self.root / failure).exists())

    def test_context_wheel_tamper_and_special_file_rejected(self):
        path, receipt = self.prepare()
        wheel = next((path / 'wheels').iterdir())
        wheel.write_bytes(b'changed')
        with self.assertRaises(migration.Blocked): migration.verify(path, COMMIT, receipt['manifest_sha256'])
        wheel.unlink(); os.mkfifo(wheel)
        with self.assertRaises(migration.Blocked): migration.verify(path, COMMIT, receipt['manifest_sha256'])

    def test_independent_verify_never_invokes_any_child(self):
        path, receipt = self.prepare()
        with patch.object(migration, 'bounded_command', side_effect=AssertionError('must not execute')):
            self.assertEqual(migration.verify(path, COMMIT, receipt['manifest_sha256'])['migration_count'], 29)

    def test_manifest_close_uncertainty_and_final_verify_failure_never_succeed(self):
        for reason in ('manifest_close', 'verify'):
            with self.subTest(reason=reason):
                sources = self.sources()
                wheelhouse = self.root / ('wheels_' + reason)
                # One separate per-case directory while retaining prior failed output.
                with tempfile.TemporaryDirectory() as temporary:
                    original_root = self.root; self.root = Path(temporary)
                    try: wheelhouse = self.synthetic_wheels(sources)
                    finally: self.root = original_root
                    destination = self.root / ('context_' + reason)
                    original = migration.write_file
                    def write(fd, name, raw):
                        original(fd, name, raw)
                        if reason == 'manifest_close' and name == migration.MANIFEST:
                            raise OSError('uncertain manifest close')
                    with patch.object(migration, 'snapshot', return_value=sources), \
                         patch.object(migration.wheels, 'metadata'), \
                         patch.object(migration, 'verify_wheel_closure', return_value={
                             'status': 'OFFLINE_PIP_CLOSURE_VERIFIED', 'wheel_count': 30,
                             'closure_report_sha256': 'b'*64}), \
                         patch.object(migration, 'write_file', side_effect=write), \
                         patch.object(migration, 'verify', side_effect=migration.Blocked('blocked')):
                        with self.assertRaises(migration.Blocked):
                            migration.prepare(ROOT, COMMIT, wheelhouse, destination)
                    self.assertTrue((destination / migration.MANIFEST).exists())

    def test_invalid_cli_arguments_use_fixed_error(self):
        for argv in ([], ['PRIVATE_UNKNOWN'], ['verify', '--context', '/PRIVATE']):
            with self.subTest(argv=argv):
                output = io.StringIO()
                with patch('sys.stderr', output): self.assertEqual(migration.main(argv), 2)
                self.assertEqual(output.getvalue(), 'MIGRATION_INPUTS_BLOCKED\n')

    def test_snapshot_reads_real_clean_local_git_objects_without_execution(self):
        # A disposable local repository, no remote, downloads or context preparation.
        import subprocess
        sources = self.sources()
        repo = self.root / 'repo'; repo.mkdir()
        for name, raw in sources.items():
            target = repo / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(self.root), 'GIT_CONFIG_NOSYSTEM': '1',
               'GIT_CONFIG_GLOBAL': '/dev/null'}
        def git(*args):
            return subprocess.run(['/usr/bin/git', *args], cwd=repo, env=env, check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
        git('init', '-q'); git('add', '.')
        git('-c', 'user.name=synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'synthetic')
        commit = git('rev-parse', 'HEAD').decode().strip()
        self.assertEqual(migration.snapshot(repo, commit), sources)
        (repo / 'backend/app/main.py').write_bytes(b'changed')
        with self.assertRaises(migration.Blocked): migration.snapshot(repo, commit)

    def test_ast_rejects_metadata_rebinding_beyond_plain_declaration(self):
        name = 'backend/alembic/versions/0001_core_and_snapshot.py'
        for suffix in (b"\nrevision += '_changed'\n", b"\nif True: revision = 'different'\n",
                       b"\nrevision, other = 'different', None\n", b"\ndel revision\n",
                       b"\ndef change():\n global revision\n revision = 'different'\n"):
            with self.subTest(suffix=suffix):
                sources = self.sources(); sources[name] += suffix
                with self.assertRaises(migration.Blocked): migration.validate_sources(sources)
        sources = self.sources(); name = 'backend/app/core/config.py'
        sources[name] = sources[name].replace(b'class Settings(BaseSettings):',
            b'class Settings(BaseSettings):\n    required_db_revision = "different"')
        with self.assertRaises(migration.Blocked): migration.validate_sources(sources)

    def test_verify_rejects_same_names_after_directory_replacement(self):
        import shutil
        path, receipt = self.prepare()
        replacement = self.root / 'replacement'
        shutil.copytree(path / 'app', replacement)
        target = replacement / 'main.py'
        raw = target.read_bytes(); target.write_bytes(b'x' * len(raw))
        original = migration.read_at
        swapped = False
        def read(fd, name, limit):
            nonlocal swapped
            raw = original(fd, name, limit)
            if name == 'app/main.py' and not swapped:
                swapped = True
                (path / 'app').rename(self.root / 'old-app')
                replacement.rename(path / 'app')
            return raw
        with patch.object(migration, 'read_at', side_effect=read):
            with self.assertRaises(migration.Blocked): migration.verify(path, COMMIT, receipt['manifest_sha256'])

    def test_uncertain_close_never_retries_same_descriptor(self):
        directory = self.root / 'nested'; directory.mkdir(); (directory / 'file').write_bytes(b'x')
        original = os.close
        with migration.wheels.directory(self.root) as root_fd:
            calls = []
            def close(fd):
                calls.append(fd)
                if len(calls) == 1:
                    original(fd)
                    raise OSError('closed but outcome uncertain')
                original(fd)
            with patch.object(migration.os, 'close', side_effect=close):
                with self.assertRaises(OSError): migration.read_at(root_fd, 'nested/file', 10)
            self.assertEqual(calls.count(calls[0]), 1)

    def test_verify_rejects_context_root_and_ancestor_replacement(self):
        for replaced in ('context', 'parent'):
            with self.subTest(replaced=replaced), tempfile.TemporaryDirectory() as temporary:
                original_root = self.root; self.root = Path(temporary)
                try:
                    parent = self.root / 'parent'; parent.mkdir()
                    path, receipt = self.prepare(destination=parent / 'context')
                    original = migration.read_at
                    swapped = False
                    def read(fd, name, limit):
                        nonlocal swapped
                        data = original(fd, name, limit)
                        if name == 'app/main.py' and not swapped:
                            swapped = True
                            target = path if replaced == 'context' else parent
                            target.rename(self.root / 'moved')
                            target.mkdir(); (target / 'wrong').write_bytes(b'wrong')
                        return data
                    with patch.object(migration, 'read_at', side_effect=read):
                        with self.assertRaises(migration.Blocked): migration.verify(path, COMMIT, receipt['manifest_sha256'])
                finally:
                    self.root = original_root

    def test_directory_and_write_close_uncertainty_never_retries(self):
        original = os.close
        for action in ('directory', 'write'):
            with self.subTest(action=action):
                calls = []
                def close(fd):
                    calls.append(fd)
                    original(fd)
                    if len(calls) == 1: raise OSError('uncertain close')
                if action == 'directory':
                    with patch.object(migration.os, 'close', side_effect=close):
                        with self.assertRaises(OSError):
                            with migration.directory(self.root): pass
                else:
                    with migration.directory(self.root) as fd:
                        with patch.object(migration.os, 'close', side_effect=close):
                            with self.assertRaises(OSError): migration.write_file(fd, 'subdir/file', b'x')
                self.assertEqual(len(calls), len(set(calls)))

    def test_ast_rejects_exception_pattern_and_wildcard_bindings(self):
        cases = (b"\ntry: pass\nexcept RuntimeError as revision: pass\n",
                 b"\nmatch object():\n case revision: pass\n",
                 b"\nmatch object():\n case [*revision]: pass\n",
                 b"\nmatch object():\n case {**revision}: pass\n",
                 b"\nfrom unknown import *\n")
        for raw in cases:
            with self.subTest(raw=raw):
                sources = self.sources(); sources['backend/alembic/versions/0001_core_and_snapshot.py'] += raw
                with self.assertRaises(migration.Blocked): migration.validate_sources(sources)
        sources = self.sources()
        sources['backend/app/core/config.py'] += b"\ntry: pass\nexcept RuntimeError as required_db_revision: pass\n"
        with self.assertRaises(migration.Blocked): migration.validate_sources(sources)

    def test_recipe_is_fail_closed_and_offline(self):
        raw = (ROOT / 'deploy/offline/migration.Dockerfile').read_text()
        self.assertIn('ENTRYPOINT ["/bin/false"]', raw)
        self.assertIn('CMD []', raw)
        self.assertIn('USER 65532:65532', raw)
        self.assertIn('RUN --network=none ', raw)
        self.assertIn('--no-index', raw)
        self.assertIn('--require-hashes', raw)
        self.assertIn('COPY alembic/ /app/alembic/', raw)
        self.assertIn('COPY alembic.ini /app/alembic.ini', raw)
        for forbidden in ('upgrade head', 'entrypoint.sh', 'uvicorn', 'apt-get', 'curl ', 'ADD ', 'VOLUME', 'EXPOSE'):
            self.assertNotIn(forbidden, raw)


if __name__ == '__main__':
    unittest.main()
