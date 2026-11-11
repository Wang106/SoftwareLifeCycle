"""Bounded retained-package IO tests; dependency stubs never run a database."""
import ast
import copy
from contextlib import ExitStack
import json
import re
import subprocess
import uuid
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'app/ops/retained_synthetic_restore.py'


def module():
    backup = types.ModuleType('app.ops.postgresql_backup_restore')
    backup.RehearsalError = RuntimeError
    ops = types.ModuleType('app.ops')
    ops.postgresql_backup_restore = backup
    spec = importlib.util.spec_from_file_location('bounded_recovery_test', SCRIPT)
    result = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'psycopg': types.ModuleType('psycopg'),
                                 'app': types.ModuleType('app'), 'app.ops': ops,
                                 'app.ops.postgresql_backup_restore': backup}):
        spec.loader.exec_module(result)
    return result


class RetainedInputBoundsTests(unittest.TestCase):
    def setUp(self):
        self.m = module()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'input'

    def test_oversized_json_rejected(self):
        self.path.write_bytes(b'{"padding":"' + b'x' * 65536 + b'"}')
        with self.assertRaisesRegex(RuntimeError, 'limit'):
            self.m.read_object(self.path)

    def test_json_boundary_and_invalid_values(self):
        self.path.write_bytes(b'{}' + b' ' * (65536 - 2))
        self.assertEqual(self.m.read_object(self.path), {})
        for value in (b'[]', b'\xff', b'{'):
            self.path.write_bytes(value)
            with self.assertRaises(RuntimeError):
                self.m.read_object(self.path)

    def test_copy_streams_and_preserves_original(self):
        data = b'archive' * 20000
        self.path.write_bytes(data)
        destination = self.root / 'snapshot'
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('whole-file read')):
            self.m.copy_snapshot(self.path, destination, len(data), hashlib.sha256(data).hexdigest(), 64 * 1024 * 1024)
        self.assertEqual(destination.read_bytes(), data)
        self.assertEqual(self.path.read_bytes(), data)

    def test_copy_rejects_changed_truncated_and_grown_inputs(self):
        original = b'original'
        for changed in (b'change!!', b'short', b'original-more'):
            self.path.write_bytes(changed)
            destination = self.root / ('snapshot' + str(len(changed)))
            with self.assertRaises(RuntimeError):
                self.m.copy_snapshot(self.path, destination, len(original), hashlib.sha256(original).hexdigest(), 64)

    def test_copy_refuses_existing_destination(self):
        self.path.write_bytes(b'archive')
        destination = self.root / 'snapshot'
        destination.write_bytes(b'keep')
        with self.assertRaises((RuntimeError, FileExistsError)):
            self.m.copy_snapshot(self.path, destination, 7, hashlib.sha256(b'archive').hexdigest(), 64)
        self.assertEqual(destination.read_bytes(), b'keep')

    def test_stream_limit_and_nonregular_inputs(self):
        self.path.write_bytes(b'x' * 65)
        with self.assertRaisesRegex(RuntimeError, 'limit'):
            list(self.m.bounded_chunks(self.path, 64))
        link = self.root / 'link'
        link.symlink_to(self.path)
        for path in (link, self.root, self.root / 'missing'):
            with self.assertRaises(RuntimeError):
                list(self.m.bounded_chunks(path, 64))

    def test_growth_and_truncation_during_stream_are_rejected(self):
        for operation in ('grow', 'truncate', 'replace'):
            with self.subTest(operation=operation):
                self.path.write_bytes(b'x' * 20)
                with patch.object(self.m, 'COPY_CHUNK_BYTES', 4):
                    chunks = self.m.bounded_chunks(self.path, 24)
                    self.assertEqual(next(chunks), b'xxxx')
                    if operation == 'grow':
                        with self.path.open('ab') as stream:
                            stream.write(b'y' * 20)
                    elif operation == 'truncate':
                        self.path.write_bytes(b'x')
                    else:
                        replacement = self.root / 'replacement'
                        replacement.write_bytes(b'x' * 20)
                        replacement.replace(self.path)
                    with self.assertRaises(RuntimeError):
                        list(chunks)

    def test_reads_are_chunk_bounded_including_eof_probe(self):
        self.path.write_bytes(b'x' * 20)
        requests = []
        original_open = Path.open
        class Reader:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def fileno(self):
                return self.stream.fileno()
            def read(self, size):
                requests.append(size)
                return self.stream.read(size)
        def open_reader(path, *args, **kwargs):
            return Reader(original_open(path, *args, **kwargs))
        with patch.object(Path, 'open', open_reader), patch.object(self.m, 'COPY_CHUNK_BYTES', 4):
            self.assertEqual(b''.join(self.m.bounded_chunks(self.path, 20)), b'x' * 20)
        self.assertTrue(all(0 < size <= 4 for size in requests))
        self.assertEqual(requests[-1], 1)

    def test_actual_validation_caps_archive_growth_before_native_catalog(self):
        # Execute unchanged production helpers and the existing canonical fixture,
        # stubbing only native calls/dependencies, never the verification path.
        backup = self.m.backup
        backup.__dict__.update(hashlib=hashlib, Path=Path, json=json, re=re, uuid=uuid,
                               RUN_ID_PATTERN=re.compile(r'^[0-9a-f]{12}$'),
                               DATABASE_PREFIX='slc_rehearsal_')
        names = {'fixture_ids', 'canonical_fixture', 'ownership_proof_path',
                 'owned_database_name', 'archive_digest', 'verify_archive', 'write_manifest'}
        def definitions(path, names, namespace):
            tree = ast.parse(path.read_text())
            selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
            source = 'from __future__ import annotations\n' + '\n'.join(ast.unparse(node) for node in selected)
            exec(compile(source, str(path), 'exec'), namespace)
        definitions(SCRIPT.with_name('postgresql_backup_restore.py'), names, backup.__dict__)
        fixture = dict(backup=backup, recovery=self.m, OLD_RUN='0123456789ab',
                       Path=Path, copy=copy, subprocess=subprocess)
        definitions(Path(__file__).with_name('test_retained_synthetic_restore.py'), {'package'}, fixture)
        backup.native_version = lambda *args: None
        backup._native = lambda *args: None
        with ExitStack() as stack:
            class MonkeyPatch:
                def setattr(self, obj, name, value):
                    stack.enter_context(patch.object(obj, name, value))
            archive, manifest, baseline = fixture['package'](self.root, MonkeyPatch())
            original_open = Path.open
            requests, returned = [], []
            class GrowingReader:
                def __init__(self, stream):
                    self.stream = stream
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    self.stream.close()
                def read(self, size):
                    if not requests:
                        with original_open(archive, 'ab') as writer:
                            writer.write(b'x' * 100)
                    requests.append(size)
                    result = self.stream.read(size)
                    returned.append(len(result))
                    return result
            def growing_open(path, mode='r', *args, **kwargs):
                stream = original_open(path, mode, *args, **kwargs)
                return GrowingReader(stream) if path == archive and mode == 'rb' else stream
            with patch.object(self.m, 'MAX_ARCHIVE_BYTES', 32), patch.object(Path, 'open', growing_open), patch.object(backup, '_native') as native:
                with self.assertRaisesRegex(RuntimeError, 'limit'):
                    self.m.validate_package(None, archive, manifest, baseline)
                native.assert_not_called()
            self.assertTrue(requests)
            self.assertLessEqual(max(requests), 33)
            self.assertEqual(sum(returned), 33)
            for invalid_limit in (-2, True, 1.5):
                with self.assertRaisesRegex(RuntimeError, 'limit'):
                    backup.archive_digest(archive, max_bytes=invalid_limit)
            data = archive.read_bytes()
            expected = hashlib.sha256(data).hexdigest()
            self.assertEqual(backup.archive_digest(archive), expected)
            self.assertEqual(backup.archive_digest(archive, max_bytes=len(data)), expected)
            with self.assertRaisesRegex(RuntimeError, 'limit'):
                backup.archive_digest(archive, max_bytes=len(data) - 1)

    def test_archive_limit_precedes_metadata_or_native_work(self):
        self.path.write_bytes(b'x' * 65)
        with patch.object(self.m, 'MAX_ARCHIVE_BYTES', 64, create=True), patch.object(self.m, 'read_object') as read:
            with self.assertRaises(RuntimeError):
                self.m.validate_package(None, self.path, self.root / 'manifest', self.root / 'baseline')
            read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
