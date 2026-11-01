"""Seventeen summary contracts; native commands are replaced by controlled results."""
import ast, contextlib, hashlib, io, json, os, pathlib, plistlib, stat, subprocess, tempfile, types, unittest
from browser_guard_fixture import guard_code, install_io_guard
install_io_guard()

def load():
    code = guard_code()
    tree = ast.parse(code)
    ns = {'os': types.SimpleNamespace(), 'stat': stat, 'hashlib': hashlib, 'json': json, 'plistlib': plistlib, 'pathlib': pathlib, 'subprocess': subprocess, 're': __import__('re')}
    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            exec(compile(ast.Module(body=[n], type_ignores=[]), 'actual', 'exec'), ns)
    ns['components'] = ('.',)
    return ns

class Diagnostics(unittest.TestCase):

    def exercise(self, mode='ok', bad_plist=False, escape=False, resource_escape=False, missing_resources=False, after_strict=False):
        ns = load()
        calls = []
        with tempfile.TemporaryDirectory() as d:
            outside = pathlib.Path(d) / 'outside'
            outside.write_bytes(b'PRIVATE_OUTSIDE_FIXTURE')
            source = pathlib.Path(d) / 'Google Chrome.app'
            (source / 'Contents/_CodeSignature').mkdir(parents=True)
            (source / 'Contents/Info.plist').write_bytes(b'bad' if bad_plist else plistlib.dumps({'CFBundleIdentifier': 'com.google.Chrome', 'CFBundleShortVersionString': '1', 'Private': 'PRIVATE_PLIST_VALUE'}))
            (source / 'Contents/_CodeSignature/CodeResources').write_bytes(b'fixture')
            if resource_escape:
                (source / 'Contents/Info.plist').unlink()
                (source / 'Contents/Info.plist').symlink_to(outside)
            if missing_resources:
                (source / 'Contents/Info.plist').unlink()
                (source / 'Contents/_CodeSignature/CodeResources').unlink()
            if escape:
                (source / 'escape').symlink_to(pathlib.Path(d))
                ns['components'] = ('escape',)

            def run(args, **kwargs):
                calls.append(args)
                self.assertFalse(kwargs.get('shell', False))
                if args[0] == '/usr/bin/xattr':
                    if mode == 'timeout':
                        raise subprocess.TimeoutExpired(args, 20, output=b'PRIVATE_TIMEOUT_VALUE', stderr=b'PRIVATE_TIMEOUT_ERROR')
                    if mode == 'missing':
                        raise FileNotFoundError(2, 'No such file or directory', '/usr/bin/xattr')
                    if mode == 'nonzero':
                        return types.SimpleNamespace(returncode=1, stdout=b'PRIVATE_FAILURE_STDOUT', stderr=b'xattr: permission denied')
                    if len(args) == 2:
                        out = {'empty': b'', 'unsafe': b'-w\ncom.apple.FinderInfo\n', 'ok': b'com.apple.FinderInfo\n', 'readfail': b'com.apple.FinderInfo\ncom.apple.other\n', 'malformed': b'com.apple.FinderInfo\n'}.get(mode, b'com.apple.FinderInfo\n')
                        return types.SimpleNamespace(returncode=0, stdout=out, stderr=b'')
                    self.assertEqual(args[1:3], ('-p', '-x'))
                    if mode == 'readfail' and args[3] == 'com.apple.FinderInfo':
                        return types.SimpleNamespace(returncode=1, stdout=b'PRIVATE_FAILURE_STDOUT', stderr=b'xattr: no such xattr')
                    out = b'not hex PRIVATE_VALUE' if mode == 'malformed' else b'' if mode == 'emptyvalue' else b'00 01 02 03\n'
                    return types.SimpleNamespace(returncode=0, stdout=out, stderr=b'')
                self.assertEqual(args[:3], ('/usr/bin/codesign', '--display', '--verbose=4'))
                if mode == 'displayfail':
                    return types.SimpleNamespace(returncode=1, stdout=b'PRIVATE_STDOUT', stderr=b'Permission denied PRIVATE_STDERR')
                return types.SimpleNamespace(returncode=0, stdout=b'', stderr=b'Identifier=com.google.Chrome\nTeamIdentifier=EQHXZ8M8AV\nUNEXPECTED_PRIVATE_FIELD\n')
            ns['subprocess'] = types.SimpleNamespace(run=run, PIPE=-1, STDOUT=-2, TimeoutExpired=subprocess.TimeoutExpired, CalledProcessError=subprocess.CalledProcessError)
            if mode == 'hashfail':

                def bad_hash(path):
                    raise PermissionError(13, 'Permission denied')
                ns['file_digest'] = bad_hash
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                if after_strict:
                    original = subprocess.CalledProcessError(7, ['codesign'], output='original failure')
                    try:
                        try:
                            raise original
                        finally:
                            ns['diagnostics'](source, 'after strict')
                    except subprocess.CalledProcessError as caught:
                        self.assertIs(caught, original)
                    else:
                        self.fail('strict failure swallowed')
                else:
                    ns['diagnostics'](source, 'test')
            return (buf.getvalue(), calls)

    def test_platform_without_python_xattr(self):
        log, calls = self.exercise()
        self.assertTrue(any((c[0] == '/usr/bin/xattr' for c in calls)))
        self.assertIn('Plist:', log)
        self.assertIn('Signature display:', log)
        self.assertIn('length: 4', log)

    def test_missing_command_independent(self):
        log, calls = self.exercise('missing')
        self.assertIn('Plist:', log)
        self.assertIn('CodeResources', log)
        self.assertIn('Signature display:', log)
        self.assertIn('No such file', log)

    def test_nonzero_original_stderr_not_stdout(self):
        log, _ = self.exercise('nonzero')
        self.assertIn('permission denied', log)
        self.assertNotIn('PRIVATE_FAILURE_STDOUT', log)
        self.assertIn('Plist:', log)
        self.assertIn('Signature display:', log)

    def test_empty_attrs(self):
        log, _ = self.exercise('empty')
        self.assertIn('count: 0', log)
        self.assertIn('Signature display:', log)

    def test_per_attribute_failure(self):
        log, _ = self.exercise('readfail')
        self.assertIn('no such xattr', log)
        self.assertIn('com.apple.other', log)
        self.assertIn('length: 4', log)

    def test_plist_failure_independent(self):
        log, _ = self.exercise(bad_plist=True)
        self.assertIn('CodeResources', log)
        self.assertIn('Signature display:', log)

    def test_no_values(self):
        log, _ = self.exercise()
        self.assertNotIn('PRIVATE_PLIST_VALUE', log)
        self.assertNotIn('UNEXPECTED_PRIVATE_FIELD', log)
        self.assertNotIn('00 01 02 03', log)

    def test_invalid_hex_hidden(self):
        log, _ = self.exercise('malformed')
        self.assertNotIn('PRIVATE_VALUE', log)
        self.assertIn('Signature display:', log)

    def test_no_option_injection(self):
        log, calls = self.exercise('unsafe')
        self.assertFalse(any(('-w' in c for c in calls)))
        self.assertIn('Signature display:', log)

    def test_timeout_does_not_leak(self):
        log, _ = self.exercise('timeout')
        self.assertIn('TimeoutExpired', log)
        self.assertNotIn('PRIVATE_TIMEOUT', log)
        self.assertIn('Plist:', log)
        self.assertIn('Signature display:', log)

    def test_empty_value_summary(self):
        log, _ = self.exercise('emptyvalue')
        self.assertIn('length: 0', log)
        self.assertIn(hashlib.sha256(b'').hexdigest(), log)

    def test_display_error_summary(self):
        log, _ = self.exercise('displayfail')
        self.assertIn('Permission denied', log)
        self.assertNotIn('PRIVATE_STDERR', log)
        self.assertNotIn('PRIVATE_STDOUT', log)
        self.assertIn('Plist:', log)

    def test_resource_escape_independent(self):
        log, _ = self.exercise(resource_escape=True)
        self.assertIn('object', log.lower())
        self.assertIn('CodeResources', log)
        self.assertIn('Signature display:', log)
        self.assertNotIn('PRIVATE_OUTSIDE_FIXTURE', log)

    def test_missing_resources_independent(self):
        log, _ = self.exercise(missing_resources=True)
        self.assertIn('Missing:', log)
        self.assertIn('Signature display:', log)

    def test_hash_error_still_display(self):
        log, _ = self.exercise('hashfail')
        self.assertIn('Permission denied', log)
        self.assertIn('Signature display:', log)

    def test_after_diagnostics_preserves_strict(self):
        for mode in ('missing', 'nonzero', 'timeout', 'hashfail'):
            log, _ = self.exercise(mode, after_strict=True)
            self.assertIn('Signature display:', log)

    def test_escape_no_commands(self):
        _, calls = self.exercise(escape=True)
        self.assertEqual(calls, [])
if __name__ == '__main__':
    unittest.main()
