"""Synthetic-only local storage contract; runnable with stdlib unittest."""
import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.services.local_artifact_storage import LocalArtifactStorage, Receipt, StorageError


class LocalArtifactStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = LocalArtifactStorage(str(self.root), enabled=True, max_bytes=16, chunk_bytes=3)
        self.data = b'synthetic'
        self.digest = hashlib.sha256(self.data).hexdigest()

    def stage(self, source=None, **kw):
        receipt = self.store.reserve(expected_bytes=kw.get('size', len(self.data)), sha256=kw.get('digest', self.digest))
        return self.store.stage(receipt, source or io.BytesIO(self.data))

    def test_disabled_has_no_io(self):
        with patch('os.open', side_effect=AssertionError('I/O')):
            store = LocalArtifactStorage('/missing')
            for method, args in [(store.stage, (None, io.BytesIO())), (store.commit, (None,)), (store.inspect, (None,))]:
                with self.assertRaises(StorageError):
                    method(*args)

    def test_stage_commit_and_inspect(self):
        receipt = self.stage()
        self.assertEqual(self.store.inspect(receipt), {'stage': 'verified', 'object': 'missing'})
        self.store.commit(receipt)
        self.assertEqual(self.store.inspect(receipt), {'stage': 'verified', 'object': 'verified'})
        self.assertEqual((self.root / (receipt.object_id + '.blob')).read_bytes(), self.data)
        with self.assertRaises(StorageError):
            self.store.commit(receipt)
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_bounded_reader_and_caller_ownership(self):
        class Reader(io.BytesIO):
            def read(inner, count=-1):
                self.assertGreater(count, 0)
                self.assertLessEqual(count, 3)
                return super().read(count)
        source = Reader(self.data)
        self.stage(source)
        self.assertFalse(source.closed)

    def test_invalid_metadata_before_io(self):
        for size, digest in [(-1, self.digest), (17, self.digest), (True, self.digest), (9, 'bad')]:
            with self.subTest(size=size), patch('os.open', side_effect=AssertionError('I/O')):
                with self.assertRaises(StorageError):
                    self.stage(size=size, digest=digest)

    def test_size_and_digest_failures_retained(self):
        for content in [b'short', self.data + b'extra', b'corrupted']:
            with self.subTest(content=content):
                with self.assertRaises(StorageError) as error:
                    self.stage(io.BytesIO(content))
                receipt = error.exception.receipt
                self.assertIsNotNone(receipt)
                before = sorted(p.name for p in self.root.iterdir())
                self.assertEqual(self.store.inspect(receipt)['object'], 'missing')
                self.assertEqual(before, sorted(p.name for p in self.root.iterdir()))
                self.assertLessEqual((self.root / (receipt.object_id + '.part')).stat().st_size, 9)

    def test_reader_failure_retained(self):
        class Broken:
            def read(self, count):
                raise OSError('synthetic read failure')
        with self.assertRaises(StorageError) as error:
            self.stage(Broken())
        self.assertEqual(self.store.inspect(error.exception.receipt), {'stage': 'mismatch', 'object': 'missing'})

    def test_write_and_fsync_failure_retained(self):
        for target in ['os.write', 'os.fsync']:
            with self.subTest(target=target), patch(target, side_effect=OSError('synthetic failure')):
                with self.assertRaises(StorageError) as error:
                    self.stage()
            self.assertIsNotNone(error.exception.receipt)
            self.assertEqual(self.store.inspect(error.exception.receipt)['object'], 'missing')

    def test_publication_uncertain_and_inspection_read_only(self):
        receipt = self.stage()
        real_link = os.link
        def uncertain(*args, **kwargs):
            real_link(*args, **kwargs)
            raise OSError('lost acknowledgement')
        with patch('os.link', side_effect=uncertain):
            with self.assertRaises(StorageError):
                self.store.commit(receipt)
        with patch('os.write', side_effect=AssertionError()), patch('os.link', side_effect=AssertionError()), patch('os.unlink', side_effect=AssertionError()), patch('os.fsync', side_effect=AssertionError()):
            self.assertEqual(self.store.inspect(receipt), {'stage': 'verified', 'object': 'verified'})

    def test_commit_fsync_failure_retains_both(self):
        receipt = self.stage()
        with patch('os.fsync', side_effect=OSError('synthetic sync failure')):
            with self.assertRaises(StorageError):
                self.store.commit(receipt)
        self.assertEqual(self.store.inspect(receipt)['object'], 'verified')

    def test_corrupt_stage_not_published(self):
        receipt = self.stage()
        (self.root / (receipt.object_id + '.part')).write_bytes(b'corrupted')
        with self.assertRaises(StorageError):
            self.store.commit(receipt)
        self.assertEqual(self.store.inspect(receipt)['object'], 'missing')

    def test_duplicate_final_is_not_overwritten(self):
        receipt = self.stage()
        final = self.root / (receipt.object_id + '.blob')
        final.write_bytes(b'other')
        final.chmod(0o600)
        with self.assertRaises(StorageError):
            self.store.commit(receipt)
        self.assertEqual(final.read_bytes(), b'other')

    def test_root_and_file_path_denials(self):
        for root in ['relative', str(self.root / '..' / self.root.name), str(self.root / 'missing')]:
            with self.subTest(root=root), self.assertRaises(StorageError):
                LocalArtifactStorage(root, enabled=True).inspect(self.store.reserve(expected_bytes=0, sha256=hashlib.sha256(b'').hexdigest()))
        self.root.chmod(0o755)
        with self.assertRaises(StorageError):
            self.stage()
        self.root.chmod(0o700)
        receipt = self.stage()
        stage = self.root / (receipt.object_id + '.part')
        stage.chmod(0o644)
        with self.assertRaises(StorageError):
            self.store.inspect(receipt)
        stage.chmod(0o600)
        alias = self.root / 'alias'
        os.link(stage, alias)
        with self.assertRaises(StorageError):
            self.store.commit(receipt)

    def test_reserved_identity_survives_interrupted_stage(self):
        receipt = self.store.reserve(expected_bytes=9, sha256=self.digest)
        self.assertEqual(list(self.root.iterdir()), [])
        class Interrupted:
            def read(self, count):
                raise KeyboardInterrupt()
        before = len(os.listdir('/proc/self/fd'))
        with self.assertRaises(KeyboardInterrupt):
            self.store.stage(receipt, Interrupted())
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)
        restarted = LocalArtifactStorage(str(self.root), enabled=True)
        self.assertEqual(restarted.inspect(receipt), {'stage': 'mismatch', 'object': 'missing'})
        with self.assertRaises(StorageError):
            restarted.commit(receipt)
        with self.assertRaises(StorageError):
            self.store.stage(receipt, io.BytesIO(self.data))

    def test_failed_stage_and_commit_only_allow_inspection(self):
        receipt = self.store.reserve(expected_bytes=9, sha256=self.digest)
        with patch('os.fsync', side_effect=OSError('sync failed')):
            with self.assertRaises(StorageError):
                self.store.stage(receipt, io.BytesIO(self.data))
        self.assertEqual(self.store.inspect(receipt)['stage'], 'verified')
        with self.assertRaises(StorageError):
            self.store.commit(receipt)
        receipt = self.stage()
        with patch('os.link', side_effect=OSError('link failed')):
            with self.assertRaises(StorageError):
                self.store.commit(receipt)
        with self.assertRaises(StorageError):
            self.store.commit(receipt)
        self.assertEqual(self.store.inspect(receipt)['object'], 'missing')

    def test_short_writes_and_zero_progress(self):
        real_write = os.write
        with patch('os.write', side_effect=lambda fd, data: real_write(fd, data[:1])):
            receipt = self.stage()
        self.assertEqual(self.store.inspect(receipt)['stage'], 'verified')
        with patch('os.write', return_value=0):
            with self.assertRaises(StorageError):
                self.stage()

    def test_bad_reader_results_and_fd_cleanup(self):
        for value in [None, 'text', bytearray(b'a'), b'a' * 100]:
            class Reader:
                def read(self, count):
                    return value
            before = len(os.listdir('/proc/self/fd'))
            with self.subTest(value=value), self.assertRaises(StorageError):
                self.stage(Reader())
            self.assertEqual(len(os.listdir('/proc/self/fd')), before)

    def test_empty_and_exact_limit(self):
        for data in [b'', b'x' * 16]:
            receipt = self.store.reserve(expected_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            self.store.stage(receipt, io.BytesIO(data))
            self.store.commit(receipt)
            self.assertEqual(self.store.inspect(receipt)['object'], 'verified')

    def test_path_identifiers_rejected_before_io(self):
        with patch('os.open', side_effect=AssertionError('I/O')):
            for identifier in ['../escape', '/tmp/a', 'bad', '00000000-0000-0000-0000-000000000000']:
                receipt = Receipt(identifier, 9, self.digest)
                for method in [self.store.commit, self.store.inspect]:
                    with self.assertRaises(StorageError):
                        method(receipt)

    def test_untrusted_ancestor_rejected(self):
        ancestor = self.root / 'shared'
        ancestor.mkdir(mode=0o700)
        child = ancestor / 'private'
        child.mkdir(mode=0o700)
        ancestor.chmod(0o777)
        receipt = self.store.reserve(expected_bytes=9, sha256=self.digest)
        with self.assertRaises(StorageError):
            LocalArtifactStorage(str(child), enabled=True).inspect(receipt)

    def test_close_uncertainty_never_retries_or_leaks_next_fd(self):
        receipt = self.store.reserve(expected_bytes=9, sha256=self.digest)
        real_open, real_close = os.open, os.close
        owned, closed = [], []
        def track_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            owned.append(fd)
            return fd
        def uncertain_close(fd):
            closed.append(fd)
            real_close(fd)
            if len(closed) == 1:
                raise OSError('close acknowledgement lost')
        try:
            with patch('os.open', side_effect=track_open), patch('os.close', side_effect=uncertain_close):
                with self.assertRaises(StorageError):
                    self.store.inspect(receipt)
            self.assertEqual(closed, owned)
        finally:
            for fd in owned:
                if fd not in closed:
                    real_close(fd)

    def test_root_fsync_failure_retains_stage_but_denies_commit(self):
        real_fsync = os.fsync
        calls = []
        def fail_directory(fd):
            calls.append(fd)
            if len(calls) == 2:
                raise OSError('directory sync failure')
            real_fsync(fd)
        with patch('os.fsync', side_effect=fail_directory):
            with self.assertRaises(StorageError) as error:
                self.stage()
        receipt = error.exception.receipt
        self.assertEqual(self.store.inspect(receipt)['stage'], 'verified')
        with self.assertRaises(StorageError):
            self.store.commit(receipt)

    def test_restart_never_resumes_verified_stage(self):
        receipt = self.stage()
        restarted = LocalArtifactStorage(str(self.root), enabled=True)
        self.assertEqual(restarted.inspect(receipt)['stage'], 'verified')
        with self.assertRaises(StorageError):
            restarted.commit(receipt)
        self.assertFalse((self.root / (receipt.object_id + '.blob')).exists())

    def test_stage_collision_preserves_existing_bytes(self):
        receipt = self.stage()
        with self.assertRaises(StorageError):
            self.store.stage(receipt, io.BytesIO(b'changed'))
        self.assertEqual((self.root / (receipt.object_id + '.part')).read_bytes(), self.data)

    def test_post_publication_corruption_is_not_verified(self):
        receipt = self.stage()
        self.store.commit(receipt)
        final = self.root / (receipt.object_id + '.blob')
        final.write_bytes(b'corrupted')
        self.assertEqual(self.store.inspect(receipt), {'stage': 'mismatch', 'object': 'mismatch'})
        final.write_bytes(b'cut')
        self.assertEqual(self.store.inspect(receipt)['object'], 'mismatch')
        final.write_bytes(self.data + b'oversize')
        self.assertEqual(self.store.inspect(receipt)['object'], 'mismatch')

    def test_inspection_ignores_access_time_updates(self):
        receipt = self.stage()
        self.store.commit(receipt)
        path = self.root / (receipt.object_id + '.part')
        info = path.stat()
        os.utime(path, ns=(1, info.st_mtime_ns))
        self.assertEqual(self.store.inspect(receipt), {'stage': 'verified', 'object': 'verified'})

    def test_caller_exception_does_not_hide_close_failure(self):
        import stat
        real_close = os.close
        failed = []
        def close_file_then_fail(fd):
            regular = stat.S_ISREG(os.fstat(fd).st_mode)
            real_close(fd)
            if regular and not failed:
                failed.append(fd)
                raise OSError('regular file close acknowledgement lost')
        try:
            raise ValueError('unrelated caller exception')
        except ValueError:
            with patch('os.close', side_effect=close_file_then_fail):
                with self.assertRaises(StorageError):
                    self.stage()

    def test_failed_repeated_stage_revokes_commit_capability(self):
        receipt = self.stage()
        with self.assertRaises(StorageError):
            self.store.stage(receipt, io.BytesIO(self.data))
        with self.assertRaises(StorageError):
            self.store.commit(receipt)

    def test_import_is_inert(self):
        import importlib
        import app.services.local_artifact_storage as module
        # Execute fresh module source without changing the classes used above.
        spec = importlib.util.spec_from_file_location('app.services.local_artifact_storage', module.__file__)
        fresh = importlib.util.module_from_spec(spec)
        with patch('os.open', side_effect=AssertionError('I/O')), patch('os.mkdir', side_effect=AssertionError('I/O')):
            spec.loader.exec_module(fresh)

    def test_symlink_and_fifo_denials(self):
        receipt = self.stage()
        final = self.root / (receipt.object_id + '.blob')
        final.symlink_to(self.root / (receipt.object_id + '.part'))
        with self.assertRaises(StorageError):
            self.store.inspect(receipt)
        final.unlink()
        os.mkfifo(final, 0o600)
        with self.assertRaises(StorageError):
            self.store.inspect(receipt)
        link = self.root / 'rootlink'
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(StorageError):
            LocalArtifactStorage(str(link), enabled=True).inspect(receipt)


if __name__ == '__main__':
    unittest.main()
