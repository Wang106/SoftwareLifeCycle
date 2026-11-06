"""Read-only, descriptor-bound directory capacity observations, not acceptance."""
import errno
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('directory_diagnostics', ROOT / 'scripts/offline_directory_diagnostics.py')
diag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diag)


class DirectoryDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = {role: str(self.root / role) for role in diag.ROLES}
        for path in self.paths.values():
            Path(path).mkdir()
        self.disk = SimpleNamespace(f_bavail=10, f_frsize=4096)

    def report(self, minimum=1):
        return diag.diagnose(self.paths, minimum)

    def cli(self, *extra):
        args = [item for role, path in self.paths.items() for item in ('--' + role, path)]
        return subprocess.run([sys.executable, str(ROOT / 'scripts/offline_directory_diagnostics.py'),
                               *args, '--minimum-free-bytes', '1', *extra], capture_output=True, text=True)

    def test_real_directories(self):
        report = self.report()
        self.assertEqual(report['status'], 'OBSERVATION_ONLY')
        self.assertEqual([x['role'] for x in report['directories']], list(diag.ROLES))
        self.assertTrue(all(x['available_bytes'] >= 0 for x in report['directories']))

    def test_available_not_root_free_and_no_sum(self):
        self.disk.f_bfree = 100000
        with patch.object(diag.os, 'fstatvfs', return_value=self.disk):
            report = self.report(40960)
        self.assertEqual(report['status'], 'OBSERVATION_ONLY')
        self.assertEqual([x['available_bytes'] for x in report['directories']], [40960] * 3)
        self.assertNotIn('total_available_bytes', report)

    def test_low_space_blocks(self):
        with patch.object(diag.os, 'fstatvfs', return_value=self.disk):
            report = self.report(40961)
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertTrue(all(x['status'] == 'BELOW_MINIMUM' for x in report['directories']))

    def test_unknown_capacity_is_not_zero(self):
        for data in (SimpleNamespace(), SimpleNamespace(f_bavail=-1, f_frsize=4096),
                     SimpleNamespace(f_bavail=1, f_frsize=0), SimpleNamespace(f_bavail=True, f_frsize=1),
                     SimpleNamespace(f_bavail=1.5, f_frsize=1), SimpleNamespace(f_bavail=2**64, f_frsize=4096)):
            with self.subTest(data=data), patch.object(diag.os, 'fstatvfs', return_value=data):
                row = self.report()['directories'][0]
                self.assertEqual(row['status'], 'CAPACITY_UNKNOWN')
                self.assertIsNone(row['available_bytes'])

    def test_capacity_error_redacted(self):
        with patch.object(diag.os, 'fstatvfs', side_effect=OSError('SECRET /private/user/name')):
            report = self.report()
        self.assertNotIn('SECRET', json.dumps(report))
        self.assertTrue(all(x['status'] == 'CAPACITY_UNKNOWN' for x in report['directories']))

    def test_missing_preserves_other_roles(self):
        Path(self.paths['logs']).rmdir()
        report = self.report()
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertEqual(report['directories'][0]['status'], 'PATH_UNAVAILABLE')
        self.assertEqual(report['directories'][1]['status'], 'DIRECTORY_OBSERVED')

    def test_leaf_and_parent_symlink_rejected(self):
        link = self.root / 'link'
        link.symlink_to(self.root, target_is_directory=True)
        for value in (str(link), str(link / 'logs')):
            with self.subTest(value=value):
                self.paths['logs'] = value
                self.assertEqual(self.report()['directories'][0]['status'], 'PATH_UNAVAILABLE')

    def test_regular_file_and_fifo_rejected(self):
        file = self.root / 'secret'
        file.write_text('DO NOT READ')
        fifo = self.root / 'pipe'
        os.mkfifo(fifo)
        for value in (file, fifo):
            self.paths['logs'] = str(value)
            self.assertEqual(self.report()['directories'][0]['status'], 'PATH_UNAVAILABLE')

    def test_invalid_paths_and_threshold_fail_before_open(self):
        for value in ('relative', '/tmp/../private', '/tmp/./secret', '//tmp', '/tmp/', '/tmp/\x00', '/tmp/\n', '/' + 'a' * 4096):
            with self.subTest(value=value), patch.object(diag.os, 'open') as opened:
                self.paths['logs'] = value
                self.assertEqual(self.report()['status'], 'BLOCKED')
                opened.assert_not_called()
        self.paths['logs'] = str(self.root)
        for value in (-1, True, 1.1, '1', 2**63):
            with self.subTest(value=value), patch.object(diag.os, 'open') as opened:
                self.assertEqual(self.report(value)['status'], 'BLOCKED')
                opened.assert_not_called()

    def test_unsupported_fails_closed(self):
        with patch.object(diag, 'supported', return_value=False), patch.object(diag.os, 'open') as opened:
            report = self.report()
        opened.assert_not_called()
        self.assertTrue(all(x['status'] == 'UNSUPPORTED' for x in report['directories']))

    def test_rename_after_open_observes_original_fd(self):
        original = os.fstatvfs
        expected_inode = os.stat(self.paths['logs']).st_ino
        seen = []
        def replace(fd):
            seen.append(os.fstat(fd).st_ino)
            if len(seen) == 1:
                Path(self.paths['logs']).rename(self.root / 'old')
                Path(self.paths['logs']).symlink_to(self.paths['backups'], target_is_directory=True)
            return original(fd)
        with patch.object(diag.os, 'fstatvfs', side_effect=replace):
            report = self.report()
        self.assertEqual(seen[0], expected_inode)
        self.assertEqual(report['directories'][0]['status'], 'DIRECTORY_OBSERVED')

    def test_parent_rename_during_walk_keeps_open_parent(self):
        parent = self.root / 'parent'
        parent.mkdir()
        (parent / 'child').mkdir()
        self.paths['logs'] = str(parent / 'child')
        original = os.open
        expected = os.stat(parent / 'child').st_ino
        seen = []
        def racing_open(name, flags, **kwargs):
            fd = original(name, flags, **kwargs)
            if name == 'parent':
                parent.rename(self.root / 'old-parent')
                parent.symlink_to(self.paths['backups'], target_is_directory=True)
            return fd
        def capacity(fd):
            seen.append(os.fstat(fd).st_ino)
            return self.disk
        with patch.object(diag, 'supported', return_value=True), patch.object(diag.os, 'open', side_effect=racing_open), patch.object(diag.os, 'fstatvfs', side_effect=capacity):
            self.assertEqual(self.report()['status'], 'OBSERVATION_ONLY')
        self.assertEqual(seen[0], expected)

    def test_fds_closed_on_success_and_errors(self):
        original = os.open
        for failure in (False, True):
            opened = []
            def tracked(*args, **kwargs):
                fd = original(*args, **kwargs)
                opened.append(fd)
                return fd
            with patch.object(diag, 'supported', return_value=True), patch.object(diag.os, 'open', side_effect=tracked), patch.object(diag.os, 'fstatvfs', side_effect=OSError('private') if failure else None, return_value=self.disk):
                self.report()
            for fd in opened:
                with self.assertRaises(OSError):
                    os.fstat(fd)

    def test_no_listing_content_reads_or_target_writes(self):
        with patch('builtins.open', side_effect=AssertionError('file content')), patch.object(diag.os, 'listdir', side_effect=AssertionError('listing')), patch.object(diag.os, 'scandir', side_effect=AssertionError('listing')), patch.object(diag.os, 'read', side_effect=AssertionError('read')), patch.object(diag.os, 'write', side_effect=AssertionError('write')):
            self.assertEqual(self.report()['status'], 'OBSERVATION_ONLY')

    def test_root_and_zero_available_are_valid_observations(self):
        self.paths['logs'] = '/'
        with patch.object(diag.os, 'fstatvfs', return_value=SimpleNamespace(f_bavail=0, f_frsize=4096)):
            result = self.report(0)
        self.assertEqual(result['status'], 'OBSERVATION_ONLY')
        self.assertEqual(result['directories'][0]['available_bytes'], 0)

    def test_each_required_capability_fails_closed(self):
        for name, value in (('O_NOFOLLOW', None), ('O_DIRECTORY', 0), ('fstatvfs', None), ('supports_dir_fd', set())):
            with self.subTest(name=name), patch.object(diag.os, name, value):
                self.assertTrue(all(row['status'] == 'UNSUPPORTED' for row in self.report()['directories']))

    def test_fstat_error_closes_root_and_child(self):
        original_open, original_stat = os.open, os.fstat
        for fail_on in (1, 2):
            opened = []
            count = 0
            def tracked(*args, **kwargs):
                fd = original_open(*args, **kwargs)
                opened.append(fd)
                return fd
            def failing(fd):
                nonlocal count
                count += 1
                if count == fail_on:
                    raise OSError('PRIVATE')
                return original_stat(fd)
            with patch.object(diag, 'supported', return_value=True), patch.object(diag.os, 'open', side_effect=tracked), patch.object(diag.os, 'fstat', side_effect=failing):
                self.assertEqual(self.report()['directories'][0]['status'], 'PATH_UNAVAILABLE')
            for fd in opened:
                with self.assertRaises(OSError):
                    original_stat(fd)

    def test_open_flags_are_readonly_directories_without_follow(self):
        original = os.open
        def checked(name, flags, **kwargs):
            self.assertEqual(flags & os.O_ACCMODE, os.O_RDONLY)
            self.assertTrue(flags & os.O_DIRECTORY)
            self.assertTrue(flags & os.O_NOFOLLOW)
            self.assertFalse(flags & (os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            return original(name, flags, **kwargs)
        with patch.object(diag, 'supported', return_value=True), patch.object(diag.os, 'open', side_effect=checked):
            self.assertEqual(self.report()['status'], 'OBSERVATION_ONLY')

    def test_errno_classification_and_redaction(self):
        for operation in ('open', 'fstatvfs'):
            for number in (errno.EACCES, errno.ENOSYS, errno.ENOTSUP):
                expected = ('UNSUPPORTED' if number != errno.EACCES else
                            'PATH_UNAVAILABLE' if operation == 'open' else 'CAPACITY_UNKNOWN')
                with self.subTest(operation=operation, number=number), patch.object(diag, 'supported', return_value=True), patch.object(diag.os, operation, side_effect=OSError(number, 'PRIVATE /secret/user')):
                    result = self.report()
                self.assertEqual(result['status'], 'BLOCKED')
                self.assertTrue(all(row['status'] == expected for row in result['directories']))
                self.assertTrue(all(row['available_bytes'] is None for row in result['directories']))
                self.assertNotIn('PRIVATE', json.dumps(result))
                self.assertNotIn('/secret/user', json.dumps(result))

    def test_capacity_product_boundaries(self):
        for blocks, fragment, expected in ((diag.MAX_INTEGER, 1, 'DIRECTORY_OBSERVED'),
                                           (diag.MAX_INTEGER // 2 + 1, 2, 'CAPACITY_UNKNOWN')):
            with self.subTest(blocks=blocks), patch.object(diag.os, 'fstatvfs', return_value=SimpleNamespace(f_bavail=blocks, f_frsize=fragment)):
                result = self.report()['directories'][0]
            self.assertEqual(result['status'], expected)
            self.assertEqual(result['available_bytes'], blocks * fragment if expected == 'DIRECTORY_OBSERVED' else None)

    def test_path_length_and_component_boundaries(self):
        # Parser bounds are independent of the host's per-component/path limits.
        for path in ('/' + '/'.join(['x'] * 256), '/' + 'x' * 4095):
            self.assertTrue(diag.valid_path(path))
            args = [item for role in diag.ROLES for item in ('--' + role, path)]
            paths, minimum = diag.parse([*args, '--minimum-free-bytes', str(diag.MAX_INTEGER)])
            self.assertEqual(paths['logs'], path)
            self.assertEqual(minimum, diag.MAX_INTEGER)
        for path in ('/' + '/'.join(['x'] * 257), '/' + 'x' * 4096):
            self.assertFalse(diag.valid_path(path))
            self.paths['logs'] = path
            with patch.object(diag.os, 'open') as opened:
                result = self.report()
            opened.assert_not_called()
            self.assertTrue(all(row['status'] == 'INVALID_INPUT' for row in result['directories']))

    def test_child_open_failure_closes_all_parent_descriptors(self):
        original = os.open
        opened = []
        def failing(name, flags, **kwargs):
            if name == 'logs':
                raise OSError(errno.EACCES, 'PRIVATE')
            fd = original(name, flags, **kwargs)
            opened.append(fd)
            return fd
        with patch.object(diag, 'supported', return_value=True), patch.object(diag.os, 'open', side_effect=failing):
            result = self.report()
        self.assertEqual(result['directories'][0]['status'], 'PATH_UNAVAILABLE')
        self.assertEqual(result['directories'][1]['status'], 'DIRECTORY_OBSERVED')
        for fd in opened:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_cli_success_private_output(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertNotIn(str(self.root), result.stdout)
        self.assertEqual(json.loads(result.stdout)['status'], 'OBSERVATION_ONLY')

    def test_cli_duplicate_unknown_and_bounded_integers(self):
        for extra in (('--logs', '/secret'), ('--private-secret', 'value'), ('--minimum-free-bytes', '9' * 5000)):
            result = self.cli(*extra)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('secret', result.stdout + result.stderr)
            self.assertEqual(len(json.loads(result.stdout)['directories']), 3)

    def test_cli_missing_and_invalid_minimum(self):
        for value in ('-1', '01', '+1', '1.0', 'nan', str(2**63)):
            args = [item for role, path in self.paths.items() for item in ('--' + role, path)]
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/offline_directory_diagnostics.py'), *args, '--minimum-free-bytes', value], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/offline_directory_diagnostics.py')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)

    def test_cli_observation_failure_exit(self):
        Path(self.paths['logs']).rmdir()
        self.assertEqual(self.cli().returncode, 1)


if __name__ == '__main__':
    unittest.main()
