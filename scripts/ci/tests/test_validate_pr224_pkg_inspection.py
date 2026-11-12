"""Pure metadata tests: no downloads, subprocesses, database or candidate execution."""
import importlib.util
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('scope', ROOT / 'scripts/ci/validate_pr224_pkg_inspection.py')
scope = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scope)


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.tool = 'a' * 40
        self.event = {'inputs': {'source_head': scope.SOURCE_HEAD, 'tooling_head': self.tool,
                                'approval': scope.APPROVAL}}
        self.env = {'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REPOSITORY': scope.REPOSITORY,
                    'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_SHA': self.tool,
                    'GITHUB_REF': scope.REF, 'GITHUB_WORKFLOW_REF': scope.WORKFLOW_REF}

    def check(self):
        return scope.validate(self.event, self.env, self.tool, scope.SOURCE_HEAD)

    def test_separate_tooling_and_source_heads(self):
        self.assertEqual(self.check()['source_head'], scope.SOURCE_HEAD)
        self.assertFalse(self.check()['acceptance'])

    def test_invalid_metadata_fails_closed(self):
        for key, value in [('GITHUB_EVENT_NAME', 'pull_request'), ('GITHUB_REPOSITORY', 'fork/repo'),
                           ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_SHA', 'b' * 40),
                           ('GITHUB_REF', 'refs/heads/main'), ('GITHUB_WORKFLOW_REF', 'other')]:
            with self.subTest(key=key):
                old = self.env[key]
                self.env[key] = value
                with self.assertRaises(ValueError): self.check()
                self.env[key] = old

    def test_inputs_not_approval_proof(self):
        for key in self.event['inputs']:
            with self.subTest(key=key):
                old = self.event['inputs'][key]
                self.event['inputs'][key] = 'wrong'
                with self.assertRaises(ValueError): self.check()
                self.event['inputs'][key] = old

    def test_wrong_checkout(self):
        for tool, source in [('b' * 40, scope.SOURCE_HEAD), (self.tool, 'b' * 40)]:
            with self.assertRaises(ValueError): scope.validate(self.event, self.env, tool, source)

    def test_bad_shapes(self):
        for event in [None, [], {'inputs': []}, {'inputs': None}]:
            with self.assertRaises(ValueError): scope.validate(event, self.env, self.tool, scope.SOURCE_HEAD)

    def test_safe_stable_failed_check_names(self):
        cases = [
            ('GITHUB_EVENT_NAME', 'event_name'),
            ('GITHUB_REPOSITORY', 'repository'),
            ('GITHUB_RUN_ATTEMPT', 'run_attempt'),
            ('GITHUB_REF', 'ref'),
            ('GITHUB_WORKFLOW_REF', 'workflow_ref'),
            ('GITHUB_SHA', 'tooling_head_match'),
        ]
        for key, name in cases:
            with self.subTest(key=key):
                env = dict(self.env, **{key: 'PRIVATE_PAYLOAD\n::error::injected'})
                with self.assertRaises(ValueError) as error:
                    scope.validate(self.event, env, self.tool, scope.SOURCE_HEAD)
                self.assertEqual(str(error.exception), 'Scope checks failed: ' + name)
        for key, names in [('tooling_head', 'tooling_head_format,tooling_head_match'),
                           ('source_head', 'source_head_match'),
                           ('approval', 'approval')]:
            with self.subTest(key=key):
                event = {'inputs': dict(self.event['inputs'], **{key: 'PRIVATE_PAYLOAD'})}
                with self.assertRaises(ValueError) as error:
                    scope.validate(event, self.env, self.tool, scope.SOURCE_HEAD)
                self.assertEqual(str(error.exception), 'Scope checks failed: ' + names)

    def test_all_failures_in_stable_order_without_payload(self):
        with self.assertRaises(ValueError) as error:
            scope.validate({'inputs': {}}, {}, 'PRIVATE_TOOL', 'PRIVATE_SOURCE')
        self.assertEqual(str(error.exception), 'Scope checks failed: '
                         'event_name,repository,run_attempt,ref,workflow_ref,'
                         'tooling_head_format,tooling_head_match,source_head_match,approval')

    def test_metadata_shape_has_safe_name(self):
        for event in [None, [], {'inputs': ['PRIVATE_PAYLOAD']}, {'inputs': None}]:
            with self.assertRaises(ValueError) as error:
                scope.validate(event, self.env, self.tool, scope.SOURCE_HEAD)
            self.assertEqual(str(error.exception), 'Scope checks failed: metadata_shape')

    def test_registered_entry_is_dispatch_only_and_source_pinned(self):
        text = (ROOT / '.github/workflows/browser-diagnostics.yml').read_text()
        self.assertNotIn('if: ${{ false }}', text)
        self.assertIn('workflow_dispatch:', text)
        self.assertIn("github.ref == 'refs/heads/diagnostics/pr224-pkg-inspection'", text)
        self.assertIn('/.github/workflows/browser-diagnostics.yml@', scope.WORKFLOW_REF)
        self.assertFalse((ROOT / 'docs/ci/pr224-pkg-inspection.yml.example').exists())
        self.assertIn('ref: ' + scope.SOURCE_HEAD, text)
        self.assertNotIn('pull_request:', text)
        self.assertFalse((ROOT / '.github/workflows/pr224-pkg-inspection.yml').exists())

    def test_fixed_workflow_security_contract(self):
        text = (ROOT / '.github/workflows/browser-diagnostics.yml').read_text()
        for required in ('permissions:\n  contents: read\n',
                         'group: pr224-static-package-inspection\n  cancel-in-progress: false',
                         'github.run_attempt == 1', 'runs-on: macos-26',
                         'timeout-minutes: 12', 'ref: ${{ github.sha }}',
                         'set -euo pipefail',
                         "if: ${{ !cancelled() && steps.scope.outcome == 'success' }}",
                         'path: pkg-inspection-evidence/static-observation.txt',
                         'if-no-files-found: error', 'retention-days: 14'):
            self.assertIn(required, text)
        self.assertEqual(text.count('persist-credentials: false'), 2)
        self.assertEqual(text.count('      - '), 5)
        self.assertEqual(text.count('actions/checkout@11d5960a326750d5838078e36cf38b85af677262'), 2)
        self.assertEqual(text.count('actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02'), 1)
        for forbidden in ('secrets', 'environment:', 'env:', 'write', 'continue-on-error',
                          'sudo', 'installer ', '--version', 'prepare_pkg_browser',
                          'npm ', 'npx ', 'curl ', 'wget ', 'pull_request:', 'push:'):
            self.assertNotIn(forbidden, text)
        scope_command = 'python3 -I tooling/scripts/ci/validate_pr224_pkg_inspection.py'
        inspect_command = 'python3 -I source/scripts/ci/inspect_pkg_candidate.py'
        self.assertLess(text.index(scope_command), text.index(inspect_command))

    def test_fixed_inspector_bytes_unchanged(self):
        inspector = ROOT / 'scripts/ci/inspect_pkg_candidate.py'
        self.assertEqual(hashlib.sha256(inspector.read_bytes()).hexdigest(),
                         'a84bc829e9f7ead2d038b51e61ba7d3bce8258278d8e75e01caee4cd331889aa')


if __name__ == '__main__': unittest.main()
