"""Retained synthetic bundles must restore in a genuinely separate process."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts'


class RetainedRestoreTests(unittest.TestCase):
    def original(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'offline_software_restore_rehearsal.py')],
                                capture_output=True, text=True, timeout=10, check=True)
        report = json.loads(result.stdout)
        root = Path('/tmp') / report['run_id']
        self.addCleanup(shutil.rmtree, root)
        return report, root

    def test_separate_process_without_original_source(self):
        report, root = self.original()
        with tempfile.TemporaryDirectory() as owned:
            (root / 'source').rename(Path(owned) / 'source')
            before = {p.name: p.read_bytes() for p in (root / 'bundle').iterdir()}
            result = subprocess.run([sys.executable, str(SCRIPTS / 'offline_retained_software_restore.py'),
                                     report['run_id'], report['manifest_sha256']],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            restored = json.loads(result.stdout)
            target = Path('/tmp') / restored['run_id']
            self.addCleanup(shutil.rmtree, target)
            self.assertNotEqual(target, root)
            self.assertEqual(restored['source_run_id'], report['run_id'])
            self.assertEqual(restored['status'], 'VERIFIED')
            self.assertFalse((root / 'source').exists())
            self.assertEqual(before, {p.name: p.read_bytes() for p in (root / 'bundle').iterdir()})
            for name, data in before.items():
                if name != 'manifest.json':
                    self.assertEqual((target / 'restored' / name).read_bytes(), data)

    def module(self):
        spec = importlib.util.spec_from_file_location('retained_restore', SCRIPTS / 'offline_retained_software_restore.py')
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', [str(SCRIPTS), *sys.path]):
            spec.loader.exec_module(module)
        return module

    def open_run(self, report):
        module = self.module()
        run = module.RetainedRestore(report['run_id'], report['manifest_sha256'])
        self.addCleanup(run.close)
        return module, run

    def reject_before_target(self, report):
        module = self.module()
        with patch.object(module.RetainedRestore, '_new_dir') as create:
            with self.assertRaises((OSError, module.Rejected)):
                with module.RetainedRestore(report['run_id'], report['manifest_sha256']) as run:
                    run.restore()
            create.assert_not_called()

    def test_missing_or_forged_success_baseline(self):
        for content in (None, b'{}', b'X' * 10000):
            with self.subTest(content=content is None):
                report, root = self.original()
                if content is None:
                    (root / 'result.json').unlink()
                else:
                    (root / 'result.json').write_bytes(content)
                self.reject_before_target(report)

    def test_wrong_digest_and_wrong_run(self):
        report, _ = self.original()
        other, _ = self.original()
        for changes in ({'manifest_sha256': '0' * 64}, {'run_id': other['run_id']},
                        {'run_id': 'software-rehearsal-' + 'f' * 32}):
            with self.subTest(changes=changes):
                self.reject_before_target({**report, **changes})

    def test_bundle_missing_extra_corrupt_and_unbounded_entries(self):
        for kind in ('missing', 'extra', 'corrupt', 'many', 'manifest', 'huge'):
            with self.subTest(kind=kind):
                report, root = self.original()
                file = root / 'bundle/firmware.bin'
                if kind == 'missing':
                    file.unlink()
                elif kind in ('extra', 'many'):
                    for index in range(20 if kind == 'many' else 1):
                        (root / 'bundle' / str(index)).touch()
                elif kind == 'corrupt':
                    file.write_bytes(b'x' * file.stat().st_size)
                elif kind == 'huge':
                    file.write_bytes(b'x' * 10000)
                else:
                    (root / 'bundle/manifest.json').write_bytes(b'{')
                self.reject_before_target(report)

    def test_joint_manifest_bytes_and_result_forgery(self):
        import hashlib
        report, root = self.original()
        manifest = json.loads((root / 'bundle/manifest.json').read_bytes())
        data = b'forged'
        (root / 'bundle/firmware.bin').write_bytes(data)
        row = next(row for row in manifest['files'] if row['path'] == 'firmware.bin')
        row.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
        forged = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
        (root / 'bundle/manifest.json').write_bytes(forged)
        report['manifest_sha256'] = hashlib.sha256(forged).hexdigest()
        (root / 'result.json').write_text(json.dumps(report, sort_keys=True))
        self.reject_before_target(report)

    def test_malicious_manifest_paths_are_not_used(self):
        for name in ('../escape', '/tmp/escape', 'x\\y', '\x00', ''):
            with self.subTest(name=name):
                report, root = self.original()
                manifest = json.loads((root / 'bundle/manifest.json').read_bytes())
                manifest['files'][0]['path'] = name
                (root / 'bundle/manifest.json').write_text(json.dumps(manifest))
                self.reject_before_target(report)

    def test_special_files_rejected_for_bundle_and_baseline(self):
        for relative in ('bundle/firmware.bin', 'bundle/manifest.json', 'result.json'):
            for kind in ('symlink', 'hardlink', 'fifo', 'directory'):
                with self.subTest(relative=relative, kind=kind):
                    report, root = self.original()
                    file = root / relative
                    old = root / 'held-file'
                    file.rename(old)
                    if kind == 'symlink':
                        file.symlink_to(old)
                    elif kind == 'hardlink':
                        os.link(old, file)
                    elif kind == 'fifo':
                        os.mkfifo(file, 0o600)
                    else:
                        file.mkdir(mode=0o700)
                    self.reject_before_target(report)

    def test_private_modes_required(self):
        for relative, mode in (('', 0o755), ('bundle', 0o750), ('bundle/manifest.json', 0o640),
                               ('bundle/firmware.bin', 0o644), ('result.json', 0o644)):
            with self.subTest(relative=relative):
                report, root = self.original()
                (root / relative).chmod(mode)
                self.reject_before_target(report)

    def test_directory_symlinks_rejected(self):
        report, root = self.original()
        (root / 'bundle').rename(root / 'held-bundle')
        (root / 'bundle').symlink_to(root / 'held-bundle', target_is_directory=True)
        self.reject_before_target(report)

    def test_source_and_original_restored_are_not_opened(self):
        report, root = self.original()
        module, run = self.open_run(report)
        before = {p.name: p.read_bytes() for p in (root / 'bundle').iterdir()}
        opened = []
        original = os.open
        def tracking_open(name, *args, **kwargs):
            opened.append(name)
            return original(name, *args, **kwargs)
        with patch.object(module.os, 'open', side_effect=tracking_open):
            result = run.restore()
        self.addCleanup(shutil.rmtree, Path('/tmp') / result['run_id'])
        self.assertNotIn('source', opened)
        # Exactly one restored open, belonging to the fresh recovery output.
        self.assertEqual(opened.count('restored'), 1)
        self.assertEqual(before, {p.name: p.read_bytes() for p in (root / 'bundle').iterdir()})

    def test_existing_recovery_run_never_overwritten(self):
        for kind in ('empty', 'populated', 'symlink', 'file'):
            with self.subTest(kind=kind):
                report, root = self.original()
                module, run = self.open_run(report)
                token = os.urandom(16).hex()
                target = Path('/tmp') / ('software-recovery-' + token)
                if kind == 'symlink':
                    target.symlink_to(root, target_is_directory=True)
                    self.addCleanup(target.unlink)
                elif kind == 'file':
                    target.write_bytes(b'keep')
                    self.addCleanup(target.unlink)
                else:
                    target.mkdir(mode=0o700)
                    self.addCleanup(shutil.rmtree, target)
                    if kind == 'populated':
                        (target / 'keep').write_bytes(b'keep')
                with patch.object(module.secrets, 'token_hex', return_value=token):
                    with self.assertRaises(FileExistsError):
                        run.restore()
                if kind == 'populated':
                    self.assertEqual((target / 'keep').read_bytes(), b'keep')
                self.assertTrue(target.exists())

    def test_existing_restored_target_rejected(self):
        report, _ = self.original()
        _, run = self.open_run(report)
        original = run._new_dir
        def injecting_new(parent, name):
            if name == 'restored':
                os.mkdir(name, 0o700, dir_fd=parent)
            return original(parent, name)
        with patch.object(run, '_new_dir', side_effect=injecting_new):
            with self.assertRaises(FileExistsError):
                run.restore()
        self.addCleanup(shutil.rmtree, Path('/tmp') / run.run_id)
        self.assertEqual(list((Path('/tmp') / run.run_id / 'restored').iterdir()), [])

    def test_read_stat_open_replacement(self):
        report, root = self.original()
        module, run = self.open_run(report)
        original = os.open
        swapped = False
        def swapping_open(name, flags, *args, **kwargs):
            nonlocal swapped
            if name == 'firmware.bin' and not swapped:
                swapped = True
                file = root / 'bundle/firmware.bin'
                file.rename(root / 'held-file')
                file.symlink_to(root / 'held-file')
            return original(name, flags, *args, **kwargs)
        with patch.object(module.os, 'open', side_effect=swapping_open):
            with self.assertRaises((OSError, module.Rejected)):
                run.restore()
        self.assertTrue(swapped)
        self.assertIsNone(run.run_id)

    def test_change_during_read(self):
        for kind in ('file', 'file_mode', 'directory', 'directory_mode'):
            with self.subTest(kind=kind):
                report, root = self.original()
                module, run = self.open_run(report)
                original = os.read
                changed = False
                def changing_read(fd, count):
                    nonlocal changed
                    data = original(fd, count)
                    if not changed:
                        changed = True
                        if kind == 'file':
                            file = root / 'result.json'
                            before = file.read_bytes()
                            file.unlink()
                            file.write_bytes(before)
                        elif kind == 'file_mode':
                            (root / 'result.json').chmod(0o644)
                        elif kind == 'directory':
                            (root / 'bundle').rename(root / 'held-bundle')
                            (root / 'bundle').mkdir(mode=0o700)
                        else:
                            (root / 'bundle').chmod(0o755)
                    return data
                with patch.object(module.os, 'read', side_effect=changing_read):
                    with self.assertRaises(module.Rejected):
                        run.restore()
                self.assertIsNone(run.run_id)

    def test_target_swap_before_write(self):
        report, root = self.original()
        module, run = self.open_run(report)
        original = run._write
        changed = False
        def changing_write(directory, name, data):
            nonlocal changed
            if not changed:
                changed = True
                target = Path('/tmp') / run.run_id
                (target / 'restored').rename(target / 'detached')
                (target / 'restored').symlink_to(root / 'bundle', target_is_directory=True)
            return original(directory, name, data)
        with patch.object(run, '_write', side_effect=changing_write):
            with self.assertRaises(module.Rejected):
                run.restore()
        target = Path('/tmp') / run.run_id
        self.addCleanup(shutil.rmtree, target)
        self.assertEqual(list((target / 'detached').iterdir()), [])
        self.assertFalse((target / 'recovery-result.json').exists())

    def test_partial_failure_retained_and_not_resumed(self):
        report, root = self.original()
        module, run = self.open_run(report)
        original = os.write
        calls = 0
        def failing_write(fd, data):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('private secret path')
            return original(fd, data[:3])
        with patch.object(module.os, 'write', side_effect=failing_write):
            with self.assertRaises(OSError):
                run.restore()
        target = Path('/tmp') / run.run_id
        self.addCleanup(shutil.rmtree, target)
        self.assertEqual((target / 'restored/firmware.bin').read_bytes(), module.FIXTURES['firmware.bin'][:3])
        self.assertFalse((target / 'recovery-result.json').exists())
        self.assertTrue((root / 'bundle/manifest.json').exists())
        with self.assertRaises(module.Rejected):
            run.restore()
        run.close()
        self.assertEqual(run.fds, [])

    def test_short_writes_complete(self):
        report, _ = self.original()
        module, run = self.open_run(report)
        original = os.write
        with patch.object(module.os, 'write', side_effect=lambda fd, data: original(fd, data[:3])):
            result = run.restore()
        self.addCleanup(shutil.rmtree, Path('/tmp') / result['run_id'])
        self.assertEqual(result['status'], 'VERIFIED')
        run.close()
        self.assertEqual(run.fds, [])

    def test_unsupported_platform_no_allocation(self):
        module = self.module()
        report, _ = self.original()
        with patch.object(module, 'supported', return_value=False), patch.object(module.os, 'open') as opened:
            with self.assertRaises(module.Rejected):
                module.RetainedRestore(report['run_id'], report['manifest_sha256'])
            opened.assert_not_called()

    def test_cli_rejects_unbounded_and_path_arguments_without_echo(self):
        module = self.module()
        from contextlib import redirect_stdout
        import io
        for args in ([], ['private/path', 'f' * 64], ['x' * 100000, 'f' * 64],
                     ['software-rehearsal-' + 'A' * 32, 'f' * 64],
                     ['software-rehearsal-' + 'a' * 32, 'F' * 64],
                     ['software-rehearsal-' + 'a' * 32, 'f' * 64, '--target=private']):
            with self.subTest(length=len(args)):
                output = io.StringIO()
                with redirect_stdout(output), patch.object(module.os, 'open') as opened:
                    self.assertEqual(module.main(args), 2)
                    opened.assert_not_called()
                self.assertEqual(json.loads(output.getvalue()), {
                    'scope': 'SYNTHETIC_ONLY', 'status': 'BLOCKED', 'reason': 'ARGUMENTS_REJECTED'})

    def test_cli_failure_redacted_and_help(self):
        module = self.module()
        from contextlib import redirect_stdout
        import io
        output = io.StringIO()
        with redirect_stdout(output), patch.object(module, 'RetainedRestore', side_effect=OSError('SECRET /private')):
            self.assertEqual(module.main(['software-rehearsal-' + 'a' * 32, 'f' * 64]), 1)
        self.assertNotIn('SECRET', output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['status'], 'BLOCKED')
        with redirect_stdout(io.StringIO()), patch.object(module.os, 'open') as opened:
            self.assertEqual(module.main(['--help']), 0)
            opened.assert_not_called()

    def test_recovery_report_cannot_be_baseline(self):
        report, root = self.original()
        module, run = self.open_run(report)
        result = run.restore()
        target = Path('/tmp') / result['run_id']
        self.addCleanup(shutil.rmtree, target)
        self.assertFalse(module.valid_arguments([result['run_id'], result['manifest_sha256']]))
        (root / 'result.json').write_bytes((target / 'recovery-result.json').read_bytes())
        self.reject_before_target(report)

    def test_write_zero_and_fsync_failures_close_descriptors(self):
        for kind in ('zero', 'fsync'):
            with self.subTest(kind=kind):
                report, root = self.original()
                module, run = self.open_run(report)
                before = {p.name: p.read_bytes() for p in (root / 'bundle').iterdir()}
                with patch.object(module.os, 'write' if kind == 'zero' else 'fsync',
                                  **({'return_value': 0} if kind == 'zero' else {'side_effect': OSError('full disk')})):
                    with self.assertRaises((OSError, module.Rejected)):
                        with run:
                            run.restore()
                target = Path('/tmp') / run.run_id
                self.addCleanup(shutil.rmtree, target)
                self.assertFalse((target / 'recovery-result.json').exists())
                self.assertEqual(run.fds, [])
                self.assertEqual(before, {p.name: p.read_bytes() for p in (root / 'bundle').iterdir()})

    def test_existing_target_file_is_not_overwritten(self):
        report, _ = self.original()
        _, run = self.open_run(report)
        original = run._write
        def injecting_write(directory, name, data):
            if name == 'firmware.bin':
                fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=directory)
                try:
                    os.write(fd, b'keep')
                finally:
                    os.close(fd)
            return original(directory, name, data)
        with patch.object(run, '_write', side_effect=injecting_write):
            with self.assertRaises(FileExistsError):
                run.restore()
        target = Path('/tmp') / run.run_id
        self.addCleanup(shutil.rmtree, target)
        self.assertEqual((target / 'restored/firmware.bin').read_bytes(), b'keep')

    def test_target_permissions_change_during_write_rejected(self):
        report, _ = self.original()
        module, run = self.open_run(report)
        original = os.write
        def changing_write(fd, data):
            result = original(fd, data)
            os.fchmod(fd, 0o644)
            return result
        with patch.object(module.os, 'write', side_effect=changing_write):
            with self.assertRaises(module.Rejected):
                run.restore()
        target = Path('/tmp') / run.run_id
        self.addCleanup(shutil.rmtree, target)
        self.assertFalse((target / 'recovery-result.json').exists())

    def test_constructor_failure_closes_descriptors(self):
        report, root = self.original()
        module = self.module()
        (root / 'bundle').chmod(0o755)
        original = os.close
        closed = []
        def tracking_close(fd):
            closed.append(fd)
            return original(fd)
        with patch.object(module.os, 'close', side_effect=tracking_close):
            with self.assertRaises(module.Rejected):
                module.RetainedRestore(report['run_id'], report['manifest_sha256'])
        self.assertEqual(len(closed), 3)
        for fd in closed:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_root_replaced_after_open(self):
        report, root = self.original()
        module, run = self.open_run(report)
        held = root.with_name(root.name + '-held')
        root.rename(held)
        self.addCleanup(shutil.rmtree, held)
        root.mkdir(mode=0o700)
        with self.assertRaises(module.Rejected):
            run.restore()
        self.assertIsNone(run.run_id)

    def test_final_report_failures_never_leave_verified_disk_evidence(self):
        from contextlib import redirect_stdout
        import io
        for kind in ('write', 'fsync', 'close', 'guard'):
            with self.subTest(kind=kind):
                report, _ = self.original()
                module, run = self.open_run(report)
                original_write, original_fsync, original_close = os.write, os.fsync, os.close
                original_guard = run._guard
                injected = False
                def is_report(fd):
                    return os.readlink('/proc/self/fd/' + str(fd)).endswith('/recovery-result.json')
                def failing_write(fd, data):
                    nonlocal injected
                    if kind == 'write' and is_report(fd):
                        if injected:
                            raise OSError('private write failure')
                        injected = True
                        return original_write(fd, data[:10])
                    return original_write(fd, data)
                def failing_fsync(fd):
                    nonlocal injected
                    if kind == 'fsync' and is_report(fd):
                        injected = True
                        raise OSError('private fsync failure')
                    return original_fsync(fd)
                def failing_close(fd):
                    nonlocal injected
                    fail = kind == 'close' and not injected and is_report(fd)
                    original_close(fd)
                    if fail:
                        injected = True
                        raise OSError('private uncertain close result')
                def failing_guard():
                    nonlocal injected
                    original_guard()
                    if kind == 'guard' and any(name == 'recovery-result.json' for _, name in run.snapshots):
                        injected = True
                        raise module.Rejected('FINAL_GUARD_FAILED')
                output = io.StringIO()
                with patch.object(module, 'RetainedRestore', return_value=run), \
                        patch.object(module.os, 'write', side_effect=failing_write), \
                        patch.object(module.os, 'fsync', side_effect=failing_fsync), \
                        patch.object(module.os, 'close', side_effect=failing_close), \
                        patch.object(run, '_guard', side_effect=failing_guard), redirect_stdout(output):
                    self.assertEqual(module.main([report['run_id'], report['manifest_sha256']]), 1)
                target = Path('/tmp') / run.run_id
                self.addCleanup(shutil.rmtree, target)
                self.assertTrue(injected)
                self.assertEqual(json.loads(output.getvalue())['status'], 'BLOCKED')
                evidence = (target / 'recovery-result.json').read_bytes()
                self.assertNotIn(b'VERIFIED', evidence)
                if kind != 'write':
                    self.assertEqual(json.loads(evidence)['status'], 'CANDIDATE')
                self.assertEqual(run.fds, [])

    def test_close_attempts_every_registered_fd_once_and_blocks_cli(self):
        from contextlib import redirect_stdout
        import io
        report, _ = self.original()
        module, run = self.open_run(report)
        original_close = os.close
        attempted = []
        failed = False
        def uncertain_close(fd):
            nonlocal failed
            # close() pops before attempting. Directory closes at exit can be
            # distinguished from per-file closes by fstat.
            is_directory = stat.S_ISDIR(os.fstat(fd).st_mode)
            original_close(fd)
            if is_directory:
                attempted.append(fd)
                if not failed:
                    failed = True
                    raise OSError('uncertain close outcome; do not retry')
        output = io.StringIO()
        with patch.object(module, 'RetainedRestore', return_value=run), \
                patch.object(module.os, 'close', side_effect=uncertain_close), redirect_stdout(output):
            self.assertEqual(module.main([report['run_id'], report['manifest_sha256']]), 1)
        target = Path('/tmp') / run.run_id
        self.addCleanup(shutil.rmtree, target)
        self.assertEqual(len(attempted), 5)
        self.assertEqual(len(set(attempted)), 5)
        self.assertEqual(run.fds, [])
        self.assertEqual(json.loads(output.getvalue())['status'], 'BLOCKED')
        self.assertEqual(json.loads((target / 'recovery-result.json').read_bytes())['status'], 'CANDIDATE')
        for fd in attempted:
            with self.assertRaises(OSError):
                os.fstat(fd)
