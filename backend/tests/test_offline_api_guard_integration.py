"""Request-bracketing integration contracts; all runtime operations are mocked."""
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import offline_migration_database_rehearsal as joint
import offline_migrated_api_probe as probe
import test_offline_api_lifecycle_integration as lifecycle


class GuardIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(probe, 'guard'), 'guard comparison not integrated')
        self.guard = probe.guard
        self.fixture = lifecycle.LifecycleTests()

    def run_case(self, **kwargs):
        return self.fixture.run_case(**kwargs)

    def test_exact_two_matches_bracket_five_unchanged_http_cases(self):
        result = self.run_case()
        events = self.fixture.events
        before, after = [i for i, event in enumerate(events) if event == 'guard_collect']
        http = [i for i, event in enumerate(events) if event.startswith('http:')]
        self.assertEqual([events[i][5:] for i in http], list(probe.CASES))
        self.assertTrue(before < min(http) < max(http) < after < events.index('remove_api'))
        self.assertEqual(result['format'], 'slc-offline-migration-api-lifecycle-v2')
        self.assertEqual(result['guard_coverage'], 'api-alive-five-http-cases-three-functions-six-triggers')
        self.assertEqual(result['guard_checks_before'], self.guard.expected_checks())
        self.assertEqual(result['guard_checks_after'], self.guard.expected_checks())
        self.assertEqual(result['guard_transactions_closed'], 2)
        self.assertEqual(self.fixture.removals(), ['remove_api', 'remove_migration', 'remove_pg'])

    def test_guard_source_prepare_precedes_any_build_or_create(self):
        self.run_case()
        events = self.fixture.events
        self.assertLess(events.index('guard_prepare'), events.index('migration_prepare'))
        self.assertIs(self.fixture.guard_budget, self.fixture.probe_budget)
        self.assertEqual(self.fixture.guard_program, 'MOCK_BOUND_GUARD_PROGRAM')

    def test_legacy_migration_only_never_prepares_or_collects_guard(self):
        result = self.run_case(enabled=False)
        self.assertNotIn('guard_prepare', self.fixture.events)
        self.assertNotIn('guard_collect', self.fixture.events)
        self.assertEqual(result['format'], 'slc-offline-migration-database-rehearsal-v1')

    def test_guard_prepare_failure_prevents_build_or_container(self):
        with self.assertRaises(joint.Blocked): self.run_case(guard_failure='prepare')
        self.assertFalse(any(e in self.fixture.events for e in ('migration_prepare', 'create_pg', 'create_api')))
        self.assertEqual(self.fixture.removals(), [])

    def test_before_failure_skips_http_and_cleans_once(self):
        with self.assertRaises(joint.Blocked): self.run_case(guard_failure='before')
        self.assertEqual(self.fixture.events.count('guard_collect'), 1)
        self.assertFalse(any(e.startswith('http:') for e in self.fixture.events))
        self.assertEqual(self.fixture.removals(), ['remove_api', 'remove_migration', 'remove_pg'])

    def test_after_failure_fails_success_and_cleans_once(self):
        with self.assertRaises(joint.Blocked): self.run_case(guard_failure='after')
        self.assertEqual(self.fixture.events.count('guard_collect'), 2)
        self.assertEqual(sum(e.startswith('http:') for e in self.fixture.events), 5)
        self.assertEqual(self.fixture.removals(), ['remove_api', 'remove_migration', 'remove_pg'])

    def test_guard_control_exception_retained_through_all_cleanup(self):
        for phase in ('before', 'after'):
            for error in (KeyboardInterrupt('guard control'), SystemExit(9)):
                with self.subTest(phase=phase, error=type(error)), self.assertRaises(type(error)) as caught:
                    self.run_case(guard_failure=(phase, error))
                self.assertIs(caught.exception, error)
                self.assertEqual(self.fixture.removals(), ['remove_api', 'remove_migration', 'remove_pg'])

    def test_pair_namespace_or_version_change_cannot_pass(self):
        for key, value in (('namespace_oid', 999), ('server_version_num', 160016)):
            with self.subTest(key=key), self.assertRaises(joint.Blocked):
                self.run_case(guard_mutation=lambda result: result.update({key:value}))
            self.assertEqual(self.fixture.removals(), ['remove_api', 'remove_migration', 'remove_pg'])

    def test_guard_receipt_v1_missing_or_inexact_checks_rejected(self):
        mutations = [lambda r:r.update(format='slc-migrated-api-probe-v1'),
            lambda r:r.pop('guard_checks_before'), lambda r:r.update(guard_transactions_closed=True),
            lambda r:r['guard_checks_after'][0].update(matched=False),
            lambda r:r['guard_checks_before'].pop(),
            lambda r:r.update(guard_coverage='all-schema')]
        for mutate in mutations:
            with self.subTest(mutate=mutate), self.assertRaises(joint.Blocked):
                self.run_case(probe_mutation=mutate)
            self.assertEqual(self.fixture.removals(), ['remove_api', 'remove_migration', 'remove_pg'])

    def test_guard_transport_separate_from_unchanged_http_bounds(self):
        self.run_case()
        guard_calls = [kw for args, kw in self.fixture.calls if 'MOCK_BOUND_GUARD_PROGRAM' in args]
        http_calls = [kw for args, kw in self.fixture.calls if probe.PROBE_PROGRAM in args]
        self.assertEqual(len(guard_calls), 2)
        self.assertTrue(all(0 < kw['timeout'] <= 45 and kw['limit'] == 524288 for kw in guard_calls))
        self.assertTrue(all(kw['timeout'] <= 8 and kw['limit'] == 4096 for kw in http_calls))

    def test_guard_work_exhaustion_uses_original_cleanup_without_retry(self):
        with self.assertRaises(joint.Blocked): self.run_case(guard_failure='exhaust_before')
        self.assertLessEqual(self.fixture.events.count('guard_collect'), 1)
        self.assertEqual(self.fixture.removals(), ['remove_api', 'remove_migration', 'remove_pg'])

    def test_mutated_budget_during_guard_cannot_prevent_owned_api_cleanup(self):
        for value in (4400.0, 2400.0, None):
            with self.subTest(value=value), self.assertRaises(joint.Blocked) as caught:
                self.run_case(guard_failure=('mutate_budget', value))
            self.assertEqual(str(caught.exception), 'BUDGET_CHANGED')
            self.assertEqual(self.fixture.removals(), ['remove_api', 'remove_migration', 'remove_pg'])
            self.assertEqual(self.fixture.events.count('guard_collect'), 1)

    def test_final_receipt_has_only_safe_summary_and_false_acceptance_flags(self):
        output = io.StringIO()
        with patch('sys.stdout', output): result = self.run_case()
        self.assertEqual(output.getvalue(), '')
        encoded = json.dumps(result)
        for forbidden in ('PRIVATE_SENTINEL', 'namespace_oid', 'body_sha256', 'definition'):
            self.assertNotIn(forbidden, encoded)
        for key in ('readonly_role_verified', 'complete_schema_verified', 'provenance_authenticated'):
            self.assertIs(result[key], False)


if __name__ == '__main__': unittest.main()
