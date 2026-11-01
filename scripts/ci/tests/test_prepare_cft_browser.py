"""Synthetic ZIP/transfer/native fixtures; never obtain or execute a browser."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import plistlib
import stat
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from browser_guard_fixture import install_io_guard

install_io_guard()
SOURCE = Path(__file__).resolve().parents[1] / 'prepare_cft_browser.py'
spec = importlib.util.spec_from_file_location('prepare_cft_browser', SOURCE)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
PREFIX = '/'.join(guard.BUNDLE_PARTS)


class CandidateContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive = self.root / 'candidate.zip'
        self.stdout = redirect_stdout(io.StringIO())
        self.stdout.__enter__()

    def tearDown(self):
        self.stdout.__exit__(None, None, None)
        self.temp.cleanup()

    def make_archive(self, extra=()):
        members = [(PREFIX + '/Contents/Info.plist', b'fixture', stat.S_IFREG | 0o644)]
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for name, data, mode in members + list(extra):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = mode << 16
                archive.writestr(info, data)
        return self.archive

    def bundle(self, **metadata):
        bundle = self.root.joinpath(*guard.BUNDLE_PARTS)
        binary = bundle / 'Contents/MacOS/Google Chrome for Testing'
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b'synthetic, not executable code')
        binary.chmod(0o755)
        values = {'CFBundleIdentifier': guard.IDENTIFIER,
                  'CFBundleShortVersionString': guard.VERSION}
        values.update(metadata)
        with (bundle / 'Contents/Info.plist').open('wb') as stream:
            plistlib.dump(values, stream)
        return bundle, binary

    def test_exact_url_and_redirect_rejection(self):
        self.assertEqual(guard.official_url(guard.URL), guard.URL)
        for value in [guard.URL + '?x=1', guard.URL.replace('https:', 'http:'),
                      guard.URL.replace(guard.VERSION, '155.0.8059.40'),
                      guard.URL.replace('storage.googleapis.com', 'example.com'),
                      guard.URL.replace('/mac-arm64/', '/mac-x64/'), '']:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                guard.official_url(value)
        with self.assertRaises(RuntimeError):
            guard.NoRedirect().redirect_request(None, None, 302, '', {}, guard.URL)

    def test_download_child_has_total_timeout_and_no_retry(self):
        with patch.object(guard.subprocess, 'run', side_effect=subprocess.TimeoutExpired('child', 120)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                guard.download_once()
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs, {'check': True, 'timeout': 120})
        self.assertEqual(run.call_args.args[0][-1], '--download')
        self.assertNotIn(guard.URL, run.call_args.args[0])

    def response(self, chunks, url=None, status=200):
        response = Mock(status=status)
        response.geturl.return_value = guard.URL if url is None else url
        response.read.side_effect = chunks
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = context
        return opener

    def test_transfer_exclusive_file_and_digest(self):
        opener = self.response([b'ABC', b'DEF', b''])
        with patch.object(guard.urllib.request, 'build_opener', return_value=opener):
            guard.download(self.archive)
            self.assertEqual(self.archive.read_bytes(), b'ABCDEF')
            with self.assertRaises(FileExistsError):
                guard.download(self.archive)
        self.assertIn(hashlib.sha256(b'ABCDEF').hexdigest(), self.stdout._new_target.getvalue())

    def test_transfer_rejects_size_empty_status_and_changed_final_url(self):
        cases = [([b'1234'], None, 200), ([b''], None, 200),
                 ([b'x'], None, 206), ([b'x'], 'https://example.com', 200)]
        for chunks, url, status in cases:
            with self.subTest(chunks=chunks, status=status):
                self.archive.unlink(missing_ok=True)
                with patch.object(guard, 'MAX_DOWNLOAD', 3), patch.object(
                        guard.urllib.request, 'build_opener', return_value=self.response(chunks, url, status)):
                    with self.assertRaises(RuntimeError):
                        guard.download(self.archive)

    def test_archive_validates_data_and_internal_framework_symlink(self):
        base = PREFIX + '/Contents/Frameworks/F.framework/Versions/'
        path = self.make_archive([(base + 'A/F', b'CODE', stat.S_IFREG | 0o755),
                                  (base + 'Current', b'A', stat.S_IFLNK | 0o777)])
        manifest = guard.validate_archive(path)
        self.assertEqual(manifest[tuple((base + 'Current').split('/'))]['target'], 'A')
        self.assertEqual(manifest[tuple((base + 'A/F').split('/'))]['sha256'],
                         hashlib.sha256(b'CODE').hexdigest())

    def test_archive_rejects_unsafe_paths_and_types(self):
        for name, mode in [('/outside', stat.S_IFREG | 0o644),
                           ('chrome-mac-arm64/../outside', stat.S_IFREG | 0o644),
                           ('chrome-mac-arm64//extra', stat.S_IFREG | 0o644),
                           ('chrome-mac-arm64/./extra', stat.S_IFREG | 0o644),
                           ('chrome-mac-arm64/C:extra', stat.S_IFREG | 0o644),
                           ('chrome-mac-arm64/evil\\extra', stat.S_IFREG | 0o644),
                           ('__MACOSX/extra', stat.S_IFREG | 0o644),
                           (PREFIX + '/pipe', stat.S_IFIFO | 0o644),
                           (PREFIX + '/writable', stat.S_IFREG | 0o666),
                           (PREFIX + '/setuid', stat.S_IFREG | 0o4755),
                           (PREFIX + '/directory', stat.S_IFDIR | 0o755)]:
            with self.subTest(name=name, mode=mode), self.assertRaises(RuntimeError):
                guard.validate_archive(self.make_archive([(name, b'x', mode)]))

    def test_archive_rejects_case_unicode_and_implicit_parent_collisions(self):
        for first, second in [('Case', 'case'), ('é', 'e\u0301'), ('UP/one', 'up/two')]:
            with self.subTest(first=first), self.assertRaises(RuntimeError):
                guard.validate_archive(self.make_archive([
                    (PREFIX + '/' + first, b'a', stat.S_IFREG | 0o644),
                    (PREFIX + '/' + second, b'b', stat.S_IFREG | 0o644)]))

    def test_archive_rejects_duplicate_and_file_as_ancestor(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with self.assertRaises(RuntimeError):
                guard.validate_archive(self.make_archive([
                    (PREFIX + '/Contents/Info.plist', b'b', stat.S_IFREG | 0o644)]))
        with self.assertRaises(RuntimeError):
            guard.validate_archive(self.make_archive([
                (PREFIX + '/Contents/Info.plist/child', b'b', stat.S_IFREG | 0o644)]))

    def test_archive_rejects_escaping_dangling_cyclic_and_ancestor_links(self):
        for entries in [
                [(PREFIX + '/link', b'../../outside', stat.S_IFLNK | 0o777)],
                [(PREFIX + '/link', b'/outside', stat.S_IFLNK | 0o777)],
                [(PREFIX + '/link', b'missing', stat.S_IFLNK | 0o777)],
                [(PREFIX + '/link', b'link', stat.S_IFLNK | 0o777)],
                [(PREFIX + '/link', b'Contents', stat.S_IFLNK | 0o777),
                 (PREFIX + '/link/new', b'X', stat.S_IFREG | 0o644)],
                [(PREFIX + '/one', b'two', stat.S_IFLNK | 0o777),
                 (PREFIX + '/two', b'one', stat.S_IFLNK | 0o777)]]:
            with self.subTest(entries=entries), self.assertRaises(RuntimeError):
                guard.validate_archive(self.make_archive(entries))

    def test_archive_rejects_budgets_and_crc_corruption(self):
        self.make_archive()
        for name, value in [('MAX_ENTRIES', 0), ('MAX_EXPANDED', 2), ('MAX_DOWNLOAD', 2)]:
            with patch.object(guard, name, value), self.subTest(limit=name), self.assertRaises(RuntimeError):
                guard.validate_archive(self.archive)
        content = self.archive.read_bytes()
        self.archive.write_bytes(content.replace(b'fixture', b'fixturX', 1))
        with self.assertRaises((RuntimeError, zipfile.BadZipFile)):
            guard.validate_archive(self.archive)

    def test_archive_rejects_oversized_symlink(self):
        with self.assertRaises(RuntimeError):
            guard.validate_archive(self.make_archive([
                (PREFIX + '/link', b'a' * 4097, stat.S_IFLNK | 0o777)]))

    def test_symlink_parent_traversal_follows_alias_before_dotdot(self):
        # alias/../.. traverses from the actual nested directory, not from
        # the lexical location of the alias name.
        valid = [(PREFIX + '/Contents/Deep/leaf', b'x', stat.S_IFREG | 0o644),
                 (PREFIX + '/Inside', b'x', stat.S_IFREG | 0o644),
                 (PREFIX + '/alias', b'Contents/Deep', stat.S_IFLNK | 0o777),
                 (PREFIX + '/relative', b'alias/../../Inside', stat.S_IFLNK | 0o777)]
        guard.validate_archive(self.make_archive(valid))
        escaping = [(PREFIX + '/Contents/alias', b'..', stat.S_IFLNK | 0o777),
                    (PREFIX + '/Contents/outside', b'x', stat.S_IFREG | 0o644),
                    (guard.ARCHIVE_ROOT + '/outside', b'x', stat.S_IFREG | 0o644),
                    (PREFIX + '/Contents/escape', b'alias/../outside', stat.S_IFLNK | 0o777)]
        with self.assertRaises(RuntimeError):
            guard.validate_archive(self.make_archive(escaping))

    def test_extra_fields_are_bounded_and_cannot_override_paths(self):
        for extra in [b'x', struct.pack('<HH', 0x5455, 9) + b'x',
                      struct.pack('<HH', 0x7075, 5) + b'\x01xxxx',
                      struct.pack('<HH', 0x000d, 5) + b'xxxxx',
                      struct.pack('<HH', 0x7875, 5) + b'\x01\x09xxx']:
            with self.subTest(extra=extra), self.assertRaises(RuntimeError):
                guard.validate_extra(extra)
        timestamp = struct.pack('<HH', 0x5455, 5) + b'\x01' + b'\x00' * 4
        guard.validate_extra(timestamp)
        with self.assertRaises(RuntimeError):
            guard.validate_extra(timestamp + timestamp)

    def test_local_header_path_override_rejected_even_when_central_is_safe(self):
        import zlib
        self.make_archive()
        data = bytearray(self.archive.read_bytes())
        name_size = struct.unpack_from('<H', data, 26)[0]
        filename = bytes(data[30:30 + name_size])
        value = b'\x01' + struct.pack('<L', zlib.crc32(filename)) + b'../../outside'
        extra = struct.pack('<HH', 0x7075, len(value)) + value
        struct.pack_into('<H', data, 28, len(extra))
        data[30 + name_size:30 + name_size] = extra
        end = data.rfind(b'PK\x05\x06')
        old_offset = struct.unpack_from('<L', data, end + 16)[0]
        struct.pack_into('<L', data, end + 16, old_offset + len(extra))
        self.archive.write_bytes(data)
        with self.assertRaisesRegex(RuntimeError, 'Unsupported ZIP extra'):
            guard.validate_archive(self.archive)

    def test_local_header_filename_mismatch_rejected(self):
        self.make_archive()
        data = bytearray(self.archive.read_bytes())
        data[30] = ord('X')
        self.archive.write_bytes(data)
        with self.assertRaisesRegex(RuntimeError, 'filename mismatch'):
            guard.validate_archive(self.archive)

    def test_local_sizes_and_crc_must_match_central(self):
        for offset in (14, 18, 22):
            self.make_archive()
            data = bytearray(self.archive.read_bytes())
            original = struct.unpack_from('<L', data, offset)[0]
            struct.pack_into('<L', data, offset, original + 1)
            self.archive.write_bytes(data)
            with self.subTest(offset=offset), self.assertRaisesRegex(RuntimeError, 'sizes mismatch'):
                guard.validate_archive(self.archive)

    def test_raw_deflate_rejects_hidden_expansion_with_forged_small_size_and_crc(self):
        import zlib
        info = zipfile.ZipInfo(PREFIX + '/Contents/Info.plist')
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr(info, b'A' * 50)
        data = bytearray(self.archive.read_bytes())
        central = data.index(b'PK\x01\x02')
        struct.pack_into('<L', data, 14, zlib.crc32(b'A'))
        struct.pack_into('<L', data, 22, 1)
        struct.pack_into('<L', data, central + 16, zlib.crc32(b'A'))
        struct.pack_into('<L', data, central + 24, 1)
        self.archive.write_bytes(data)
        # ZipExtFile silently exposes only the forged 1-byte prefix.
        with zipfile.ZipFile(self.archive) as archive:
            self.assertEqual(archive.read(info.filename), b'A')
        with self.assertRaisesRegex(RuntimeError, 'Actual ZIP expansion'):
            guard.validate_archive(self.archive)

    def test_valid_deflate_descriptor_and_zip64_are_supported(self):
        class NonSeekable(io.BytesIO):
            def seek(self, *args):
                raise io.UnsupportedOperation('synthetic stream')
        for descriptor in (False, True):
            for zip64 in (False, True):
                with self.subTest(descriptor=descriptor, zip64=zip64):
                    payload = b'A' * (2 * 1024 * 1024) + b'END'
                    stream = NonSeekable() if descriptor else io.BytesIO()
                    info = zipfile.ZipInfo(PREFIX + '/Contents/Info.plist')
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | 0o644) << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    with zipfile.ZipFile(stream, 'w') as archive:
                        with archive.open(info, 'w', force_zip64=zip64) as member:
                            member.write(payload)
                    self.archive.write_bytes(stream.getvalue())
                    manifest = guard.validate_archive(self.archive)
                    self.assertEqual(manifest[tuple(info.filename.split('/'))]['sha256'],
                                     hashlib.sha256(payload).hexdigest())

    def test_descriptor_sizes_must_match_central(self):
        class NonSeekable(io.BytesIO):
            def seek(self, *args):
                raise io.UnsupportedOperation('synthetic stream')
        stream = NonSeekable()
        info = zipfile.ZipInfo(PREFIX + '/Contents/Info.plist')
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr(info, b'fixture')
        data = bytearray(stream.getvalue())
        descriptor = data.index(b'PK\x07\x08')
        struct.pack_into('<L', data, descriptor + 12, 999)
        self.archive.write_bytes(data)
        with self.assertRaisesRegex(RuntimeError, 'descriptor/central sizes mismatch'):
            guard.validate_archive(self.archive)

    def test_archive_layout_rejects_unindexed_records_trailers_and_spanning(self):
        self.make_archive()
        original = self.archive.read_bytes()
        # A reader using local-header order must not see content absent from
        # the central directory that our validator inspected.
        central = original.index(b'PK\x01\x02')
        hidden_local = original[:central]
        for injected in (b'JUNK', hidden_local):
            data = bytearray(original[:central] + injected + original[central:])
            end = data.rfind(b'PK\x05\x06')
            struct.pack_into('<L', data, end + 16, central + len(injected))
            self.archive.write_bytes(data)
            with self.subTest(injected=len(injected)), self.assertRaisesRegex(RuntimeError, 'unindexed'):
                guard.validate_archive(self.archive)
        self.archive.write_bytes(original + b'trailing payload')
        with self.assertRaisesRegex(RuntimeError, 'directory layout'):
            guard.validate_archive(self.archive)
        data = bytearray(original)
        end = data.rfind(b'PK\x05\x06')
        struct.pack_into('<H', data, end + 4, 1)
        self.archive.write_bytes(data)
        with self.assertRaisesRegex(RuntimeError, 'Spanning'):
            guard.validate_archive(self.archive)

    def test_extraction_requires_all_original_bytes_and_no_extra_members(self):
        manifest = guard.validate_archive(self.make_archive())
        path = self.root / PREFIX / 'Contents/Info.plist'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'fixture')
        guard.verify_extraction(self.root, manifest)
        path.write_bytes(b'changed')
        with self.assertRaises(RuntimeError):
            guard.verify_extraction(self.root, manifest)
        path.write_bytes(b'fixture')
        extra = path.parent / 'injected'
        extra.write_bytes(b'x')
        with self.assertRaises(RuntimeError):
            guard.verify_extraction(self.root, manifest)
        extra.unlink()
        path.unlink()
        with self.assertRaises(RuntimeError):
            guard.verify_extraction(self.root, manifest)

    def test_strict_failure_never_executes_candidate(self):
        bundle, binary = self.bundle()
        failure = subprocess.CalledProcessError(1, 'codesign', output='strict rejection')
        with patch.object(guard, 'output', side_effect=failure) as output:
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                guard.verify_bundle(bundle)
        self.assertIs(caught.exception, failure)
        output.assert_called_once_with('/usr/bin/codesign', '--verify', '--deep', '--strict',
                                      '--verbose=2', '-R', '=' + guard.REQUIREMENT, str(bundle))

    def test_guard_version_identity_or_config_failure_never_executes_candidate(self):
        for key, value in [('CFBundleIdentifier', 'com.google.Chrome'),
                           ('CFBundleShortVersionString', '155.0.8059.40'),
                           ('config', '/wrong/browser')]:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                original = self.root
                self.root = Path(directory)
                bundle, binary = self.bundle(**({key: value} if key != 'config' else {}))
                self.root = original
                with patch.object(guard, 'output', side_effect=['', '', value]) as output:
                    with self.assertRaises(RuntimeError):
                        guard.verify_bundle(bundle)
                self.assertFalse(any(call.args[0] == str(binary) for call in output.call_args_list))

    def test_success_order_and_exact_candidate_version(self):
        bundle, binary = self.bundle()
        with patch.object(guard, 'output', side_effect=['strict', 'display', str(binary),
                                                      'Google Chrome for Testing ' + guard.VERSION]) as output:
            guard.verify_bundle(bundle)
        self.assertEqual([call.args[0] for call in output.call_args_list],
                         ['/usr/bin/codesign', '/usr/bin/codesign', 'node', str(binary)])
        self.assertEqual(output.call_args.args, (str(binary), '--version'))
        with patch.object(guard, 'output', side_effect=['', '', str(binary), 'Google Chrome for Testing WRONG']):
            with self.assertRaises(RuntimeError):
                guard.verify_bundle(bundle)

    def test_permissions_and_escaping_link_fail_before_signature_or_launch(self):
        bundle, binary = self.bundle()
        with patch.object(guard, 'output') as output:
            binary.chmod(0o777)
            with self.assertRaises(RuntimeError):
                guard.verify_bundle(bundle)
            binary.chmod(0o755)
            (bundle / 'escape').symlink_to(self.root)
            with self.assertRaises(RuntimeError):
                guard.verify_bundle(bundle)
            output.assert_not_called()

    def test_prepare_stops_before_extraction_or_launch_on_archive_failure(self):
        with patch.dict(os.environ, {'RUNNER_TEMP': str(self.root)}), patch.object(
                guard, 'download_once') as download, patch.object(
                guard, 'validate_archive', side_effect=RuntimeError('bad ZIP')), patch.object(
                guard.subprocess, 'run') as run, patch.object(guard, 'verify_bundle') as verify:
            with self.assertRaises(RuntimeError):
                guard.prepare()
            download.assert_called_once()
            run.assert_not_called()
            verify.assert_not_called()
            with self.assertRaises(FileExistsError):
                guard.prepare()
            download.assert_called_once()

    def test_prepare_order_preserves_metadata_and_verifies_after_extract(self):
        events = []
        with patch.dict(os.environ, {'RUNNER_TEMP': str(self.root)}), patch.object(
                guard, 'download_once', side_effect=lambda: events.append('download')), patch.object(
                guard, 'validate_archive', side_effect=lambda p: events.append('archive') or {}), patch.object(
                guard.subprocess, 'run', side_effect=lambda *a, **k: events.append('ditto')) as run, patch.object(
                guard, 'verify_extraction', side_effect=lambda *a: events.append('bytes')), patch.object(
                guard, 'verify_bundle', side_effect=lambda *a: events.append('strict')):
            guard.prepare()
        self.assertEqual(events, ['download', 'archive', 'ditto', 'bytes', 'strict'])
        self.assertEqual(run.call_args.args[0][:5], ('/usr/bin/ditto', '-x', '-k', '--rsrc', '--extattr'))
        self.assertEqual(run.call_args.kwargs, {'check': True, 'timeout': 180})

    def test_platform_argument_and_optimized_execution_rejected_without_io(self):
        with patch.object(guard.platform, 'system', return_value='Linux'), patch.object(guard, 'prepare') as prepare:
            with self.assertRaises(RuntimeError):
                guard.main([])
            prepare.assert_not_called()
        with patch.object(guard.platform, 'system', return_value='Darwin'), patch.object(
                guard.platform, 'machine', return_value='arm64'), patch.object(guard, 'prepare') as prepare:
            with self.assertRaises(RuntimeError):
                guard.main(['--url', 'https://example.com'])
            prepare.assert_not_called()
        namespace = {'__name__': 'optimized_guard', '__file__': str(SOURCE)}
        exec(compile(SOURCE.read_text(), str(SOURCE), 'exec', optimize=2), namespace)
        with self.assertRaisesRegex(RuntimeError, 'without -O'):
            namespace['main']([])


if __name__ == '__main__':
    unittest.main()
