"""Pure metadata tests: no downloads, subprocesses, database or candidate execution."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('scope', ROOT / 'scripts/ci/validate_pr210_pkg_inspection.py')
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

    def test_registered_entry_is_dispatch_only_and_source_pinned(self):
        text = (ROOT / '.github/workflows/browser-diagnostics.yml').read_text()
        self.assertNotIn('if: ${{ false }}', text)
        self.assertIn('workflow_dispatch:', text)
        self.assertIn("github.ref == 'refs/heads/diagnostics/pr210-pkg-inspection'", text)
        self.assertIn('/.github/workflows/browser-diagnostics.yml@', scope.WORKFLOW_REF)
        self.assertFalse((ROOT / 'docs/ci/pr210-pkg-inspection.yml.example').exists())
        self.assertIn('ref: ' + scope.SOURCE_HEAD, text)
        self.assertNotIn('pull_request:', text)
        self.assertFalse((ROOT / '.github/workflows/pr210-pkg-inspection.yml').exists())


if __name__ == '__main__': unittest.main()
