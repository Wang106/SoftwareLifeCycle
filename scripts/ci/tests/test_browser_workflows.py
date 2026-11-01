"""Offline contracts for manual diagnostics versus required browser acceptance.

This deliberately reads only the small, explicit YAML subset used by these
workflows. Ambiguous/aliased/scalar blocks fail; it is not a general YAML parser.
No workflow, native command, browser or network operation is executed.
"""
from pathlib import Path
import re
import unittest

from browser_guard_fixture import WORKFLOW


ROOT = Path(__file__).resolve().parents[3]


def block(source, key, indent=0):
    """Require one standalone mapping key and return its indented body."""
    lines = source.splitlines()
    marker = ' ' * indent + key + ':'
    starts = [i for i, line in enumerate(lines)
              if re.match(r'^' + re.escape(marker) + r'(?:\s|$)', line)]
    if len(starts) != 1 or lines[starts[0]] != marker:
        raise AssertionError('Missing, duplicate or unsupported mapping: ' + key)
    start = starts[0] + 1
    end = len(lines)
    for i in range(start, len(lines)):
        line = lines[i]
        if line.strip() and not line.lstrip().startswith('#'):
            if len(line) - len(line.lstrip()) <= indent:
                end = i
                break
    return '\n'.join(lines[start:end])


def keys(source, indent):
    result = []
    for line in source.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        width = len(line) - len(line.lstrip())
        if width < indent:
            raise AssertionError('Unexpected indentation')
        if width == indent:
            match = re.fullmatch(r'\s*([A-Za-z_][A-Za-z_0-9-]*):(?: .*|)', line)
            if not match or match[1] in result:
                raise AssertionError('Unsupported or duplicate key')
            result.append(match[1])
    return result


def check_separation(ci, diagnostic):
    if keys(block(diagnostic, 'on'), 2) != ['workflow_dispatch']:
        raise AssertionError('Diagnostics must be dispatch-only')
    if keys(block(diagnostic, 'jobs'), 2) != ['diagnostic']:
        raise AssertionError('Diagnostics must have a distinct job')
    for forbidden in ('browser-diagnostics.yml', 'hdiutil', 'googlechrome.dmg',
                      'Diagnostic-only run:', 'Diagnose official Chrome'):
        if forbidden in ci:
            raise AssertionError('Automatic CI must not execute diagnostics')
    if 'Diagnostic-only run: browser execution and acceptance intentionally prohibited' not in diagnostic:
        raise AssertionError('Diagnostic terminal prohibition missing')


def check_acceptance(ci):
    jobs = block(ci, 'jobs')
    if keys(jobs, 2) != ['backend', 'frontend', 'browser', 'acceptance']:
        raise AssertionError('Required validation jobs changed')
    if 'continue-on-error:' in ci:
        raise AssertionError('Validation failures must propagate')
    acceptance = block(jobs, 'acceptance', 2)
    if '    needs: [backend, frontend, browser]' not in acceptance.splitlines():
        raise AssertionError('Browser must remain a required dependency')
    if '    if: ${{ always() }}' not in acceptance.splitlines():
        raise AssertionError('Aggregate must report failed dependencies')
    for name in ('BACKEND', 'FRONTEND', 'BROWSER'):
        expected = '          ' + name + '_RESULT: ${{ needs.' + name.lower() + '.result }}'
        if expected not in acceptance.splitlines():
            raise AssertionError('Aggregate result binding changed')
    # Require the explicit literal shell block, not an alias or expression.
    marker = '        run: |\n'
    if acceptance.count(marker) != 1:
        raise AssertionError('Aggregate shell must be explicit')
    commands = acceptance.split(marker, 1)[1].strip().splitlines()
    if [line.strip() for line in commands] != [
        'test "$BACKEND_RESULT" = success',
        'test "$FRONTEND_RESULT" = success',
        'test "$BROWSER_RESULT" = success',
    ]:
        raise AssertionError('Aggregate must require all three successes')
    browser = block(jobs, 'browser', 2)
    if 'if' in keys(browser, 4):
        raise AssertionError('Required browser job cannot be conditional')
    if '    runs-on: macos-26' not in browser.splitlines():
        raise AssertionError('Approved browser platform changed')
    steps = block(browser, 'steps', 4)
    if re.search(r'^        if:', steps, re.MULTILINE):
        # Only evidence upload may run after an earlier failure.
        upload = steps.index('      - name: Save synthetic browser evidence')
        if re.search(r'^        if:', steps[:upload], re.MULTILINE):
            raise AssertionError('Required browser work cannot be skipped')
    guard = steps.index('      - name: Verify isolated signed official Chrome PKG candidate')
    build = steps.index('      - name: Build isolated production app')
    test = steps.index('      - name: Run real-browser synthetic read-only journey')
    if not guard < build < test:
        raise AssertionError('Guard must precede build and browser execution')
    expected_guard = '''      - name: Verify isolated signed official Chrome PKG candidate
        shell: bash
        run: |
          mkdir -p browser-results
          python3 ../scripts/ci/prepare_pkg_browser.py | tee browser-results/runner-browser.txt'''
    if steps[guard:build].strip() != expected_guard.strip():
        raise AssertionError('Candidate failure must propagate through bash pipefail')
    if '        run: npm run build' not in steps[build:test].splitlines():
        raise AssertionError('Production build missing')
    if '        run: npm run test:browser' not in steps[test:].splitlines():
        raise AssertionError('Original browser and strict report command missing')


class WorkflowSeparation(unittest.TestCase):
    def setUp(self):
        self.ci = (ROOT / '.github/workflows/ci.yml').read_text()
        self.diagnostic = (ROOT / '.github/workflows/browser-diagnostics.yml').read_text()

    def test_diagnostic_is_explicit_manual_work_only(self):
        check_separation(self.ci, self.diagnostic)
        self.assertEqual(WORKFLOW, ROOT / '.github/workflows/browser-diagnostics.yml')

    def test_browser_and_aggregate_remain_required(self):
        check_acceptance(self.ci)

    def test_contracts_run_in_existing_backend_job(self):
        backend = block(block(self.ci, 'jobs'), 'backend', 2)
        self.assertIn('        working-directory: backend', backend.splitlines())
        self.assertEqual(backend.count('        run: python -m unittest discover -s ../scripts/ci/tests -v'), 1)

    def test_mapping_ambiguity_is_rejected(self):
        for invalid in ('on: [workflow_dispatch]', 'on: *events', 'on:\non:\n',
                        'on:\n  workflow_dispatch:\non: [push]'):
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                block(invalid, 'on')

    def test_negative_controls_catch_auto_diagnostic_and_weakened_gates(self):
        mutations = [
            (self.ci, self.diagnostic.replace('  workflow_dispatch:', '  push:\n  workflow_dispatch:')),
            (self.ci + '\n# browser-diagnostics.yml\n', self.diagnostic),
            (self.ci.replace('needs: [backend, frontend, browser]', 'needs: [backend, frontend]'), self.diagnostic),
            (self.ci.replace('    runs-on: macos-26', '    if: false\n    runs-on: macos-26'), self.diagnostic),
            (self.ci.replace('        run: npm run test:browser', '        if: false\n        run: npm run test:browser'), self.diagnostic),
            (self.ci.replace('test "$BROWSER_RESULT" = success', 'true'), self.diagnostic),
            (self.ci.replace('python3 ../scripts/ci/prepare_pkg_browser.py | tee', 'python3 ../scripts/ci/prepare_pkg_browser.py || true | tee'), self.diagnostic),
            (self.ci.replace('        run: npm run test:browser', '        continue-on-error: true\n        run: npm run test:browser'), self.diagnostic),
        ]
        for ci, diagnostic in mutations:
            with self.subTest(), self.assertRaises((AssertionError, ValueError)):
                check_separation(ci, diagnostic)
                check_acceptance(ci)


if __name__ == '__main__':
    unittest.main()
