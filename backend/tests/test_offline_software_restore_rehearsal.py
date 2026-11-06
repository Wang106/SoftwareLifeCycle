"""Synthetic-only software restore exercises real files, never company inputs."""
import importlib.util
from pathlib import Path
import shutil
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('software_restore', ROOT / 'scripts/offline_software_restore_rehearsal.py')
restore = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restore)


class SoftwareRestoreTests(unittest.TestCase):
    def test_roundtrip(self):
        with restore.Rehearsal() as run:
            self.addCleanup(shutil.rmtree, Path('/tmp') / run.run_id)
            run.prepare()
            report = run.restore()
            self.assertEqual(report['status'], 'VERIFIED')
            self.assertEqual(report['scope'], 'SYNTHETIC_ONLY')
            for name, data in restore.FIXTURES.items():
                self.assertEqual((Path('/tmp') / run.run_id / 'restored' / name).read_bytes(), data)

    def new_run(self):
        run = restore.Rehearsal()
        self.addCleanup(run.close)
        root = Path('/tmp') / run.run_id
        self.addCleanup(shutil.rmtree, root)
        run.prepare()
        return run, root

    def blocked(self, run):
        with self.assertRaises((restore.Rejected, OSError)):
            run.restore()

    def test_corrupt_bundle(self):
        run, root = self.new_run()
        (root / 'bundle/firmware.bin').write_bytes(b'x' * len(restore.FIXTURES['firmware.bin']))
        self.blocked(run)
        self.assertFalse((root / 'restored').exists())

    def test_missing_bundle_file(self):
        run, root = self.new_run()
        (root / 'bundle/firmware.bin').unlink()
        self.blocked(run)

    def test_extra_bundle_file(self):
        run, root = self.new_run()
        (root / 'bundle/extra').touch()
        self.blocked(run)

    def test_many_entries_are_bounded(self):
        run, root = self.new_run()
        for index in range(20):
            (root / 'bundle' / str(index)).touch()
        self.blocked(run)

    def test_manifest_and_content_forgery(self):
        import hashlib
        import json
        run, root = self.new_run()
        data = b'forged bytes'
        (root / 'bundle/firmware.bin').write_bytes(data)
        manifest = json.loads(run.manifest)
        row = next(row for row in manifest['files'] if row['path'] == 'firmware.bin')
        row.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
        (root / 'bundle/manifest.json').write_text(json.dumps(manifest, sort_keys=True, separators=(',', ':')))
        self.blocked(run)

    def test_manifest_paths_and_invalid_json_are_never_followed(self):
        import json
        for value in ('../escape', '/tmp/escape', 'source/../escape', 'x\\y', '', '\x00'):
            with self.subTest(path=value):
                run, root = self.new_run()
                data = json.loads(run.manifest)
                data['files'][0]['path'] = value
                (root / 'bundle/manifest.json').write_text(json.dumps(data))
                self.blocked(run)
                self.assertFalse((root / 'restored').exists())
        run, root = self.new_run()
        (root / 'bundle/manifest.json').write_bytes(b'{' * 10000)
        self.blocked(run)

    def test_manifest_bound_to_run(self):
        run, root = self.new_run()
        other, _ = self.new_run()
        (root / 'bundle/manifest.json').write_bytes(other.manifest)
        self.blocked(run)

    def test_symlink_file(self):
        run, root = self.new_run()
        file = root / 'bundle/firmware.bin'
        file.unlink()
        file.symlink_to(root / 'source/firmware.bin')
        self.blocked(run)

    def test_hardlink_file(self):
        import os
        run, root = self.new_run()
        file = root / 'bundle/firmware.bin'
        file.unlink()
        os.link(root / 'source/firmware.bin', file)
        self.blocked(run)

    def test_fifo_without_blocking(self):
        import os
        run, root = self.new_run()
        file = root / 'bundle/firmware.bin'
        file.unlink()
        os.mkfifo(file)
        self.blocked(run)

    def test_directory_instead_of_file(self):
        run, root = self.new_run()
        file = root / 'bundle/firmware.bin'
        file.unlink()
        file.mkdir()
        self.blocked(run)

    def test_existing_targets_preserved(self):
        for kind in ('empty', 'populated', 'symlink'):
            with self.subTest(kind=kind):
                run, root = self.new_run()
                target = root / 'restored'
                if kind == 'symlink':
                    target.symlink_to(root / 'source', target_is_directory=True)
                else:
                    target.mkdir()
                    if kind == 'populated':
                        (target / 'keep').write_bytes(b'keep')
                self.blocked(run)
                self.assertTrue(target.exists())
                if kind == 'populated':
                    self.assertEqual((target / 'keep').read_bytes(), b'keep')
                self.assertFalse((root / 'result.json').exists())

    def test_bundle_directory_replaced(self):
        run, root = self.new_run()
        (root / 'bundle').rename(root / 'old_bundle')
        (root / 'bundle').symlink_to(root / 'source', target_is_directory=True)
        self.blocked(run)

    def test_source_directory_replaced(self):
        run, root = self.new_run()
        (root / 'source').rename(root / 'old_source')
        (root / 'source').mkdir()
        self.blocked(run)
        self.assertFalse((root / 'restored').exists())

    def test_read_swap_between_stat_and_open(self):
        import os
        from unittest.mock import patch
        run, root = self.new_run()
        original = os.open
        swapped = False
        def swapping_open(name, flags, *args, **kwargs):
            nonlocal swapped
            if name == 'firmware.bin' and not swapped:
                swapped = True
                file = root / 'bundle/firmware.bin'
                file.rename(root / 'bundle/old')
                file.symlink_to(root / 'source/firmware.bin')
            return original(name, flags, *args, **kwargs)
        with patch.object(restore.os, 'open', side_effect=swapping_open):
            self.blocked(run)
        self.assertTrue(swapped)
        self.assertFalse((root / 'restored').exists())

    def test_file_replaced_during_read(self):
        import os
        from unittest.mock import patch
        run, root = self.new_run()
        original = os.read
        replaced = False
        def swapping_read(fd, size):
            nonlocal replaced
            data = original(fd, size)
            if not replaced:
                replaced = True
                file = root / 'bundle/manifest.json'
                file.unlink()
                file.write_bytes(run.manifest)
            return data
        with patch.object(restore.os, 'read', side_effect=swapping_read):
            self.blocked(run)
        self.assertTrue(replaced)

    def test_target_swap_before_write_never_follows_replacement(self):
        from unittest.mock import patch
        run, root = self.new_run()
        original = run._write
        swapped = False
        def swapping_write(directory, name, data):
            nonlocal swapped
            if not swapped:
                swapped = True
                (root / 'restored').rename(root / 'detached')
                (root / 'restored').symlink_to(root / 'source', target_is_directory=True)
            return original(directory, name, data)
        with patch.object(run, '_write', side_effect=swapping_write):
            self.blocked(run)
        self.assertEqual(list((root / 'detached').iterdir()), [])
        for name, data in restore.FIXTURES.items():
            self.assertEqual((root / 'source' / name).read_bytes(), data)

    def test_failure_retains_partial_evidence_no_resume(self):
        import os
        from unittest.mock import patch
        run, root = self.new_run()
        original = os.write
        count = 0
        def failing_write(fd, data):
            nonlocal count
            count += 1
            if count == 2:
                raise PermissionError('private path and secret')
            return original(fd, data[:3])
        with patch.object(restore.os, 'write', side_effect=failing_write):
            self.blocked(run)
        self.assertEqual((root / 'restored/firmware.bin').read_bytes(), restore.FIXTURES['firmware.bin'][:3])
        self.assertFalse((root / 'result.json').exists())
        self.blocked(run)
        run.close()
        self.assertEqual(run.fds, [])
        self.assertTrue((root / 'bundle/manifest.json').exists())

    def test_short_writes_complete(self):
        import os
        from unittest.mock import patch
        run, root = self.new_run()
        original = os.write
        with patch.object(restore.os, 'write', side_effect=lambda fd, data: original(fd, data[:7])):
            self.assertEqual(run.restore()['status'], 'VERIFIED')

    def test_zero_write_rejected(self):
        from unittest.mock import patch
        run, _ = self.new_run()
        with patch.object(restore.os, 'write', return_value=0):
            self.blocked(run)

    def test_create_collision_never_overwrites(self):
        from unittest.mock import patch
        run, root = self.new_run()
        with patch.object(restore.secrets, 'token_hex', return_value=run.run_id.removeprefix('software-rehearsal-')):
            with self.assertRaises(FileExistsError):
                restore.Rehearsal()
        self.assertTrue((root / 'bundle/manifest.json').exists())

    def test_repeated_restore_and_prepare_rejected(self):
        run, _ = self.new_run()
        with self.assertRaises(restore.Rejected):
            run.prepare()
        run.restore()
        self.blocked(run)

    def test_cli_rejects_sources_targets_and_cleanup_without_echo(self):
        import contextlib
        import io
        for args in (['--source', '/secret'], ['--restore', '/secret'], ['--cleanup'], ['/secret']):
            with self.subTest(args=args):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(restore.main(args), 2)
                self.assertNotIn('/secret', output.getvalue())
                self.assertIn('ARGUMENTS_REJECTED', output.getvalue())

    def test_cli_failure_is_redacted(self):
        import contextlib
        import io
        from unittest.mock import patch
        output = io.StringIO()
        with patch.object(restore, 'Rehearsal', side_effect=PermissionError('/private/secret')):
            with contextlib.redirect_stdout(output):
                self.assertEqual(restore.main([]), 1)
        self.assertNotIn('/private', output.getvalue())
        self.assertNotIn('secret', output.getvalue())

    def test_unsupported_platform_and_failed_constructor_close_fds(self):
        import os
        from unittest.mock import patch
        before = len(os.listdir('/proc/self/fd'))
        with patch.object(restore, 'supported', return_value=False):
            with self.assertRaises(restore.Rejected):
                restore.Rehearsal()
        with patch.object(restore, 'supported', return_value=True), \
                patch.object(restore.os, 'mkdir', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):
                restore.Rehearsal()
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)

    def test_failure_and_success_close_file_descriptors(self):
        import os
        before = len(os.listdir('/proc/self/fd'))
        run, root = self.new_run()
        (root / 'bundle/firmware.bin').write_bytes(b'bad')
        self.blocked(run)
        run.close()
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)
        run, _ = self.new_run()
        run.restore()
        run.close()
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)
