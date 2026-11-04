"""Offline event/workflow negatives; no network, native programs or workflow run."""
import copy
import importlib.util
from pathlib import Path
import unittest
from browser_guard_fixture import install_io_guard
from test_browser_workflows import block, keys

install_io_guard()
ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('inspection_event', ROOT / 'scripts/ci/validate_pkg_inspection_event.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
SHA = 'a' * 40

REQUIRED = [
    "types: [synchronize]", "branches: [main]",
    "github.event_name == 'pull_request' &&",
    "github.event.action == 'synchronize' &&",
    "github.repository == 'Wang106/SoftwareLifeCycle' &&",
    'github.event.number == 176 &&',
    'github.event.pull_request.head.repo.full_name == github.repository &&',
    'github.event.pull_request.head.repo.fork == false &&',
    "github.event.pull_request.head.ref == 'docs/b2-evidence-b3-recovery' &&",
    "github.event.pull_request.base.ref == 'main' &&",
    "github.event.before == '" + guard.PARENT + "' &&",
    'github.run_attempt == 1',
    'ref: ${{ github.event.pull_request.head.sha }}', 'fetch-depth: 2',
    'persist-credentials: false', 'runs-on: macos-26', 'timeout-minutes: 12',
    'actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
    'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02',
    'id: scope', 'shell: bash',
    'run: python3 -I scripts/ci/validate_pkg_inspection_event.py',
    'python3 -I scripts/ci/inspect_pkg_candidate.py | tee pkg-inspection-evidence/static-observation.txt',
    "if: ${{ !cancelled() && steps.scope.outcome == 'success' }}",
    'path: pkg-inspection-evidence/static-observation.txt',
    'if-no-files-found: error', 'retention-days: 14',
]


def check_workflow(text):
    assert keys(text, 0) == ['name', 'on', 'permissions', 'concurrency', 'jobs']
    assert keys(block(text, 'on'), 2) == ['pull_request']
    assert keys(block(text, 'permissions'), 2) == ['contents']
    assert block(text, 'permissions').strip() == 'contents: read'
    assert keys(block(text, 'jobs'), 2) == ['inspection']
    for line in REQUIRED:
        assert line in text, line
    for path in guard.FILES:
        assert "      - '" + path + "'" in text
    for forbidden in ['secrets', 'token:', 'env:', 'environment:', 'needs:', 'write',
                      'continue-on-error', 'always()', 'workflow_dispatch',
                      'pull_request_target', 'sudo', 'installer ', '--version',
                      'prepare_pkg_browser', 'npm ', 'npx ', 'curl ', 'wget ']:
        assert forbidden not in text, forbidden
    conditions = [line for line in REQUIRED if line.startswith('github.')]
    actual_conditions = block(text, 'if', 4) if '    if:\n' in text else text.split('    if: >-\n', 1)[1].split('    runs-on:', 1)[0]
    assert actual_conditions.strip().splitlines() == [conditions[0]] + ['      ' + line for line in conditions[1:]]
    runs = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('        run: '):
            if line == '        run: |':
                body = []
                for following in lines[i + 1:]:
                    if not following.startswith('          '):
                        break
                    body.append(following.strip())
                runs.append('\n'.join(body))
            else:
                runs.append(line.removeprefix('        run: '))
    assert runs == ['python3 -I scripts/ci/validate_pkg_inspection_event.py',
                    'mkdir -p pkg-inspection-evidence\npython3 -I scripts/ci/inspect_pkg_candidate.py | tee pkg-inspection-evidence/static-observation.txt']
    step_conditions = [line for line in lines if line.startswith('        if:')]
    assert step_conditions == ["        if: ${{ !cancelled() && steps.scope.outcome == 'success' }}"]
    assert "      - name: Save static text evidence, not candidate binaries\n" + step_conditions[0] in text
    assert text.count('uses: ') == 2
    assert text.count('shell: bash') == 2
    assert text.count('      - ') == len(guard.FILES) + 4
    assert text.index('run: python3 -I scripts/ci/validate_pkg_inspection_event.py') < text.index('python3 -I scripts/ci/inspect_pkg_candidate.py | tee')
    assert 'inspect_pkg_candidate' not in (ROOT / '.github/workflows/ci.yml').read_text()
    assert 'browser-pkg-inspection' not in (ROOT / '.github/workflows/ci.yml').read_text()


class InspectionScope(unittest.TestCase):
    def setUp(self):
        self.env = {'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_REPOSITORY': guard.REPOSITORY, 'GITHUB_RUN_ATTEMPT': '1'}
        repo = {'full_name': guard.REPOSITORY, 'fork': False}
        self.event = {'action': 'synchronize', 'number': 176, 'before': guard.PARENT, 'after': SHA,
                      'repository': repo.copy(), 'pull_request': {'number': 176, 'state': 'open',
                      'head': {'sha': SHA, 'ref': guard.BRANCH, 'repo': repo.copy()},
                      'base': {'ref': 'main', 'repo': repo.copy()}}}
        self.changes = ['A\t' + p for p in sorted(guard.FILES)]

    def validate(self, event=None, env=None, checkout=SHA, parents=None, changes=None):
        return guard.validate(self.event if event is None else event, self.env if env is None else env,
                              checkout, [SHA, guard.PARENT] if parents is None else parents,
                              self.changes if changes is None else changes)

    def test_exact_first_transition_passes(self):
        self.assertEqual(self.validate(), SHA)

    def test_wrong_environment_and_repeat_rejected(self):
        for key, value in [('GITHUB_EVENT_NAME', 'workflow_dispatch'), ('GITHUB_EVENT_NAME', 'pull_request_target'), ('GITHUB_REPOSITORY', 'fork/repo'), ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_RUN_ATTEMPT', '')]:
            env = {**self.env, key: value}
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                self.validate(env=env)

    def test_wrong_event_pr_parent_after_rejected(self):
        for key, value in [('action', 'opened'), ('number', 177), ('before', 'b' * 40), ('after', 'c' * 40)]:
            event = {**self.event, key: value}
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.validate(event=event)

    def test_wrong_branches_repositories_fork_and_state_rejected(self):
        mutations = [('head', 'ref', 'other'), ('base', 'ref', 'other'), ('head', 'sha', 'not-a-sha'),
                     ('head', 'repo', {'full_name': guard.REPOSITORY, 'fork': True}),
                     ('head', 'repo', {'full_name': 'fork/repo', 'fork': False}),
                     ('base', 'repo', {'full_name': 'other/repo'})]
        for part, key, value in mutations:
            event = copy.deepcopy(self.event)
            event['pull_request'][part][key] = value
            with self.subTest(part=part, key=key), self.assertRaises(RuntimeError):
                self.validate(event=event)
        for key, value in [('number', 177), ('state', 'closed')]:
            event = copy.deepcopy(self.event)
            event['pull_request'][key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.validate(event=event)

    def test_checkout_mismatch_merge_and_later_commit_rejected(self):
        with self.assertRaises(RuntimeError):
            self.validate(checkout='b' * 40)
        for parents in ([SHA], [SHA, guard.PARENT, 'b' * 40], [SHA, 'b' * 40]):
            with self.subTest(parents=parents), self.assertRaises(RuntimeError):
                self.validate(parents=parents)

    def test_changed_missing_duplicate_or_extra_file_rejected(self):
        for changes in (self.changes[:-1], self.changes + ['M\t.github/workflows/ci.yml'],
                        [self.changes[0].replace('A\t', 'M\t')] + self.changes[1:],
                        self.changes + [self.changes[0]]):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                self.validate(changes=changes)

    def test_actual_workflow_is_bounded(self):
        check_workflow((ROOT / '.github/workflows/browser-pkg-inspection.yml').read_text())

    def test_removed_required_guards_rejected(self):
        text = (ROOT / '.github/workflows/browser-pkg-inspection.yml').read_text()
        for required in REQUIRED:
            with self.subTest(required=required), self.assertRaises(AssertionError):
                check_workflow(text.replace(required, 'REMOVED', 1))

    def test_extra_trigger_permissions_secrets_and_steps_rejected(self):
        text = (ROOT / '.github/workflows/browser-pkg-inspection.yml').read_text()
        for original, replacement in [('  pull_request:', '  push:\n  pull_request:'),
                                      ('contents: read', 'contents: write'),
                                      ('github.run_attempt == 1', 'github.run_attempt == 1 || true'),
                                      ('          mkdir -p pkg-inspection-evidence', '          echo unexpected\n          mkdir -p pkg-inspection-evidence'),
                                      ('    steps:', '    env:\n      TOKEN: ${{ secrets.TOKEN }}\n    steps:'),
                                      ('    steps:', '    needs: browser\n    steps:'),
                                      ('    steps:', '    steps:\n      - run: echo unexpected'),
                                      ('      - name: Inspect static official PKG without running candidate content', '      - name: Inspect static official PKG without running candidate content\n        if: ${{ !cancelled() }}')]:
            with self.subTest(replacement=replacement), self.assertRaises(AssertionError):
                check_workflow(text.replace(original, replacement))


if __name__ == '__main__':
    unittest.main()
