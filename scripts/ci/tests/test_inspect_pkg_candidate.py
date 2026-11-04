"""Static candidate diagnostics: synthetic bytes and mocked native calls only."""
import contextlib
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from browser_guard_fixture import install_io_guard
from test_browser_workflows import block, keys

install_io_guard()
ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'scripts/ci/inspect_pkg_candidate.py'
spec = importlib.util.spec_from_file_location('static_pkg_inspection', SOURCE)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
BYTES = b'Synthetic inert candidate, not a package.'
SIGNATURE = ('Status: signed by a certificate trusted by macOS\nCertificate Chain:\n'
             + '\n'.join(f' {i}. {s}' for i, s in enumerate(guard.CHAIN, 1)))


class StaticCandidate(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.stage = self.root / 'stage'
        self.stage.mkdir(mode=0o700)
        self.package = self.stage / 'googlechrome.pkg'
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()

    def tearDown(self):
        self.quiet.__exit__(None, None, None)
        self.temp.cleanup()

    def bundle(self):
        bundle = self.stage / 'expanded/GoogleChrome.pkg/Payload/Google Chrome.app'
        for relative in ('Contents/MacOS/Google Chrome', 'Contents/_CodeSignature/CodeResources'):
            p = bundle / relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(BYTES)
        self.plist = bundle / 'Contents/Info.plist'
        self.metadata = {'CFBundleIdentifier': 'com.google.Chrome', 'CFBundleShortVersionString': '156.0.8078.99'}
        self.plist.write_bytes(plistlib.dumps(self.metadata))
        return bundle

    def response(self, status=200, url=None, chunks=None):
        r = Mock(status=status)
        r.headers = {'Content-Length': str(len(BYTES))}
        r.geturl.return_value = guard.URL if url is None else url
        r.read.side_effect = [BYTES, b''] if chunks is None else chunks
        op = Mock()
        op.open.return_value.__enter__ = Mock(return_value=r)
        op.open.return_value.__exit__ = Mock(return_value=False)
        return op

    def test_complete_download_reports_observed_digest_not_pin_acceptance(self):
        with patch.object(guard.urllib.request, 'build_opener', return_value=self.response()):
            guard.download(self.package)
        self.assertEqual(guard.digest_file(self.package), {'bytes': len(BYTES), 'sha256': hashlib.sha256(BYTES).hexdigest()})

    def test_redirects_wrong_source_and_non200_fail(self):
        with self.assertRaises(RuntimeError):
            guard.NoRedirect().redirect_request(None, None, 302, '', {}, guard.URL)
        for op in (self.response(status=404), self.response(url='https://other.invalid/a.pkg')):
            with self.subTest(), patch.object(guard.urllib.request, 'build_opener', return_value=op), self.assertRaises(RuntimeError):
                guard.download(self.package)
        self.assertFalse(self.package.exists())

    def test_transfer_limit_and_empty_fail(self):
        with patch.object(guard, 'MAX_BYTES', 1), patch.object(guard.urllib.request, 'build_opener', return_value=self.response()), self.assertRaises(RuntimeError):
            guard.download(self.package)
        self.package.write_bytes(b'')
        with self.assertRaises(RuntimeError):
            guard.digest_file(self.package)

    def test_truncated_body_and_missing_length_fail(self):
        for header in (None, 'invalid', str(len(BYTES) + 1)):
            op = self.response()
            op.open.return_value.__enter__.return_value.headers = {'Content-Length': header}
            with self.subTest(header=header), patch.object(guard.urllib.request, 'build_opener', return_value=op), self.assertRaises(RuntimeError):
                guard.download(self.package)
            if self.package.exists():
                self.package.unlink()

    def test_download_timeout_propagates(self):
        op = self.response()
        op.open.side_effect = TimeoutError('synthetic')
        with patch.object(guard.urllib.request, 'build_opener', return_value=op), self.assertRaises(TimeoutError):
            guard.download(self.package)

    def test_transfer_rehash_mismatch_fails(self):
        with patch.object(guard.urllib.request, 'build_opener', return_value=self.response()), patch.object(guard, 'digest_file', return_value={'bytes': 1, 'sha256': 'wrong'}), self.assertRaises(RuntimeError):
            guard.download(self.package)

    def test_reuse_and_symlink_candidate_fail(self):
        self.package.write_bytes(BYTES)
        with patch.object(guard.urllib.request, 'build_opener', return_value=self.response()), self.assertRaises(FileExistsError):
            guard.download(self.package)
        link = self.stage / 'link.pkg'
        link.symlink_to(self.package)
        with self.assertRaises(RuntimeError):
            guard.digest_file(link)

    def test_unsafe_stage_and_file_fail(self):
        self.stage.chmod(0o755)
        with self.assertRaises(RuntimeError):
            guard.check_stage(self.stage)
        self.package.write_bytes(BYTES)
        self.package.chmod(0o666)
        with self.assertRaises(RuntimeError):
            guard.digest_file(self.package)

    def test_package_signature_requires_trust_and_exact_chain(self):
        with patch.object(guard, 'native', return_value=SIGNATURE):
            guard.verify_package_signature(self.package)
        for bad in (SIGNATURE.replace('trusted by macOS', 'untrusted'), SIGNATURE.replace('Google LLC', 'Other LLC'), SIGNATURE + '\nStatus: signed by a certificate trusted by macOS', SIGNATURE.replace('Certificate Chain:', 'Unknown:')):
            with self.subTest(), patch.object(guard, 'native', return_value=bad), self.assertRaises(RuntimeError):
                guard.verify_package_signature(self.package)

    def test_static_bundle_never_executes_candidate(self):
        bundle = self.bundle()
        with patch.object(guard, 'native', return_value='') as native:
            result = guard.inspect_bundle(bundle)
        self.assertTrue(result['version_not_executed'])
        self.assertEqual(result['signed_plist_version'], '156.0.8078.99')
        self.assertEqual([c.args[:2] for c in native.call_args_list], [('/usr/bin/codesign', '--verify'), ('/usr/bin/codesign', '--display')])
        self.assertIn('--deep', native.call_args_list[0].args)
        self.assertIn('--strict', native.call_args_list[0].args)
        self.assertIn('=' + guard.REQUIREMENT, native.call_args_list[0].args)

    def test_strict_failure_stops_before_metadata_acceptance(self):
        bundle = self.bundle()
        with patch.object(guard, 'native', side_effect=subprocess.CalledProcessError(1, 'codesign')) as native, self.assertRaises(subprocess.CalledProcessError):
            guard.inspect_bundle(bundle)
        self.assertEqual(native.call_count, 1)

    def test_bad_identity_and_version_fail(self):
        bundle = self.bundle()
        for key, value in [('CFBundleIdentifier', 'other'), ('CFBundleShortVersionString', 'unknown')]:
            self.plist.write_bytes(plistlib.dumps({**self.metadata, key: value}))
            with self.subTest(), patch.object(guard, 'native', return_value=''), self.assertRaises(RuntimeError):
                guard.inspect_bundle(bundle)

    def test_oversized_metadata_and_unsafe_members_fail(self):
        bundle = self.bundle()
        self.plist.write_bytes(b'x' * (1024 * 1024 + 1))
        with patch.object(guard, 'native', return_value=''), self.assertRaises(RuntimeError):
            guard.inspect_bundle(bundle)
        self.plist.write_bytes(plistlib.dumps(self.metadata))
        self.plist.chmod(0o666)
        with patch.object(guard, 'native') as native, self.assertRaises(RuntimeError):
            guard.inspect_bundle(bundle)
        native.assert_not_called()

    def test_indirect_required_member_fails(self):
        bundle = self.bundle()
        alternate = bundle / 'other.plist'
        self.plist.rename(alternate)
        self.plist.symlink_to(alternate)
        with patch.object(guard, 'native') as native, self.assertRaises(RuntimeError):
            guard.inspect_bundle(bundle)
        native.assert_not_called()

    def test_reordered_and_additional_chain_fail(self):
        for bad in (SIGNATURE + '\n 4. Extra CA', SIGNATURE.replace(' 1.', ' 3.').replace(' 2.', ' 1.')):
            with patch.object(guard, 'native', return_value=bad), self.assertRaises(RuntimeError):
                guard.verify_package_signature(self.package)

    def test_whole_expansion_budget_includes_non_bundle_payload(self):
        expanded = self.stage / 'expanded'
        expanded.mkdir()
        (expanded / 'unrelated-payload').write_bytes(BYTES)
        with patch.object(guard, 'MAX_EXPANDED_BYTES', 1), self.assertRaises(RuntimeError):
            guard.expansion_budget(expanded)
        with patch.object(guard, 'MAX_MEMBERS', 1), self.assertRaises(RuntimeError):
            guard.expansion_budget(expanded)
        with patch.object(guard.shutil, 'disk_usage', return_value=Mock(free=0)), self.assertRaises(RuntimeError):
            guard.expansion_budget(expanded)

    def test_expansion_failure_and_budget_kill_wait(self):
        process = Mock(returncode=1)
        process.poll.return_value = 1
        with patch.object(guard.subprocess, 'Popen', return_value=process), patch.object(guard, 'expansion_budget'), self.assertRaises(RuntimeError):
            guard.expand_static(self.package, self.stage / 'expanded')
        process.wait.assert_called_once_with(timeout=10)
        process = Mock()
        process.poll.return_value = None
        with patch.object(guard.subprocess, 'Popen', return_value=process), patch.object(guard, 'expansion_budget', side_effect=[None, RuntimeError('budget')]), self.assertRaises(RuntimeError):
            guard.expand_static(self.package, self.stage / 'expanded')
        process.kill.assert_called_once()
        process.wait.assert_called_once_with(timeout=10)

    def test_expansion_timeout_kills_and_waits(self):
        process = Mock()
        process.poll.return_value = None
        with patch.object(guard.subprocess, 'Popen', return_value=process), patch.object(guard, 'expansion_budget'), patch.object(guard.time, 'monotonic', side_effect=[0, 181]), self.assertRaises(RuntimeError):
            guard.expand_static(self.package, self.stage / 'expanded')
        process.kill.assert_called_once()
        process.wait.assert_called_once_with(timeout=10)

    def test_mocked_full_order_and_post_expansion_mutation(self):
        for mutate in (False, True):
            events = []
            fresh = self.root / ('changed' if mutate else 'unchanged')
            hashes = [{'sha256': 'a'}, {'sha256': 'a'}, {'sha256': 'b' if mutate else 'a'}]
            def hash_file(_):
                events.append('hash')
                return hashes.pop(0)
            with patch.object(guard, 'paths', return_value=(fresh, fresh / 'googlechrome.pkg')), patch.object(guard.subprocess, 'run', side_effect=lambda *a, **k: events.append('download')), patch.object(guard, 'digest_file', side_effect=hash_file), patch.object(guard, 'verify_package_signature', side_effect=lambda p: events.append('trust')), patch.object(guard, 'expand_static', side_effect=lambda *a: events.append('expand')), patch.object(guard, 'check_expanded_tree', side_effect=lambda p: events.append('tree')), patch.object(guard, 'inspect_bundle', side_effect=lambda p: events.append('bundle')):
                if mutate:
                    with self.assertRaises(RuntimeError):
                        guard.inspect()
                else:
                    guard.inspect()
            self.assertEqual(events, ['download', 'hash', 'trust', 'hash', 'expand', 'tree', 'bundle', 'hash'])

    def test_expanded_tree_rejects_unrelated_unsafe_paths(self):
        expanded = self.stage / 'expanded'
        expanded.mkdir()
        path = expanded / 'outside'
        path.symlink_to(self.root)
        with self.assertRaises(RuntimeError):
            guard.check_expanded_tree(expanded)
        path.unlink()
        path.write_bytes(BYTES)
        path.chmod(0o666)
        with self.assertRaises(RuntimeError):
            guard.check_expanded_tree(expanded)

    def test_child_download_timeout_prevents_trust(self):
        fresh = self.root / 'fresh'
        with patch.object(guard, 'paths', return_value=(fresh, fresh / 'googlechrome.pkg')), patch.object(guard.subprocess, 'run', side_effect=subprocess.TimeoutExpired('python', 120)), patch.object(guard, 'verify_package_signature') as trust, self.assertRaises(subprocess.TimeoutExpired):
            guard.inspect()
        trust.assert_not_called()

    def test_escaping_symlink_and_member_limit_fail_before_native(self):
        bundle = self.bundle()
        (bundle / 'escape').symlink_to(self.root)
        with patch.object(guard, 'native') as native, self.assertRaises(RuntimeError):
            guard.inspect_bundle(bundle)
        native.assert_not_called()
        (bundle / 'escape').unlink()
        with patch.object(guard, 'MAX_MEMBERS', 1), patch.object(guard, 'native') as native, self.assertRaises(RuntimeError):
            guard.inspect_bundle(bundle)
        native.assert_not_called()

    def test_native_allowlist_rejects_installer_shell_browser_and_version(self):
        for args in [('/usr/sbin/installer', '-pkg', 'x'), ('/bin/sh', 'x'), ('/tmp/Google Chrome', '--version'), ('/usr/bin/codesign', '--sign', '-')]:
            with self.subTest(args=args), patch.object(guard.subprocess, 'run') as run, self.assertRaises(RuntimeError):
                guard.native(*args)
            run.assert_not_called()

    def test_native_error_and_timeout_propagate(self):
        for error in (subprocess.CalledProcessError(1, 'pkgutil'), subprocess.TimeoutExpired('pkgutil', 120)):
            with self.subTest(), patch.object(guard.subprocess, 'run', side_effect=error), self.assertRaises(type(error)):
                guard.native('/usr/sbin/pkgutil', '--check-signature', str(self.package))

    def test_package_trust_failure_prevents_expansion(self):
        fresh = self.root / 'fresh'
        with patch.object(guard, 'paths', return_value=(fresh, fresh / 'googlechrome.pkg')), patch.object(guard.subprocess, 'run') as child, patch.object(guard, 'digest_file', return_value={}), patch.object(guard, 'verify_package_signature', side_effect=RuntimeError('untrusted')), patch.object(guard, 'native') as native, self.assertRaises(RuntimeError):
            guard.inspect()
        native.assert_not_called()
        self.assertEqual(child.call_count, 1)
        self.assertEqual(child.call_args.kwargs['timeout'], 120)
        self.assertEqual(child.call_args.args[0][-1], '--download')

    def test_changed_candidate_prevents_expansion(self):
        fresh = self.root / 'fresh'
        with patch.object(guard, 'paths', return_value=(fresh, fresh / 'googlechrome.pkg')), patch.object(guard.subprocess, 'run'), patch.object(guard, 'digest_file', side_effect=[{'sha256': 'a'}, {'sha256': 'b'}]), patch.object(guard, 'verify_package_signature'), patch.object(guard, 'native') as native, self.assertRaises(RuntimeError):
            guard.inspect()
        native.assert_not_called()

    def test_main_rejects_platform_and_extra_arguments(self):
        with patch.object(guard.platform, 'system', return_value='Linux'), self.assertRaises(RuntimeError):
            guard.main([])
        with patch.object(guard.platform, 'system', return_value='Darwin'), patch.object(guard.platform, 'machine', return_value='arm64'), self.assertRaises(RuntimeError):
            guard.main(['--execute'])

    def test_workflow_cannot_count_as_acceptance(self):
        from test_validate_pkg_inspection_event import check_workflow
        check_workflow((ROOT / '.github/workflows/browser-pkg-inspection.yml').read_text())
        ci = (ROOT / '.github/workflows/ci.yml').read_text()
        self.assertNotIn('inspect_pkg_candidate', ci)
        self.assertNotIn('browser-pkg-inspection', ci)
        self.assertNotIn('prepare_pkg_browser', SOURCE.read_text())


if __name__ == '__main__':
    unittest.main()
