"""Execute the real workflow coordinator with all child/runtime/signal work mocked."""
import unittest
import test_offline_image_rehearsal as workflow_tests

ROOT = workflow_tests.ROOT


class WebStartupWorkflowTests(unittest.TestCase):
    # Share the bounded synthetic harness, not its existing test methods.
    COMMIT = workflow_tests.ImageBundleWorkflowTests.COMMIT
    DIGEST = workflow_tests.ImageBundleWorkflowTests.DIGEST
    TOKEN = workflow_tests.ImageBundleWorkflowTests.TOKEN
    workflow_python = workflow_tests.ImageBundleWorkflowTests.workflow_python
    result = workflow_tests.ImageBundleWorkflowTests.result
    exercise = workflow_tests.ImageBundleWorkflowTests.exercise
    api_receipt = workflow_tests.ImageBundleWorkflowTests.api_receipt
    web_receipt = workflow_tests.ImageBundleWorkflowTests.web_receipt
    blocked = workflow_tests.ImageBundleWorkflowTests.blocked

    def test_web_option_is_default_off_and_not_shell_source(self):
        text = (ROOT / '.github/workflows/offline-image-rehearsal.yml').read_text()
        self.assertRegex(text, r'run_web_startup:\n(?:        .*\n)*?        default: false')
        self.assertIn('RUN_WEB_STARTUP: ${{ inputs.run_web_startup }}', text)
        self.assertIn('test_offline_web_startup_rehearsal.py', text)
        self.assertIn('test_offline_web_workflow.py', text)
        self.assertNotIn('${{', self.workflow_python())
        self.assertIn('contents: read', text)
        self.assertIn('timeout-minutes: 60', text)
        self.assertIn('20 * 1024**3', text)
        for forbidden in ('upload-artifact', 'actions/cache', 'docker login', 'docker push', 'schedule:'):
            self.assertNotIn(forbidden, text)

    def test_eight_option_combinations_start_only_requested_same_run_images(self):
        for exported in ('false', 'true'):
            for api in ('false', 'true'):
                for web in ('false', 'true'):
                    with self.subTest(exported=exported, api=api, web=web):
                        value = self.exercise(exported, startup=api, web=web)
                        self.assertEqual(value['status'], 0)
                        self.assertEqual(value['api_calls'], [('sha256:' + 'e' * 64, self.COMMIT)] if api == 'true' else [])
                        self.assertEqual(value['web_calls'], [('sha256:' + 'f' * 64, self.COMMIT)] if web == 'true' else [])
                        self.assertEqual(value['runtime_order'], (['api'] if api == 'true' else []) + (['web'] if web == 'true' else []))
                        self.assertEqual(len(value['calls']), 2 + (exported == 'true'))
                        self.assertEqual(len(value['handlers']), 2 * ((api == 'true') + (web == 'true')))
                        for _, restored in value['handlers'][1::2]:
                            self.assertIs(restored, value['previous_handler'])
                        if web == 'true':
                            self.assertIn('WEB_STARTUP_SSR_PASSED_NOT_BROWSER_OR_OFFLINE_ACCEPTANCE', value['summary'])
                            self.assertIn('2/2', value['summary'])
                            self.assertIn('api_integration=false', value['summary'])
                            self.assertIn('browser_hydration=false', value['summary'])
                            self.assertNotIn('no application/DB startup', value['summary'])
                        else:
                            self.assertIn('Web process startup not requested', value['summary'])

    def test_invalid_or_missing_web_option_stops_before_any_child(self):
        for option in ('', 'TRUE', 'False', '1', 'true\n', 'true; echo PRIVATE', '${{ secrets.PRIVATE }}'):
            with self.subTest(option=option):
                value = self.exercise(startup='true', web=option)
                self.blocked(value, calls=0)
                self.assertEqual(value['api_calls'] + value['web_calls'], [])
        self.blocked(self.exercise(missing_env='RUN_WEB_STARTUP'), calls=0)

    def test_web_never_starts_after_prior_failure_or_bad_image_identity(self):
        for stage, count in [('checkout', 1), ('rehearsal', 2), ('verification', 3)]:
            value = self.exercise('true', web='true', fail=(stage, OSError('PRIVATE')))
            self.blocked(value, calls=count)
            self.assertEqual(value['web_calls'], [])
            self.assertEqual(value['handlers'], [])
        for key, bad in [('source_commit', 'b' * 40), ('image_id', 'tag:untrusted'), ('platform', 'arm64')]:
            result = self.result()
            result['images']['web'][key] = bad
            value = self.exercise(result=result, web='true')
            self.blocked(value, calls=2)
            self.assertEqual(value['web_calls'], [])
        value = self.exercise('true', web='true', verified={})
        self.blocked(value, calls=3)
        self.assertEqual(value['web_calls'], [])

    def test_web_never_starts_after_api_failure_or_uncertain_removal(self):
        for code, receipt in [(2, {'status': 'BLOCKED', 'reason': 'CLEANUP_UNCERTAIN'}),
                              (0, {**self.api_receipt(), 'container_removed': False})]:
            value = self.exercise(startup='true', web='true', api_return=(receipt, code))
            self.blocked(value, calls=2)
            self.assertEqual(len(value['api_calls']), 1)
            self.assertEqual(value['web_calls'], [])
        value = self.exercise(startup='true', web='true', api_error=KeyboardInterrupt('PRIVATE'))
        self.blocked(value, calls=2)
        self.assertEqual(value['web_calls'], [])

    def test_web_receipt_is_exact_typed_and_bound_to_same_build(self):
        valid = self.web_receipt()
        cases = [None, [], {}, {**valid, 'PRIVATE': 'extra'}]
        cases += [{key: value for key, value in valid.items() if key != missing} for missing in valid]
        cases += [{**valid, key: bad} for key, bad in [
            ('status', 'BLOCKED'), ('phase', 'PROBES'), ('cases_passed', 1), ('cases_passed', True),
            ('cases_total', 2.0), ('container_removed', False), ('container_removed', 1),
            ('evidence_kind', 'mock'), ('database_ready', True), ('database_ready', 0),
            ('api_integration', True), ('api_integration', 0), ('browser_hydration', True),
            ('offline_acceptance', True), ('image_id', 'sha256:' + 'e' * 64),
            ('source_commit', 'b' * 40), ('provenance', 'authenticated'), ('limitations', 'PRIVATE')]]
        for receipt in cases:
            with self.subTest(receipt=receipt):
                value = self.exercise(web='true', web_return=(receipt, 0))
                self.blocked(value, calls=2)
                self.assertEqual(len(value['web_calls']), 1)
                self.assertIs(value['handlers'][-1][1], value['previous_handler'])
        for code in (2, False, True, 0.0, None):
            self.blocked(self.exercise(web='true', web_return=(valid, code)), calls=2)

    def test_web_return_shape_and_cleanup_uncertainty_fail_without_retry(self):
        for result in ([], {}, [self.web_receipt(), 0], (self.web_receipt(),), (self.web_receipt(), 0, None),
                       ({'status': 'BLOCKED', 'reason': 'CLEANUP_UNCERTAIN', 'container_removed': False}, 2)):
            with self.subTest(result=result):
                value = self.exercise(web='true', web_return=result)
                self.blocked(value, calls=2)
                self.assertEqual(len(value['web_calls']), 1)
                self.assertFalse(any('docker' in arg or arg == 'rm' for args in value['calls'] for arg in args))

    def test_web_exception_and_signal_restore_handler_without_retry(self):
        class PrivateError(Exception):
            def __str__(self): raise AssertionError('PRIVATE string conversion')
        for api in ('false', 'true'):
            for error in (OSError('PRIVATE'), KeyboardInterrupt('PRIVATE'), PrivateError(), 'signal'):
                with self.subTest(api=api, error=type(error).__name__):
                    value = self.exercise('true', startup=api, web='true', web_error=error)
                    self.blocked(value, calls=3)
                    self.assertEqual(len(value['web_calls']), 1)
                    self.assertIs(value['handlers'][-1][1], value['previous_handler'])

    def test_web_signal_install_or_restore_failure_cannot_report_success(self):
        for api in ('false', 'true'):
            for offset in (1, 2):
                with self.subTest(api=api, offset=offset):
                    value = self.exercise(startup=api, web='true', handler_error=OSError('PRIVATE'),
                                          handler_error_at=(2 if api == 'true' else 0) + offset)
                    self.blocked(value, calls=2)
                    self.assertEqual(len(value['web_calls']), 0 if offset == 1 else 1)
                    self.assertIs(value['handlers'][-1][1], value['previous_handler'])

    def test_shared_budget_reserves_both_runtimes_without_extending_deadline(self):
        for exported in ('false', 'true'):
            for api in ('false', 'true'):
                for web in ('false', 'true'):
                    with self.subTest(exported=exported, api=api, web=web):
                        value = self.exercise(exported, startup=api, web=web,
                                              elapsed={'checkout': 10, 'rehearsal': 500})
                        self.assertEqual(value['status'], 0)
                        budgets = dict(value['timeouts'])
                        reserved = 30 + (600 if exported == 'true' else 0) + 240 * ((api == 'true') + (web == 'true'))
                        self.assertEqual(budgets['rehearsal'], 3300 - 10 - reserved)
                        if exported == 'true': self.assertEqual(budgets['verification'], 600)

    def test_api_entry_keeps_entire_web_window_in_reserve(self):
        # 509 seconds remain: enough for either stage alone, not both plus summary.
        value = self.exercise(startup='true', web='true', elapsed={'rehearsal': 2791})
        self.blocked(value, calls=2)
        self.assertEqual(value['api_calls'] + value['web_calls'], [])
        self.assertEqual(value['handlers'], [])
        value = self.exercise(startup='true', web='true', elapsed={'rehearsal': 2790, 'handler_install': 1})
        self.blocked(value, calls=2)
        self.assertEqual(value['api_calls'] + value['web_calls'], [])
        self.assertIs(value['handlers'][-1][1], value['previous_handler'])

    def test_web_budget_checks_before_and_after_handler_install(self):
        for elapsed in ({'rehearsal': 3031}, {'rehearsal': 3030, 'web_handler_install': 1}):
            value = self.exercise(web='true', elapsed=elapsed)
            self.blocked(value, calls=2)
            self.assertEqual(value['web_calls'], [])
        value = self.exercise(startup='true', web='true', elapsed={'rehearsal': 2790, 'api': 241})
        self.blocked(value, calls=2)
        self.assertEqual(len(value['api_calls']), 1)
        self.assertEqual(value['web_calls'], [])

    def test_verification_keeps_web_window_and_late_web_cannot_publish_success(self):
        value = self.exercise('true', web='true', elapsed={'rehearsal': 3031})
        self.blocked(value, calls=2)
        self.assertEqual(value['web_calls'], [])
        value = self.exercise(web='true', elapsed={'rehearsal': 3030, 'web': 241})
        self.blocked(value, calls=2)
        self.assertEqual(len(value['web_calls']), 1)
        self.assertIs(value['handlers'][-1][1], value['previous_handler'])

    def test_web_summary_has_no_private_data_or_three_tier_claim(self):
        value = self.exercise('true', startup='true', web='true')
        self.assertEqual(value['status'], 0)
        self.assertNotIn('PRIVATE', value['summary'] + value['stdout'] + value['stderr'])
        self.assertNotIn('/tmp/', value['summary'])
        self.assertIn('not a Web/API/database integration', value['summary'])
        self.assertIn('container_removed=true', value['summary'])
        self.assertIn('offline_acceptance=false', value['summary'])
        self.assertIn('no database startup', value['summary'])
        self.blocked(self.exercise(web='true', summary_error=True), calls=2)


if __name__ == '__main__':
    unittest.main()
