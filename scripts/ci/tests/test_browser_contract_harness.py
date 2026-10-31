"""Negative controls prove platform/terminal regressions are not silent passes."""
import ast
import io
import sys
import unittest
from unittest.mock import patch

from browser_guard_fixture import WORKFLOW, guard_code, install_io_guard
import test_browser_diagnostics as diagnostics
import test_browser_mount_flow as mounts

install_io_guard()


class HarnessContract(unittest.TestCase):
    def assert_regression_detected(self, case):
        result = unittest.TestResult()
        case.run(result)
        self.assertFalse(result.wasSuccessful(), 'Negative control unexpectedly passed')
        self.assertEqual(result.testsRun, 1)

    def test_missing_or_duplicate_heredoc_rejected(self):
        text = WORKFLOW.read_text()
        for invalid in ('', text + text, text.replace('\n          PYTHON\n', '\n')):
            with self.subTest(), self.assertRaises(AssertionError):
                guard_code(invalid)

    def test_native_command_and_network_fail_closed(self):
        # Dispatch audit events directly; do not attempt a real command/connection.
        for event in ('subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.exec',
                      'socket.connect', 'socket.getaddrinfo', 'socket.bind'):
            with self.subTest(event=event), self.assertRaises(RuntimeError):
                sys.audit(event, None)

    def test_regression_python_xattr_api_detected(self):
        tree = ast.parse(guard_code())
        old = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                   and n.name == 'attribute_summary')
        old.body = ast.parse('return os.listxattr(target)').body
        with patch.object(diagnostics, 'guard_code', return_value=ast.unparse(tree)):
            self.assert_regression_detected(diagnostics.Diagnostics(
                'test_platform_without_python_xattr'))

    def test_regression_missing_terminal_failure_detected(self):
        tree = ast.parse(guard_code())
        self.assertIsInstance(tree.body[-1], ast.Raise)
        flow = compile(ast.Module(body=tree.body[mounts.start:-1], type_ignores=[]),
                       'negative-control', 'exec')
        with patch.object(mounts, 'flow', flow):
            self.assert_regression_detected(mounts.MountContract(
                'test_actual_terminal_flow_matrix'))

    def test_regression_readonly_assertion_removed_detected(self):
        tree = ast.parse(guard_code())
        outer = tree.body[mounts.start]
        removed = [n for n in outer.body if isinstance(n, ast.Assert)
                   and 'not_readonly' in ast.unparse(n)]
        self.assertEqual(len(removed), 1)
        outer.body.remove(removed[0])
        flow = compile(ast.Module(body=tree.body[mounts.start:], type_ignores=[]),
                       'negative-control', 'exec')
        with patch.object(mounts, 'flow', flow):
            self.assert_regression_detected(mounts.MountContract(
                'test_actual_terminal_flow_matrix'))


if __name__ == '__main__':
    unittest.main()
