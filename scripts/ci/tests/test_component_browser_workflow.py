"""Offline contracts for additive B2 component execution on the guarded runner."""
from pathlib import Path
import unittest

from test_browser_workflows import block, check_acceptance

ROOT = Path(__file__).resolve().parents[3]
RUN = """      - name: Run isolated component browser journeys and strict report
        run: |
          node node_modules/@playwright/test/cli.js test --config=component-browser/playwright.config.cjs
          node scripts/check-component-browser-report.cjs component-browser-results/results.json
"""
UPLOAD = """      - name: Save isolated component browser evidence
        if: ${{ !cancelled() }}
        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4
        with:
          name: component-browser-evidence
          path: frontend/component-browser-results/
          if-no-files-found: error
          retention-days: 14
"""


def check_component_workflow(ci):
    check_acceptance(ci)
    browser = block(block(ci, 'jobs'), 'browser', 2)
    for section in (RUN.rstrip(), UPLOAD.rstrip()):
        if browser.count(section) != 1:
            raise AssertionError('Exact required component execution/evidence step missing')
    # Entire tail is explicit: no conditional, env override, retry, alias, or
    # alternate run shell can be inserted into either execution/report step.
    start = browser.index('      - name: Run real-browser synthetic read-only journey')
    expected = ('      - name: Run real-browser synthetic read-only journey\n'
                '        run: npm run test:browser\n' + RUN +
                '      - name: Save synthetic browser evidence\n'
                '        if: ${{ !cancelled() }}\n'
                '        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4\n'
                '        with:\n'
                '          name: browser-evidence\n'
                '          path: frontend/browser-results/\n'
                '          if-no-files-found: error\n'
                '          retention-days: 14\n' + UPLOAD)
    if browser[start:].strip() != expected.strip():
        raise AssertionError('Original and component execution/evidence order changed')


class ComponentBrowserWorkflow(unittest.TestCase):
    def setUp(self):
        self.ci = (ROOT / '.github/workflows/ci.yml').read_text()

    def test_additive_five_case_suite_is_required_on_original_guarded_job(self):
        check_component_workflow(self.ci)

    def test_rejects_missing_or_weakened_execution_and_evidence(self):
        mutations = [
            self.ci.replace(RUN, ''),
            self.ci.replace(UPLOAD, ''),
            self.ci.replace(RUN, RUN + RUN),
            self.ci.replace('test --config=component-browser/', 'test --list --config=component-browser/'),
            self.ci.replace('test --config=component-browser/', 'test --retries=1 --config=component-browser/'),
            self.ci.replace('          node scripts/check-component-browser-report.cjs component-browser-results/results.json\n', ''),
            self.ci.replace('component-browser-results/results.json', 'browser-results/results.json'),
            self.ci.replace(RUN, RUN.replace('        run:', '        if: false\n        run:')),
            self.ci.replace(RUN, RUN.replace('        run:', '        continue-on-error: true\n        run:')),
            self.ci.replace(RUN, RUN.replace('        run:', '        shell: bash {0}\n        run:')),
            self.ci.replace(RUN, RUN.replace('        run:', '        env:\n          RUNNER_TEMP: /tmp\n        run:')),
            self.ci.replace('          name: component-browser-evidence', '          name: browser-evidence'),
            self.ci.replace('          path: frontend/component-browser-results/', '          path: frontend/browser-results/'),
            self.ci.replace(UPLOAD, UPLOAD.replace('if-no-files-found: error', 'if-no-files-found: ignore')),
            self.ci.replace(UPLOAD, UPLOAD.replace('!cancelled()', 'success()')),
        ]
        for index, changed in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises((AssertionError, ValueError)):
                check_component_workflow(changed)


if __name__ == '__main__':
    unittest.main()
