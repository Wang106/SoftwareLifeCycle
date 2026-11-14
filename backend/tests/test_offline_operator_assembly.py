"""Real tiny local copies only: no runnable image, resource or deployment evidence."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'backend' / 'tests'))
import test_offline_image_bundle as fixtures
import offline_image_bundle as bundle
import offline_operator_assembly as assembly

COMMIT = fixtures.COMMIT
OUTPUT_FILES = {'api.tar', 'web.tar', 'manifest.json', 'operator.json'}


class OperatorAssemblyTests(unittest.TestCase):
    def setUp(self):
        # Import the fixture module, not an aliased TestCase that pytest recollects.
        self.fixture = fixtures.ImageBundleTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        (self.fixture.source / 'database.env').write_text('PRIVATE_DATABASE')
        self.fixture.ready()
        self.source = self.fixture.dest
        self.dest = self.root / 'operator'
        self.digest = self.fixture.result['manifest_sha256']

    def assemble(self, **kwargs):
        return assembly.assemble(self.source, self.dest,
            expected_commit=kwargs.get('expected_commit', COMMIT),
            expected_manifest_sha256=kwargs.get('expected_manifest_sha256', self.digest))

    def snapshot(self):
        return {p.name: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ino)
                for p in self.source.iterdir()}

    def rewrite_manifest(self, manifest):
        raw = bundle.canonical(manifest)
        (self.source / 'manifest.json').write_bytes(raw)
        self.digest = hashlib.sha256(raw).hexdigest()

    def cli(self, extra=()):
        return ['--run', 'assemble', str(self.source), str(self.dest),
                '--expected-commit', COMMIT, '--expected-manifest-sha256', self.digest, *extra]

    def test_real_export_verify_assemble_preflight_refuses_and_original_verifies(self):
        bundle.verify_bundle(self.source, expected_commit=COMMIT, expected_manifest_sha256=self.digest)
        before = self.snapshot()
        with patch('subprocess.run', side_effect=AssertionError('must not spawn')), \
             patch('socket.create_connection', side_effect=AssertionError('must not connect')), \
             patch.object(tarfile.TarFile, 'extractall', side_effect=AssertionError('must not extract')), \
             patch.object(os, 'link', side_effect=AssertionError('must not link')), \
             patch.object(os, 'rename', side_effect=AssertionError('must not move')):
            receipt = self.assemble()
        self.assertEqual({p.name for p in self.dest.iterdir()}, OUTPUT_FILES)
        self.assertEqual(json.loads((self.dest / 'manifest.json').read_bytes()), self.fixture.manifest)
        self.assertEqual(json.loads((self.dest / 'operator.json').read_bytes()),
                         json.loads((ROOT / 'deploy/offline-readonly/operator.example.json').read_bytes()))
        self.assertEqual(stat.S_IMODE(self.dest.stat().st_mode), 0o700)
        for name in OUTPUT_FILES:
            self.assertEqual(stat.S_IMODE((self.dest / name).stat().st_mode), 0o600)
            self.assertEqual((self.dest / name).stat().st_nlink, 1)
        for role in ('api', 'web'):
            source, dest = self.source / (role + '.tar'), self.dest / (role + '.tar')
            self.assertEqual(source.read_bytes(), dest.read_bytes())
            self.assertNotEqual((source.stat().st_dev, source.stat().st_ino),
                                (dest.stat().st_dev, dest.stat().st_ino))
        with self.assertRaisesRegex(bundle.preflight.Invalid, 'operator scope'):
            bundle.preflight.validate(self.dest)
        with self.assertRaises(bundle.BundleError):
            bundle.verify_bundle(self.dest, expected_commit=COMMIT,
                                 expected_manifest_sha256=receipt['manifest_sha256'])
        bundle.verify_bundle(self.source, expected_commit=COMMIT, expected_manifest_sha256=self.digest)
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn('PRIVATE', (self.dest / 'operator.json').read_text())
        self.assertNotIn('PRIVATE', (self.dest / 'manifest.json').read_text())

    def test_receipt_is_fixed_safe_nonacceptance_data_only(self):
        result = self.assemble()
        expected = {'status': 'OPERATOR_DIRECTORY_ASSEMBLED_NOT_READY', 'source_commit': COMMIT,
            'handoff_manifest_sha256': self.digest,
            'manifest_sha256': hashlib.sha256((self.dest / 'manifest.json').read_bytes()).hexdigest(),
            'operator_sha256': hashlib.sha256((self.dest / 'operator.json').read_bytes()).hexdigest(),
            'archive_count': 2, 'file_count': 4,
            'archive_bytes': sum(self.fixture.manifest['images'][r]['size'] for r in ('api', 'web')),
            'operator_ready': False, 'application_started': False, 'database_started': False,
            'provenance_verified': False, 'offline_accepted': False, 'deployment_approved': False,
            'limitations': ['Trusted local Linux filesystem only', 'Hashes are not signatures or provenance',
                'Database prerequisites and operator approval are not supplied',
                'No runtime, deployment or offline acceptance']}
        self.assertEqual(result, expected)
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_both_expected_values_are_strict_and_checked_before_creation(self):
        for commit, digest in ((None, None), (True, self.digest), ('A' * 40, self.digest),
                (COMMIT, 'A' * 64), ('b' * 40, self.digest), (COMMIT, 'b' * 64)):
            with self.subTest(commit=commit, digest=digest):
                with self.assertRaises(assembly.AssemblyError):
                    self.assemble(expected_commit=commit, expected_manifest_sha256=digest)
                self.assertFalse(self.dest.exists())

    def test_all_five_source_files_required_and_no_extra_input(self):
        for name in bundle.FILES | {'COMPLETE'}:
            with self.subTest(name=name):
                path, hidden = self.source / name, self.root / name
                path.rename(hidden)
                with self.assertRaises(assembly.AssemblyError): self.assemble()
                self.assertFalse(self.dest.exists())
                hidden.rename(path)
        (self.source / 'database.env').write_text('PRIVATE_SECRET')
        with self.assertRaises(assembly.AssemblyError): self.assemble()
        self.assertFalse(self.dest.exists())

    def test_nonempty_marker_tampered_archive_and_evidence_fail_before_mkdir(self):
        for name in ('COMPLETE', 'api.tar', 'web.tar', 'evidence.json'):
            path = self.source / name
            raw = path.read_bytes()
            with self.subTest(name=name):
                path.write_bytes(raw + b'X')
                with self.assertRaises(assembly.AssemblyError): self.assemble()
                self.assertFalse(self.dest.exists())
                path.write_bytes(raw)

    def test_strict_source_schema_types_with_matching_trusted_hash(self):
        original = json.loads((self.source / 'manifest.json').read_bytes())
        mutations = [lambda m: m.update(extra='PRIVATE'), lambda m: m.update(format=True),
            lambda m: m.update(source_commit=True), lambda m: m.update(evidence_sha256=True),
            lambda m: m['images'].update(other=m['images']['api']),
            lambda m: m['images']['api'].update(size=True),
            lambda m: m['images']['api'].update(size=10240.0),
            lambda m: m['images']['api'].update(archive='../api.tar'),
            lambda m: m['images']['api'].update(platform='linux/arm64'),
            lambda m: m['images']['web'].update(source_commit='b' * 40),
            lambda m: m['images']['web'].update(extra='PRIVATE')]
        for mutate in mutations:
            value = copy.deepcopy(original)
            mutate(value)
            self.rewrite_manifest(value)
            with self.assertRaises(assembly.AssemblyError): self.assemble()
            self.assertFalse(self.dest.exists())

    def test_duplicate_nonfinite_malformed_and_oversized_metadata_rejected(self):
        for raw in (b'{"format":1,"format":1}', b'{"format":NaN}', b'[]', b'\xff',
                    b' ' * (bundle.MAX_JSON_BYTES + 1)):
            (self.source / 'manifest.json').write_bytes(raw)
            self.digest = hashlib.sha256(raw).hexdigest()
            with self.assertRaises(assembly.AssemblyError): self.assemble()
            self.assertFalse(self.dest.exists())

    def test_strict_archive_gate_runs_before_destination_creation_even_with_matching_hash(self):
        path = self.source / 'api.tar'
        with tarfile.open(path, 'a') as archive:
            member = tarfile.TarInfo('../escape')
            archive.addfile(member, io.BytesIO())
        value = json.loads((self.source / 'manifest.json').read_bytes())
        value['images']['api'].update(size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.rewrite_manifest(value)
        with self.assertRaises(assembly.AssemblyError): self.assemble()
        self.assertFalse(self.dest.exists())

    def test_source_and_destination_checks_each_use_the_real_archive_validator(self):
        calls = []
        original = bundle.preflight.archive_image
        def inspect(path, item, commit):
            calls.append((os.fstat(path.file.fd).st_ino, item['archive']))
            return original(path, item, commit)
        with patch.object(bundle.preflight, 'archive_image', side_effect=inspect): self.assemble()
        for role in ('api', 'web'):
            name = role + '.tar'
            self.assertGreaterEqual(calls.count(((self.source / name).stat().st_ino, name)), 2)
            self.assertGreaterEqual(calls.count(((self.dest / name).stat().st_ino, name)), 1)

    def test_existing_destinations_never_overwritten_or_resumed(self):
        before = self.snapshot()
        for kind in ('directory', 'file', 'symlink', 'dangling', 'fifo'):
            self.dest = self.root / kind
            if kind == 'directory': self.dest.mkdir()
            elif kind == 'file': self.dest.write_bytes(b'KEEP')
            elif kind == 'fifo': os.mkfifo(self.dest)
            else: self.dest.symlink_to(self.source if kind == 'symlink' else self.root / 'missing')
            with self.assertRaises(assembly.AssemblyError): self.assemble()
            self.assertTrue(os.path.lexists(self.dest))
        self.assertEqual((self.root / 'file').read_bytes(), b'KEEP')
        self.assertEqual(self.snapshot(), before)

    def test_paths_cannot_equal_nest_or_use_noncanonical_components(self):
        original = self.source
        for dest in (original, original / 'nested', self.root, 'relative',
                     str(self.root) + '/../escape', str(self.root) + '//new', str(self.root) + '/new/',
                     str(self.root) + '/./new', str(self.root) + '/back\\slash'):
            with self.subTest(dest=dest):
                self.dest = dest
                with self.assertRaises(assembly.AssemblyError): self.assemble()
        for source in ('relative', str(original) + '/', str(self.root) + '/./handoff'):
            self.source = source
            self.dest = self.root / 'fresh'
            with self.assertRaises(assembly.AssemblyError): self.assemble()
            self.assertFalse(self.dest.exists())

    def test_symlink_directory_components_rejected_on_both_sides(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        self.dest = alias / 'fresh'
        with self.assertRaises(assembly.AssemblyError): self.assemble()
        self.dest = self.root / 'fresh'
        self.source = alias / 'handoff'
        with self.assertRaises(assembly.AssemblyError): self.assemble()
        self.assertFalse(self.dest.exists())

    def test_each_source_file_rejects_symlink_hardlink_fifo_directory(self):
        for name in sorted(bundle.FILES | {'COMPLETE'}):
            original, saved = self.source / name, self.root / ('saved-' + name)
            original.rename(saved)
            for kind in ('symlink', 'hardlink', 'fifo', 'directory'):
                with self.subTest(name=name, kind=kind):
                    if kind == 'symlink': original.symlink_to(saved)
                    elif kind == 'hardlink': os.link(saved, original)
                    elif kind == 'fifo': os.mkfifo(original)
                    else: original.mkdir()
                    with self.assertRaises(assembly.AssemblyError): self.assemble()
                    self.assertFalse(self.dest.exists())
                    original.rmdir() if kind == 'directory' else original.unlink()
            saved.rename(original)

    def test_source_identity_cannot_appear_in_destination_ancestors(self):
        original = bundle.Directory.open
        def aliased(path, stack):
            return original(self.source if os.fspath(path) == str(self.root) else path, stack)
        with patch.object(bundle.Directory, 'open', side_effect=aliased):
            with self.assertRaises(assembly.AssemblyError): self.assemble()
        self.assertFalse(self.dest.exists())
        self.assertFalse((self.source / 'operator').exists())

    def test_capacity_includes_output_metadata_and_one_gib_reserve(self):
        manifest_bytes = bundle.canonical(self.fixture.manifest)
        operator = json.loads((ROOT / 'deploy/offline-readonly/operator.example.json').read_bytes())
        required = sum(item['size'] for item in self.fixture.manifest['images'].values())
        required += len(manifest_bytes) + len(bundle.canonical(operator)) + 1024**3
        disk = type('Disk', (), {'f_bavail': required - 1, 'f_frsize': 1})()
        with patch.object(bundle.os, 'fstatvfs', return_value=disk):
            with self.assertRaises(assembly.AssemblyError): self.assemble()
        self.assertFalse(self.dest.exists())
        disk.f_bavail = required
        with patch.object(bundle.os, 'fstatvfs', return_value=disk): self.assemble()

    def test_fixed_total_limit_rejects_before_creation(self):
        self.assertEqual(assembly.MAX_TOTAL_BYTES, 16 * 1024**3)
        self.assertEqual(assembly.RESERVE_BYTES, 1024**3)
        with patch.object(assembly, 'MAX_TOTAL_BYTES', 10):
            with self.assertRaises(assembly.AssemblyError): self.assemble()
        self.assertFalse(self.dest.exists())

    def test_archive_cap_accepts_exact_limit_but_not_one_byte_over(self):
        archive_bytes = sum(item['size'] for item in self.fixture.manifest['images'].values())
        with patch.object(assembly, 'MAX_TOTAL_BYTES', archive_bytes - 1):
            with self.assertRaises(assembly.AssemblyError): self.assemble()
        self.assertFalse(self.dest.exists())
        with patch.object(assembly, 'MAX_TOTAL_BYTES', archive_bytes):
            self.assemble()
        self.assertEqual({p.name for p in self.dest.iterdir()}, OUTPUT_FILES)

    def test_reads_and_writes_bounded_and_short_writes_completed(self):
        read, write = os.read, os.write
        counts = []
        def bounded_read(fd, size):
            self.assertLessEqual(size, bundle.CHUNK)
            return read(fd, size)
        def short_write(fd, data):
            self.assertLessEqual(len(data), bundle.CHUNK)
            counts.append(len(data))
            return write(fd, data[:17])
        with patch.object(os, 'read', side_effect=bounded_read), patch.object(os, 'write', side_effect=short_write):
            self.assemble()
        self.assertTrue(counts)

    def test_zero_write_and_disk_errors_leave_partial_directory_no_retry_or_cleanup(self):
        for outcome in (0, OSError('PRIVATE_DISK')):
            self.dest = self.root / ('zero' if outcome == 0 else 'disk-error')
            with patch.object(os, 'write', **({'return_value': 0} if outcome == 0 else {'side_effect': outcome})):
                with self.assertRaises(assembly.AssemblyError) as error: self.assemble()
            self.assertNotIn('PRIVATE', str(error.exception))
            self.assertTrue(self.dest.is_dir())
            self.assertFalse((self.dest / 'COMPLETE').exists())
            before = {p.name: p.read_bytes() for p in self.dest.iterdir()}
            with self.assertRaises(assembly.AssemblyError): self.assemble()
            self.assertEqual(before, {p.name: p.read_bytes() for p in self.dest.iterdir()})

    def test_source_changed_during_copy_or_after_copy_is_rejected(self):
        original = bundle.copy_archive
        for moment in ('during', 'after'):
            self.dest = self.root / moment
            path = self.source / 'web.tar'
            raw = path.read_bytes()
            def change(source, target, item):
                if moment == 'during': path.write_bytes(raw + b'X')
                original(source, target, item)
                if moment == 'after': path.write_bytes(raw + b'X')
            with patch.object(bundle, 'copy_archive', side_effect=change):
                with self.assertRaises(assembly.AssemblyError): self.assemble()
            self.assertTrue(self.dest.is_dir())
            path.write_bytes(raw)

    def test_verified_source_file_is_not_reopened_by_name(self):
        original, opened = os.open, []
        def track(path, flags, *args, **kwargs):
            if path in bundle.FILES | {'COMPLETE'} and not flags & os.O_CREAT:
                opened.append(path)
            return original(path, flags, *args, **kwargs)
        with patch.object(os, 'open', side_effect=track): self.assemble()
        self.assertCountEqual(opened, list(bundle.FILES | {'COMPLETE'}))

    def test_source_path_replacement_after_initial_verify_is_detected(self):
        original = bundle.copy_archive
        def replace(source, target, item):
            path = self.source / item['archive']
            saved = self.root / ('old-' + item['archive'])
            path.rename(saved)
            path.write_bytes(saved.read_bytes())
            original(source, target, item)
        with patch.object(bundle, 'copy_archive', side_effect=replace):
            with self.assertRaises(assembly.AssemblyError): self.assemble()
        self.assertFalse((self.dest / 'COMPLETE').exists())

    def test_output_bytes_independently_revalidated_before_success(self):
        original = bundle.copy_archive
        def corrupt(source, target, item):
            original(source, target, item)
            os.lseek(target.fd, 0, os.SEEK_SET)
            os.write(target.fd, b'corrupt!')
            target.written()  # Fresh file stat cannot stand in for content validation.
        with patch.object(bundle, 'copy_archive', side_effect=corrupt):
            with self.assertRaises(assembly.AssemblyError): self.assemble()
        self.assertTrue(self.dest.is_dir())

    def test_written_metadata_must_match_exact_intended_bytes(self):
        original = bundle.write_bytes
        def corrupt(target, raw):
            if target.name == 'operator.json': raw = raw.replace(b'false', b'true ')
            return original(target, raw)
        with patch.object(bundle, 'write_bytes', side_effect=corrupt):
            with self.assertRaises(assembly.AssemblyError): self.assemble()

    def test_hardlink_introduced_during_output_write_cannot_be_accepted(self):
        original = bundle.write_bytes
        before = self.snapshot()
        for name in ('api.tar', 'operator.json'):
            self.dest = self.root / ('linked-' + name.replace('.', '-'))
            linked = []
            def link(target, raw):
                if target.name == name and not linked:
                    os.link(self.dest / name, self.root / ('outside-' + name))
                    linked.append(True)
                return original(target, raw)
            with patch.object(bundle, 'write_bytes', side_effect=link):
                with self.assertRaises(assembly.AssemblyError): self.assemble()
            self.assertEqual(len(linked), 1)
            self.assertEqual((self.dest / name).stat().st_nlink, 2)
            self.assertEqual(self.snapshot(), before)

    def test_output_directory_replacement_does_not_escape_or_clean_up(self):
        original = os.write
        moved, other = self.root / 'moved', self.root / 'other'
        other.mkdir()
        changed = False
        def replace(fd, raw):
            nonlocal changed
            if not changed:
                changed = True
                self.dest.rename(moved)
                self.dest.symlink_to(other, target_is_directory=True)
            return original(fd, raw)
        with patch.object(os, 'write', side_effect=replace):
            with self.assertRaises(assembly.AssemblyError): self.assemble()
        self.assertEqual(list(other.iterdir()), [])
        self.assertTrue(moved.exists())

    def test_close_failures_not_retried_or_reported_success(self):
        original = os.close
        for target in ('api.tar', 'manifest.json', 'operator', 'handoff'):
            self.dest = self.root / ('close-' + target.replace('.', '-'))
            failures = []
            def close(fd):
                name = os.readlink('/proc/self/fd/' + str(fd))
                original(fd)
                expected = str(self.dest) if target == 'operator' else (
                    str(self.source) if target == 'handoff' else str(self.dest / target))
                if name == expected:
                    failures.append(fd)
                    raise OSError('PRIVATE_CLOSE')
            with patch.object(os, 'close', side_effect=close):
                with self.assertRaises(assembly.AssemblyError) as error: self.assemble()
            self.assertEqual(len(failures), 1)
            self.assertNotIn('PRIVATE', str(error.exception))
            self.assertTrue(self.dest.exists())

    def test_fsync_failures_do_not_return_success(self):
        original = os.fsync
        for name in ('api.tar', 'operator.json', 'operator', 'parent'):
            self.dest = self.root / ('fsync-' + name.replace('.', '-'))
            def fail(fd):
                target = os.readlink('/proc/self/fd/' + str(fd))
                expected = str(self.dest) if name == 'operator' else (
                    str(self.root) if name == 'parent' else str(self.dest / name))
                if target == expected: raise OSError('PRIVATE_FSYNC')
                return original(fd)
            with patch.object(os, 'fsync', side_effect=fail):
                with self.assertRaises(assembly.AssemblyError): self.assemble()
            self.assertTrue(self.dest.exists())

    def test_interruptions_preserved_internally_even_if_close_also_fails(self):
        original = os.close
        def bad_close(fd):
            original(fd)
            raise OSError('PRIVATE_CLOSE')
        for failure in (KeyboardInterrupt('PRIVATE_INTERRUPT'), SystemExit('PRIVATE_EXIT')):
            self.dest = self.root / type(failure).__name__
            with patch.object(os, 'write', side_effect=failure), patch.object(os, 'close', side_effect=bad_close):
                with self.assertRaises(type(failure)) as error: self.assemble()
            self.assertNotIn('PRIVATE', str(error.exception))
            self.assertTrue(self.dest.exists())

    def test_late_close_interruptions_preserved_and_not_retried(self):
        original = os.close
        failed = []
        def close(fd):
            name = os.readlink('/proc/self/fd/' + str(fd))
            original(fd)
            if name == str(self.dest / 'operator.json'):
                failed.append(fd)
                raise KeyboardInterrupt('PRIVATE_INTERRUPT')
            if failed: raise OSError('PRIVATE_CLOSE')
        with patch.object(os, 'close', side_effect=close):
            with self.assertRaises(KeyboardInterrupt) as error: self.assemble()
        self.assertNotIn('PRIVATE', str(error.exception))
        self.assertEqual(len(failed), 1)

    def test_nested_validator_stream_close_cannot_hide_control_exceptions(self):
        original = bundle.PinnedArchive.open
        for stage in ('source', 'output', 'final-source'):
            for interruption in (KeyboardInterrupt, SystemExit):
                self.dest = self.root / (stage + '-' + interruption.__name__)
                class InterruptedStream:
                    def __init__(self, stream): self.stream = stream
                    def __getattr__(self, name): return getattr(self.stream, name)
                    def __enter__(self): return self
                    def read(self, *_args): raise interruption('PRIVATE_INTERRUPT')
                    def __exit__(self, *_args):
                        self.stream.close()
                        raise OSError('PRIVATE_CLOSE')
                def wrap(path, mode):
                    stream = original(path, mode)
                    is_source = os.readlink('/proc/self/fd/' + str(path.file.directory.fd)) == str(self.source)
                    applies = ((stage == 'source' and is_source and not self.dest.exists())
                        or (stage == 'output' and not is_source)
                        or (stage == 'final-source' and is_source and self.dest.exists()))
                    return InterruptedStream(stream) if applies else stream
                with self.subTest(stage=stage, interruption=interruption.__name__), \
                     patch.object(bundle.PinnedArchive, 'open', wrap):
                    with self.assertRaises(interruption) as error: self.assemble()
                    self.assertNotIn('PRIVATE', str(error.exception))
                    self.assertEqual(self.dest.exists(), stage != 'source')

    def test_original_body_control_precedes_different_stream_close_control(self):
        original = bundle.PinnedArchive.open
        for body, close in ((KeyboardInterrupt, SystemExit), (SystemExit, KeyboardInterrupt)):
            class InterruptedStream:
                def __init__(self, stream): self.stream = stream
                def __getattr__(self, name): return getattr(self.stream, name)
                def __enter__(self): return self
                def read(self, *_args): raise body('PRIVATE_BODY')
                def __exit__(self, *_args):
                    self.stream.close()
                    raise close('PRIVATE_CLOSE')
            def wrap(path, mode): return InterruptedStream(original(path, mode))
            with self.subTest(body=body.__name__, close=close.__name__), \
                 patch.object(bundle.PinnedArchive, 'open', wrap):
                try:
                    self.assemble()
                except BaseException as error:
                    self.assertIs(type(error), body)
                    self.assertNotIn('PRIVATE', str(error))
                else:
                    self.fail('Assembly must retain the original control exception')
                self.assertFalse(self.dest.exists())

    def test_previously_handled_caller_control_is_not_revived(self):
        self.source = self.root / 'missing-source'
        for prior in (KeyboardInterrupt, SystemExit):
            with self.subTest(prior=prior.__name__):
                try:
                    raise prior('PRIVATE_ALREADY_HANDLED')
                except BaseException:
                    try:
                        self.assemble()
                    except BaseException as error:
                        self.assertIs(type(error), assembly.AssemblyError)
                        self.assertNotIn('PRIVATE', str(error))
                    else:
                        self.fail('Missing source must fail assembly')
                self.assertFalse(self.dest.exists())

    def test_import_default_and_help_are_inert(self):
        with patch.object(os, 'open', side_effect=AssertionError('must not inspect inputs')), \
             patch.object(os, 'mkdir', side_effect=AssertionError('must not create')), \
             patch.object(assembly, 'assemble', side_effect=AssertionError('must not assemble')):
            spec = importlib.util.spec_from_file_location('assembly_inert', ROOT / 'scripts/offline_operator_assembly.py')
            spec.loader.exec_module(importlib.util.module_from_spec(spec))
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(assembly.main([]), 0)
                self.assertEqual(assembly.main(self.cli()[1:]), 0)
                with self.assertRaises(SystemExit) as exit_result: assembly.main(['--help'])
                self.assertEqual(exit_result.exception.code, 0)
        self.assertFalse(self.dest.exists())

    def test_cli_explicit_run_succeeds_and_prints_only_safe_receipt(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = assembly.main(self.cli())
        self.assertEqual(code, 0)
        self.assertEqual(err.getvalue(), '')
        self.assertEqual(json.loads(out.getvalue())['status'], 'OPERATOR_DIRECTORY_ASSEMBLED_NOT_READY')
        self.assertNotIn(str(self.root), out.getvalue())

    def test_cli_missing_arguments_unknown_switches_and_private_errors(self):
        for argv in (['--run'], ['--run', 'assemble', 'PRIVATE_SOURCE'],
                     self.cli(['--future-approval=PRIVATE']), self.cli(['--target=PRIVATE']),
                     self.cli(['--expected-comm=PRIVATE'])):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as result: assembly.main(argv)
            self.assertEqual(result.exception.code, 2)
            self.assertNotIn('PRIVATE', out.getvalue() + err.getvalue())
        for failure, expected in ((OSError('PRIVATE_PATH'), 2),
                                  (KeyboardInterrupt('PRIVATE_INTERRUPT'), 130), (SystemExit('PRIVATE_EXIT'), 2)):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                 patch.object(assembly, 'assemble', side_effect=failure):
                code = assembly.main(self.cli())
            self.assertEqual(code, expected)
            self.assertEqual(out.getvalue(), '')
            self.assertIn('BLOCKED', err.getvalue())
            self.assertNotIn('PRIVATE', err.getvalue())

    def test_cli_receipt_write_flush_and_short_write_failures_are_sanitized(self):
        for phase in ('write', 'flush'):
            for failure, expected in ((OSError('PRIVATE_OUTPUT'), 2),
                    (KeyboardInterrupt('PRIVATE_INTERRUPT'), 130), (SystemExit('PRIVATE_EXIT'), 2)):
                class BrokenOutput(io.StringIO):
                    def write(self, value):
                        if phase == 'write': raise failure
                        return super().write(value)
                    def flush(self):
                        if phase == 'flush': raise failure
                        return super().flush()
                err = io.StringIO()
                with contextlib.redirect_stdout(BrokenOutput()), contextlib.redirect_stderr(err), \
                     patch.object(assembly, 'assemble', return_value={'status': 'TEST_ONLY'}) as run:
                    self.assertEqual(assembly.main(self.cli()), expected)
                run.assert_called_once()
                self.assertNotIn('PRIVATE', err.getvalue())
                self.assertIn('BLOCKED', err.getvalue())
        class ShortOutput(io.StringIO):
            def write(self, value): return super().write(value[:1])
        with contextlib.redirect_stdout(ShortOutput()), contextlib.redirect_stderr(io.StringIO()), \
             patch.object(assembly, 'assemble', return_value={'status': 'TEST_ONLY'}):
            self.assertEqual(assembly.main(self.cli()), 2)

    def test_cli_disabled_output_and_failure_diagnostic_are_best_effort(self):
        class BrokenOutput(io.StringIO):
            def write(self, _value): raise OSError('PRIVATE_STREAM')
        for argv in ([], self.cli()):
            with contextlib.redirect_stdout(BrokenOutput()), contextlib.redirect_stderr(BrokenOutput()), \
                 patch.object(assembly, 'assemble', side_effect=OSError('PRIVATE_SOURCE')):
                self.assertEqual(assembly.main(argv), 2)

    def test_failed_receipt_delivery_keeps_output_and_never_reassembles(self):
        class BrokenOutput(io.StringIO):
            def flush(self): raise OSError('PRIVATE_FLUSH')
        before = self.snapshot()
        with contextlib.redirect_stdout(BrokenOutput()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(assembly.main(self.cli()), 2)
        self.assertEqual({p.name for p in self.dest.iterdir()}, OUTPUT_FILES)
        self.assertEqual(self.snapshot(), before)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(assembly.main(self.cli()), 2)


if __name__ == '__main__':
    unittest.main()
