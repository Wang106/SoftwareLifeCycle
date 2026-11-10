"""Pinned PKG guard contracts: synthetic files only, no native/network execution."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import plistlib
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from browser_guard_fixture import install_io_guard

install_io_guard()
SOURCE = Path(__file__).resolve().parents[1] / 'prepare_pkg_browser.py'
spec = importlib.util.spec_from_file_location('prepare_pkg_browser', SOURCE)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
SYNTHETIC = b'Synthetic package bytes; not a PKG or executable.'
SIGNATURE = '''Package "googlechrome.pkg":
   Status: signed by a certificate trusted by macOS
   Signed with a trusted timestamp on: 2026-10-29 12:00:00 +0000
   Certificate Chain:
    1. Developer ID Installer: Google LLC (EQHXZ8M8AV)
       Expires: 2027-02-01 22:12:15 +0000
       SHA256 Fingerprint:
           AA BB CC DD
    2. Developer ID Certification Authority
       Expires: 2027-02-01 22:12:15 +0000
       SHA256 Fingerprint:
           EE FF 00 11
    3. Apple Root CA
       Expires: 2035-02-09 21:40:36 +0000
       SHA256 Fingerprint:
           22 33 44 55
'''


class PackageContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.package = self.root / 'fixture.pkg'
        self.stdout = redirect_stdout(io.StringIO())
        self.stdout.__enter__()

    def tearDown(self):
        self.stdout.__exit__(None, None, None)
        self.temp.cleanup()

    def pin_fixture(self):
        return patch.multiple(guard, PACKAGE_BYTES=len(SYNTHETIC),
                              SHA256=hashlib.sha256(SYNTHETIC).hexdigest())

    def make_bundle(self, bundle=None, **metadata):
        bundle = self.root.joinpath(*guard.BUNDLE_PARTS) if bundle is None else bundle
        binary = bundle / 'Contents/MacOS/Google Chrome'
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b'Synthetic, not executable code')
        binary.chmod(0o755)
        resources = bundle / 'Contents/_CodeSignature/CodeResources'
        resources.parent.mkdir()
        resources.write_bytes(b'Synthetic resource seal')
        values = {'CFBundleIdentifier': guard.IDENTIFIER,
                  'CFBundleShortVersionString': guard.VERSION}
        values.update(metadata)
        with (bundle / 'Contents/Info.plist').open('wb') as stream:
            plistlib.dump(values, stream)
        return bundle, binary

    def native_output(self, binary, configured=None, version=None, strict_error=False):
        def respond(*args):
            if args[0] == '/usr/bin/codesign':
                if '--verify' in args and strict_error:
                    raise subprocess.CalledProcessError(1, args, 'strict signature failure')
                return ''
            if args[0] == 'node':
                return str(binary) if configured is None else configured
            if args == (str(binary), '--version'):
                return 'Google Chrome ' + guard.VERSION if version is None else version
            raise AssertionError('Unexpected native command: ' + repr(args))
        return respond

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

    def test_fixed_source_pin_and_bundle_identity(self):
        self.assertEqual(guard.VERSION, '157.0.8103.51')
        self.assertEqual(guard.SHA256,
                         '34b6cfbde780a236ec5c1c1a9300e231ad81acb454fc569f409513a7a6525bef')
        self.assertEqual(guard.PACKAGE_BYTES, 272444759)
        self.assertEqual(guard.IDENTIFIER, 'com.google.Chrome')
        self.assertEqual(guard.BUNDLE_PARTS,
                         ('expanded', 'GoogleChrome.pkg', 'Payload', 'Google Chrome.app'))
        self.assertEqual(guard.REQUIREMENT,
                         'anchor apple generic and identifier "com.google.Chrome" '
                         'and certificate 1[field.1.2.840.113635.100.6.2.6] exists '
                         'and certificate leaf[field.1.2.840.113635.100.6.1.13] exists '
                         'and certificate leaf[subject.OU] = "EQHXZ8M8AV"')
        self.assertEqual(guard.URL,
                         'https://dl.google.com/chrome/mac/stable/'
                         'accept_tos%3Dhttps%253A%252F%252Fwww.google.com%252Fintl%252Fen_ph%252Fchrome%252Fterms%252F'
                         '%26_and_accept_tos%3Dhttps%253A%252F%252Fpolicies.google.com%252Fterms/googlechrome.pkg')

    def test_import_has_no_download_native_or_filesystem_side_effects(self):
        code = compile(SOURCE.read_text(), str(SOURCE), 'exec')
        with patch.object(guard.subprocess, 'run') as run, patch.object(
                guard.subprocess, 'check_output') as output, patch.object(
                guard.urllib.request, 'build_opener') as opener, patch.object(Path, 'mkdir') as mkdir:
            exec(code, {'__name__': 'pkg_import_fixture'})
        for action in (run, output, opener, mkdir):
            action.assert_not_called()

    def test_optimized_mode_is_explicitly_rejected(self):
        namespace = {'__name__': 'pkg_optimized_fixture'}
        exec(compile(SOURCE.read_text(), str(SOURCE), 'exec', optimize=1), namespace)
        with self.assertRaisesRegex(RuntimeError, 'without -O'):
            namespace['main']([])

    def test_wrong_platform_and_arguments_fail_before_io(self):
        for system, machine, args in [('Linux', 'arm64', []), ('Darwin', 'x86_64', []),
                                      ('Darwin', 'arm64', ['--download', 'https://example.com'])]:
            with self.subTest(system=system, machine=machine, args=args), patch.object(
                    guard.platform, 'system', return_value=system), patch.object(
                    guard.platform, 'machine', return_value=machine), patch.object(guard, 'prepare') as prepare:
                with self.assertRaises(RuntimeError):
                    guard.main(args)
                prepare.assert_not_called()

    def test_paths_require_existing_absolute_runner_temp(self):
        for value in ['', 'relative', str(self.root / 'missing')]:
            with self.subTest(value=value), patch.dict(os.environ, {'RUNNER_TEMP': value}):
                with self.assertRaises((RuntimeError, FileNotFoundError)):
                    guard.paths()
        with patch.dict(os.environ, {'RUNNER_TEMP': str(self.root)}):
            staging, package, bundle = guard.paths()
        self.assertEqual(staging, self.root / 'slc-pkg-chrome')
        self.assertEqual(package, staging / 'googlechrome.pkg')
        self.assertEqual(bundle, staging.joinpath(*guard.BUNDLE_PARTS))

    def test_existing_staging_refused_without_download(self):
        (self.root / 'slc-pkg-chrome').mkdir(mode=0o700)
        with patch.dict(os.environ, {'RUNNER_TEMP': str(self.root)}), patch.object(
                guard, 'download_once') as download:
            with self.assertRaises(FileExistsError):
                guard.prepare()
        download.assert_not_called()

    def test_child_refuses_staging_symlink_wrong_mode_and_owner(self):
        staging = self.root / 'stage'
        staging.mkdir(mode=0o700)
        guard.verify_staging(staging)
        staging.chmod(0o755)
        with self.assertRaisesRegex(RuntimeError, 'staging'):
            guard.verify_staging(staging)
        staging.chmod(0o700)
        with patch.object(guard.os, 'getuid', return_value=staging.stat().st_uid + 1000):
            with self.assertRaisesRegex(RuntimeError, 'staging'):
                guard.verify_staging(staging)
        link = self.root / 'stage-link'
        link.symlink_to(staging)
        with self.assertRaisesRegex(RuntimeError, 'staging'):
            guard.verify_staging(link)

    def test_exact_url_and_all_redirects_refused(self):
        self.assertEqual(guard.official_url(guard.URL), guard.URL)
        for url in [guard.URL + '?x=1', guard.URL + '#x', guard.URL.replace('https:', 'http:'),
                    guard.URL.replace('dl.google.com', 'example.com'), guard.URL.replace('stable', 'beta')]:
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                guard.official_url(url)
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status), self.assertRaisesRegex(RuntimeError, 'redirect'):
                guard.NoRedirect().redirect_request(None, None, status, '', {}, guard.URL)

    def test_download_child_timeout_has_no_retry_or_alternate_arguments(self):
        with patch.object(guard.subprocess, 'run', side_effect=subprocess.TimeoutExpired('child', 120)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                guard.download_once()
        run.assert_called_once_with([guard.sys.executable, '-I', str(SOURCE.resolve()), '--download'],
                                    check=True, timeout=120)

    def test_transfer_pin_and_exclusive_destination(self):
        opener = self.response([SYNTHETIC[:10], SYNTHETIC[10:], b''])
        with self.pin_fixture(), patch.object(guard.urllib.request, 'build_opener', return_value=opener):
            guard.download(self.package)
            self.assertEqual(self.package.read_bytes(), SYNTHETIC)
            with self.assertRaises(FileExistsError):
                guard.download(self.package)
        self.assertIn(hashlib.sha256(SYNTHETIC).hexdigest(), self.stdout._new_target.getvalue())
        self.assertEqual(opener.open.call_args.args, (guard.URL,))
        self.assertEqual(opener.open.call_args.kwargs, {'timeout': 120})

    def test_transfer_rejects_hash_size_status_changed_url_and_limit(self):
        cases = [([b'X' * len(SYNTHETIC), b''], None, 200, guard.MAX_DOWNLOAD),
                 ([b''], None, 200, guard.MAX_DOWNLOAD),
                 ([SYNTHETIC, b''], None, 206, guard.MAX_DOWNLOAD),
                 ([SYNTHETIC, b''], guard.URL + '?redirect', 200, guard.MAX_DOWNLOAD),
                 ([SYNTHETIC], None, 200, len(SYNTHETIC) - 1)]
        for chunks, url, status, cap in cases:
            with self.subTest(chunks=chunks, status=status, cap=cap):
                self.package.unlink(missing_ok=True)
                with self.pin_fixture(), patch.object(guard, 'MAX_DOWNLOAD', cap), patch.object(
                        guard.urllib.request, 'build_opener', return_value=self.response(chunks, url, status)):
                    with self.assertRaises(RuntimeError):
                        guard.download(self.package)

    def test_saved_bytes_rechecked_before_native_trust(self):
        self.package.write_bytes(SYNTHETIC)
        with self.pin_fixture():
            guard.verify_package_bytes(self.package)
            self.package.write_bytes(b'X' * len(SYNTHETIC))
            with self.assertRaisesRegex(RuntimeError, 'SHA256'):
                guard.verify_package_bytes(self.package)
            self.package.write_bytes(SYNTHETIC[:-1])
            with self.assertRaisesRegex(RuntimeError, 'byte count'):
                guard.verify_package_bytes(self.package)

    def test_pin_mismatch_reports_only_bounded_counts_and_digests_then_fails(self):
        expected = hashlib.sha256(SYNTHETIC).hexdigest()
        for data, reason in ((b'', 'byte count'), (SYNTHETIC[:-1], 'byte count'),
                             (b'X' * len(SYNTHETIC), 'SHA256')):
            with self.subTest(reason=reason, size=len(data)):
                self.package.unlink(missing_ok=True)
                stream = io.StringIO()
                opener = self.response([data, b''])
                with self.pin_fixture(), redirect_stdout(stream), patch.object(
                        guard.urllib.request, 'build_opener', return_value=opener):
                    with self.assertRaisesRegex(RuntimeError, 'Pinned PKG ' + reason + ' differs'):
                        guard.download(self.package)
                self.assertEqual(stream.getvalue(),
                                 'Official PKG download: ' + guard.URL + '\n'
                                 'PKG pin mismatch: actual bytes: ' + str(len(data)) +
                                 ' ; expected bytes: ' + str(len(SYNTHETIC)) +
                                 ' ; actual SHA256: ' + hashlib.sha256(data).hexdigest() +
                                 ' ; expected SHA256: ' + expected + '\n')
                opener.open.assert_called_once_with(guard.URL, timeout=120)

    def test_matching_pin_emits_no_failure_diagnostic(self):
        stream = io.StringIO()
        with self.pin_fixture(), redirect_stdout(stream):
            guard.verify_pin(len(SYNTHETIC), hashlib.sha256(SYNTHETIC).hexdigest())
        self.assertEqual(stream.getvalue(), '')

    def test_download_pin_failure_never_reaches_native_trust_or_execution(self):
        for data in (SYNTHETIC[:-1], b'X' * len(SYNTHETIC)):
            with self.subTest(size=len(data)), tempfile.TemporaryDirectory(dir=self.root) as root:
                package = Path(root) / 'slc-pkg-chrome/googlechrome.pkg'
                opener = self.response([data, b''])
                with patch.dict(os.environ, {'RUNNER_TEMP': root}), self.pin_fixture(), patch.object(
                        guard, 'download_once', side_effect=lambda: guard.download(package)), patch.object(
                        guard.urllib.request, 'build_opener', return_value=opener), patch.object(
                        guard, 'verify_package_signature') as signature, patch.object(
                        guard.subprocess, 'run') as expand, patch.object(guard, 'verify_bundle') as bundle:
                    with self.assertRaisesRegex(RuntimeError, 'Pinned PKG'):
                        guard.prepare()
                    signature.assert_not_called()
                    expand.assert_not_called()
                    bundle.assert_not_called()
                    opener.open.assert_called_once_with(guard.URL, timeout=120)

    def test_saved_package_rejects_symlink_and_unsafe_mode(self):
        self.package.write_bytes(SYNTHETIC)
        alias = self.root / 'alias.pkg'
        alias.symlink_to(self.package)
        with self.pin_fixture():
            with self.assertRaisesRegex(RuntimeError, 'Untrusted PKG'):
                guard.verify_package_bytes(alias)
            self.package.chmod(0o666)
            with self.assertRaisesRegex(RuntimeError, 'Untrusted PKG'):
                guard.verify_package_bytes(self.package)

    def test_native_signature_command_is_absolute_bounded_and_locale_stable(self):
        with patch.object(guard.subprocess, 'check_output', return_value=SIGNATURE) as command:
            guard.verify_package_signature(self.package)
        self.assertEqual(command.call_args.args[0], ('/usr/sbin/pkgutil', '--check-signature', str(self.package)))
        self.assertEqual(command.call_args.kwargs['timeout'], 120)
        self.assertEqual(command.call_args.kwargs['env']['LC_ALL'], 'C')
        self.assertEqual(command.call_args.kwargs['env']['LANG'], 'C')

    def test_exact_both_affirmative_native_status_variants(self):
        for status in ('signed by a certificate trusted by macOS',
                       'signed by a developer certificate issued by Apple for distribution'):
            with self.subTest(status=status), patch.object(
                    guard, 'output', return_value=SIGNATURE.replace(guard.TRUSTED_STATUSES[0], status)):
                guard.verify_package_signature(self.package)

    def test_package_signature_rejects_unsigned_untrusted_selfsigned_and_wrong_chain(self):
        reports = [SIGNATURE.replace(guard.TRUSTED_STATUSES[0], 'no signature'),
                   SIGNATURE.replace(guard.TRUSTED_STATUSES[0], 'signed by an untrusted certificate'),
                   SIGNATURE.replace(guard.TRUSTED_STATUSES[0], 'signed by a self-signed certificate'),
                   SIGNATURE.replace(guard.TRUSTED_STATUSES[0], 'signed by a revoked certificate'),
                   SIGNATURE.replace(guard.TRUSTED_STATUSES[0], guard.TRUSTED_STATUSES[0] + ' (untrusted)'),
                   SIGNATURE.replace(guard.TRUSTED_STATUSES[0], guard.TRUSTED_STATUSES[1] + ' (revoked)'),
                   SIGNATURE.replace('EQHXZ8M8AV', 'WRONGTEAM1'),
                   SIGNATURE.replace('Developer ID Installer:', 'Developer ID Application:'),
                   SIGNATURE.replace('Apple Root CA', 'Untrusted Root'),
                   SIGNATURE.replace('Developer ID Certification Authority', 'Other Authority'),
                   SIGNATURE.replace('    2. ', '    4. '),
                   SIGNATURE + '\n    4. Extra Certificate\n',
                   SIGNATURE + '\n Status: no signature\n',
                   SIGNATURE.replace('   Certificate Chain:', '   Unknown Chain:')]
        for report in reports:
            with self.subTest(report=report), patch.object(guard, 'output', return_value=report):
                with self.assertRaises(RuntimeError):
                    guard.verify_package_signature(self.package)

    def test_package_verification_failures_never_expand_or_execute(self):
        for failure in ('hash', 'unsigned', 'wrongteam', 'native-exit'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(dir=self.root) as root:
                package = Path(root) / 'slc-pkg-chrome/googlechrome.pkg'
                data = b'X' * len(SYNTHETIC) if failure == 'hash' else SYNTHETIC
                report = SIGNATURE.replace(guard.TRUSTED_STATUSES[0], 'no signature') if failure == 'unsigned' else (
                    SIGNATURE.replace('EQHXZ8M8AV', 'WRONGTEAM1') if failure == 'wrongteam' else SIGNATURE)
                with patch.dict(os.environ, {'RUNNER_TEMP': root}), self.pin_fixture(), patch.object(
                        guard, 'download_once', side_effect=lambda: package.write_bytes(data)), patch.object(
                        guard, 'output', return_value=report) as output, patch.object(
                        guard.subprocess, 'run') as expand, patch.object(guard, 'verify_bundle') as bundle:
                    if failure == 'native-exit':
                        output.side_effect = subprocess.CalledProcessError(1, 'pkgutil', SIGNATURE)
                    with self.assertRaises((RuntimeError, subprocess.CalledProcessError)):
                        guard.prepare()
                    expand.assert_not_called()
                    bundle.assert_not_called()
                    if failure == 'hash':
                        output.assert_not_called()

    def test_expand_failure_never_reaches_bundle_or_browser(self):
        package = self.root / 'slc-pkg-chrome/googlechrome.pkg'
        with patch.dict(os.environ, {'RUNNER_TEMP': str(self.root)}), self.pin_fixture(), patch.object(
                guard, 'download_once', side_effect=lambda: package.write_bytes(SYNTHETIC)), patch.object(
                guard, 'output', return_value=SIGNATURE), patch.object(
                guard.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'pkgutil')) as expand, patch.object(
                guard, 'verify_bundle') as bundle:
            with self.assertRaises(subprocess.CalledProcessError):
                guard.prepare()
        expand.assert_called_once()
        self.assertEqual(expand.call_args.args[0][0:2], ('/usr/sbin/pkgutil', '--expand-full'))
        bundle.assert_not_called()

    def test_missing_resources_rejected_before_codesign_and_browser(self):
        bundle, _ = self.make_bundle()
        (bundle / 'Contents/_CodeSignature/CodeResources').unlink()
        with patch.object(guard, 'output') as output:
            with self.assertRaisesRegex(RuntimeError, 'CodeResources'):
                guard.verify_bundle(bundle)
        output.assert_not_called()

    def test_bundle_unsafe_mode_or_external_symlink_rejected_before_commands(self):
        bundle, binary = self.make_bundle()
        with patch.object(guard, 'output') as output:
            for mode in (0o777, 0o4755, 0o2755, 0o1755):
                binary.chmod(mode)
                with self.subTest(mode=mode), self.assertRaisesRegex(RuntimeError, 'mode'):
                    guard.verify_bundle(bundle)
            binary.chmod(0o755)
            (bundle / 'escape').symlink_to(self.root)
            with self.assertRaisesRegex(RuntimeError, 'escapes bundle'):
                guard.verify_bundle(bundle)
        output.assert_not_called()

    def test_bundle_rejects_wrong_owner_and_special_member(self):
        bundle, _ = self.make_bundle()
        original_lstat = Path.lstat
        def wrong_owner(path):
            info = original_lstat(path)
            if path == bundle:
                values = list(info)
                values[4] = os.getuid() + 1000
                return os.stat_result(values)
            return info
        with patch.object(Path, 'lstat', wrong_owner), patch.object(guard, 'output') as output:
            with self.assertRaisesRegex(RuntimeError, 'owner'):
                guard.verify_bundle(bundle)
            output.assert_not_called()
        os.mkfifo(bundle / 'special')
        with patch.object(guard, 'output') as output:
            with self.assertRaisesRegex(RuntimeError, 'Special Chrome member'):
                guard.verify_bundle(bundle)
            output.assert_not_called()

    def test_strict_failure_does_not_probe_version_or_config(self):
        bundle, binary = self.make_bundle()
        with patch.object(guard, 'output', side_effect=self.native_output(binary, strict_error=True)) as output:
            with self.assertRaises(subprocess.CalledProcessError):
                guard.verify_bundle(bundle)
        output.assert_called_once_with('/usr/bin/codesign', '--verify', '--deep', '--strict', '--verbose=2',
                                       '-R', '=' + guard.REQUIREMENT, str(bundle))

    def test_wrong_plist_identity_or_version_does_not_execute_browser(self):
        for values in ({'CFBundleIdentifier': 'com.google.chrome.for.testing'},
                       {'CFBundleShortVersionString': '155.0.8059.40'}):
            with self.subTest(values=values), tempfile.TemporaryDirectory(dir=self.root) as root:
                bundle, binary = self.make_bundle(Path(root) / 'Google Chrome.app', **values)
                with patch.object(guard, 'output', side_effect=self.native_output(binary)) as output:
                    with self.assertRaisesRegex(RuntimeError, 'bundle identifier|bundle version'):
                        guard.verify_bundle(bundle)
                self.assertTrue(all(call.args[0] == '/usr/bin/codesign' for call in output.call_args_list))

    def test_wrong_config_path_never_executes_browser(self):
        bundle, binary = self.make_bundle()
        with patch.object(guard, 'output', side_effect=self.native_output(binary, configured='/usr/bin/other')) as output:
            with self.assertRaisesRegex(RuntimeError, 'paths differ'):
                guard.verify_bundle(bundle)
        self.assertEqual([call.args[0] for call in output.call_args_list],
                         ['/usr/bin/codesign', '/usr/bin/codesign', 'node'])

    def test_binary_version_must_match_exact_product_and_pin(self):
        bundle, binary = self.make_bundle()
        for actual in ['Google Chrome 155.0.8059.40', 'Google Chrome for Testing ' + guard.VERSION,
                       'Google Chrome ' + guard.VERSION + ' extra']:
            with self.subTest(actual=actual), patch.object(
                    guard, 'output', side_effect=self.native_output(binary, version=actual)):
                with self.assertRaisesRegex(RuntimeError, 'binary version mismatch'):
                    guard.verify_bundle(bundle)

    def test_success_orders_all_trust_gates_before_only_candidate_execution(self):
        staging = self.root / 'slc-pkg-chrome'
        package = staging / 'googlechrome.pkg'
        bundle = staging.joinpath(*guard.BUNDLE_PARTS)
        binary = bundle / 'Contents/MacOS/Google Chrome'
        events = []
        def download():
            events.append(('download',))
            self.assertEqual(stat.S_IMODE(staging.stat().st_mode), 0o700)
            package.write_bytes(SYNTHETIC)
        def command(*args):
            events.append(args)
            if args == ('/usr/sbin/pkgutil', '--check-signature', str(package)):
                return SIGNATURE
            return self.native_output(binary)(*args)
        def expand(args, **kwargs):
            events.append(args)
            self.assertEqual(kwargs, {'check': True, 'timeout': 180})
            self.make_bundle(bundle)
            framework = bundle / 'Contents/Frameworks/F.framework/Versions'
            (framework / 'A').mkdir(parents=True)
            (framework / 'Current').symlink_to('A')
        with patch.dict(os.environ, {'RUNNER_TEMP': str(self.root)}), self.pin_fixture(), patch.object(
                guard, 'download_once', side_effect=download), patch.object(
                guard, 'output', side_effect=command), patch.object(guard.subprocess, 'run', side_effect=expand):
            guard.prepare()
        self.assertEqual(events, [
            ('download',),
            ('/usr/sbin/pkgutil', '--check-signature', str(package)),
            ('/usr/sbin/pkgutil', '--expand-full', str(package), str(staging / 'expanded')),
            ('/usr/bin/codesign', '--verify', '--deep', '--strict', '--verbose=2',
             '-R', '=' + guard.REQUIREMENT, str(bundle)),
            ('/usr/bin/codesign', '--display', '--verbose=4', str(bundle)),
            ('node', '-e', "process.stdout.write(require('./e2e/playwright.config.cjs').use.launchOptions.executablePath)"),
            (str(binary), '--version')])
        self.assertIn('anchor apple generic', guard.REQUIREMENT)
        self.assertIn('certificate leaf[subject.OU] = "EQHXZ8M8AV"', guard.REQUIREMENT)

    def test_normal_mode_only_observes_existing_security_settings(self):
        events = []
        def status(command, **kwargs):
            events.append(command)
            self.assertEqual(kwargs['timeout'], 20)
            return subprocess.CompletedProcess(command, 1, 'existing state unavailable')
        with patch.object(guard.platform, 'system', return_value='Darwin'), patch.object(
                guard.platform, 'machine', return_value='arm64'), patch.object(
                guard, 'output', return_value='15.7') as output, patch.object(
                guard.subprocess, 'run', side_effect=status), patch.object(guard, 'prepare') as prepare:
            guard.main([])
        self.assertEqual(events, [('/usr/bin/csrutil', 'status'), ('/usr/sbin/spctl', '--status')])
        output.assert_called_once_with('/usr/bin/sw_vers', '-productVersion')
        prepare.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
