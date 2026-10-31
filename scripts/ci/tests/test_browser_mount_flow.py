"""Mount observations and 32 terminal-flow combinations; no real mount/command."""
import ast, pathlib, types, os, tempfile
import unittest
from browser_guard_fixture import guard_code, install_io_guard
install_io_guard()
code = guard_code()
tree = ast.parse(code)
import subprocess, plistlib, contextlib, io
start = next((i for i, x in enumerate(tree.body) if isinstance(x, ast.Try) and 'disk' in ast.unparse(x)))
flow = compile(ast.Module(body=tree.body[start:], type_ignores=[]), 'actual-flow', 'exec')

class MountContract(unittest.TestCase):

    def test_mount_and_shadow_observations(self):
        ns = {'os': os, 'stat': __import__('stat')}
        for x in tree.body:
            if isinstance(x, ast.FunctionDef) and x.name in ('mount_state', 'shadow_state'):
                exec(compile(ast.Module(body=[x], type_ignores=[]), 'actual', 'exec'), ns)
        assert 'mount_state' in ns, 'missing real statvfs observation'
        mount = pathlib.Path(tempfile.gettempdir()).resolve()
        for flag, expected in [(1, 'readonly'), (3, 'readonly'), (-1, 'unknown'), (0, 'not_readonly'), (2, 'not_readonly'), (True, 'unknown'), (None, 'unknown')]:
            ns['os'] = types.SimpleNamespace(path=types.SimpleNamespace(ismount=lambda p: True), ST_RDONLY=1, statvfs=lambda p: types.SimpleNamespace(f_flag=flag))
            assert ns['mount_state'](mount) == expected
        ns['os'] = types.SimpleNamespace(path=types.SimpleNamespace(ismount=lambda p: True), statvfs=lambda p: types.SimpleNamespace(f_flag=1))
        assert ns['mount_state'](mount) == 'unknown'

        def error(p):
            raise OSError('fixture')
        ns['os'] = types.SimpleNamespace(path=types.SimpleNamespace(ismount=lambda p: True), ST_RDONLY=1, statvfs=error)
        assert ns['mount_state'](mount) == 'unknown'
        ns['os'] = types.SimpleNamespace(path=types.SimpleNamespace(ismount=lambda p: False), ST_RDONLY=1, statvfs=error)
        try:
            ns['mount_state'](mount)
        except AssertionError:
            pass
        else:
            raise AssertionError('non-mount accepted')
        for image, expected in [({}, 'unknown'), ({'shadow-path': None}, 'unknown'), ({'shadow': False}, 'unknown'), ({'shadow-path': ''}, 'unknown'), ({'shadow-path': '/fixture/shadow'}, 'present'), ({'shadow': True}, 'present')]:
            assert ns['shadow_state'](image) == expected
        for constant in (0, True, -1, None):
            ns['os'] = types.SimpleNamespace(path=types.SimpleNamespace(ismount=lambda p: True), ST_RDONLY=constant, statvfs=lambda p: types.SimpleNamespace(f_flag=1))
            assert ns['mount_state'](mount) == 'unknown'
        for disk in ({'FilesystemType': 'hfs', 'FilesystemName': 'HFS+', 'MountPoint': '/fixture/mount'}, {'ReadOnlyMedia': None, 'ReadOnlyVolume': None}):
            assert disk.get('ReadOnlyVolume') is None
        assert "assert disk.get('ReadOnlyVolume')" not in code

    def test_actual_terminal_flow_matrix(self):
        ns = {'shadow_state': None}
        exec(compile(ast.Module(body=[next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'shadow_state'))], type_ignores=[]), 'shadow', 'exec'), ns)
        count = 0
        for disk in ({'FilesystemType': 'hfs', 'FilesystemName': 'HFS+', 'MountPoint': '/tmp'}, {'ReadOnlyVolume': None, 'ReadOnlyMedia': None}):
            for observation in ('readonly', 'not_readonly', 'unknown', 'nonmount'):
                for strict_fails in (True, False):
                    for detach_fails in (False, True):
                        phases = []
                        calls = []
                        original_error = subprocess.CalledProcessError(7, ['codesign'], output='original')

                        def mount_observe(_):
                            if observation == 'nonmount':
                                raise AssertionError('nonmount')
                            return observation

                        def verify(_):
                            calls.append('verify')
                            if strict_fails:
                                raise original_error

                        def loads(data):
                            return disk if data == b'disk' else {'images': [{'image-path': '/fixture.dmg'}]}

                        def check(args):
                            return b'disk' if args[0].endswith('diskutil') else b'image'

                        def run(*args, **kwargs):
                            calls.append('detach')
                            if detach_fails:
                                raise OSError('detach')
                            return types.SimpleNamespace(returncode=0, stdout='ejected')
                        scope = {'mount': pathlib.Path(tempfile.gettempdir()), 'dmg': pathlib.Path('/fixture.dmg'), 'mount_state': mount_observe, 'shadow_state': ns['shadow_state'], 'plistlib': types.SimpleNamespace(loads=loads), 'subprocess': types.SimpleNamespace(check_output=check, run=run, PIPE=-1, STDOUT=-2), 'json': __import__('json'), 'verify_bundle': verify, 'diagnostics': lambda s, phase: phases.append(phase)}
                        try:
                            with contextlib.redirect_stdout(io.StringIO()):
                                exec(flow, scope)
                        except subprocess.CalledProcessError as e:
                            assert observation in ('readonly', 'unknown') and strict_fails and (e is original_error)
                        except AssertionError:
                            assert observation in ('not_readonly', 'nonmount')
                        except RuntimeError as e:
                            assert observation in ('readonly', 'unknown') and (not strict_fails) and ('Diagnostic-only' in str(e))
                        else:
                            raise AssertionError('success forbidden')
                        assert calls[-1] == 'detach'
                        assert phases == ([] if observation in ('not_readonly', 'nonmount') else ['before strict verification', 'after strict verification'])
                        count += 1
        self.assertEqual(count, 32)
if __name__ == '__main__':
    unittest.main()
