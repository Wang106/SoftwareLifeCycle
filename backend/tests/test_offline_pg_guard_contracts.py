"""Synthetic observations only; no database, SQL, process or network execution."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import offline_pg_catalog_evidence as catalog


class GuardTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / 'scripts/offline_pg_guard_contracts.py'
        self.assertTrue(path.is_file(), 'guard comparison is not implemented')
        spec = importlib.util.spec_from_file_location('guard_contracts', path)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.namespace = 'ci_catalog_' + 'a' * 32
        facts = json.loads((ROOT / 'deploy/offline/migration-schema-0030.json').read_text())['facts']
        groups = {key: [] for key in catalog.LIMITS}
        for name in catalog.FUNCTIONS:
            fact = facts['function:' + name]
            groups['functions'].append(dict(namespace=self.namespace, name=name,
                identity_arguments='', result='trigger', language='plpgsql', security_definer=False,
                body_sha256=fact['body_sha256'], body_bytes=100))
        for name in catalog.TRIGGERS:
            fact = facts['trigger:' + name]
            groups['triggers'].append(dict(namespace=self.namespace, table=fact['table'], name=name,
                function_namespace=self.namespace, function_name=fact['function'], function_arguments='',
                type_bits=27, enabled='O', internal=False, constraint=False,
                argument_count=0, argument_bytes=0, has_when=False,
                definition='uninterpreted PG definition'))
        self.document = dict(format='slc-pg16-catalog-observation-v2',
            status='CATALOG_COLLECTED_NOT_ACCEPTANCE', namespace=self.namespace, namespace_oid=1234,
            server_version_num=160015, database_verified=False, complete_schema_verified=False,
            transaction_completed=False, observations=groups)

    def check(self, document=None, namespace=None):
        return self.m.check_observation(self.document if document is None else document,
            self.namespace if namespace is None else namespace)

    def test_matching_selected_guards_remain_limited(self):
        result = self.check()
        self.assertEqual(result['status'], 'GUARD_CONTRACT_MATCHED')
        self.assertEqual(len(result['checks']), 9)
        for field in ('database_verified', 'complete_schema_verified', 'readonly_role_verified',
                      'provenance_authenticated', 'transaction_completed'):
            self.assertIs(result[field], False)
        self.assertNotIn('public', json.dumps(self.document))
        self.assertNotIn(self.namespace, json.dumps(result))

    def test_no_input_mutation_or_order_dependency(self):
        before = copy.deepcopy(self.document)
        self.check()
        self.assertEqual(self.document, before)
        for rows in self.document['observations'].values(): rows.reverse()
        self.assertEqual(self.check()['status'], 'GUARD_CONTRACT_MATCHED')

    def test_missing_objects_are_mismatch_not_invented(self):
        for group in ('functions', 'triggers'):
            doc = copy.deepcopy(self.document); doc['observations'][group].pop()
            self.assertEqual(self.check(doc)['status'], 'GUARD_CONTRACT_MISMATCH')

    def test_function_contract_changes_fail(self):
        for key, value in [('identity_arguments', 'integer'), ('result', 'integer'),
                           ('language', 'sql'), ('security_definer', True), ('body_sha256', '0' * 64)]:
            doc = copy.deepcopy(self.document); doc['observations']['functions'][0][key] = value
            with self.subTest(key=key):
                self.assertEqual(self.check(doc)['status'], 'GUARD_CONTRACT_MISMATCH')

    def test_trigger_contract_changes_fail(self):
        for key, value in [('table', 'releases'), ('function_namespace', 'other'),
                           ('function_name', 'guard_batch_physical_write'), ('function_arguments', 'integer'),
                           ('type_bits', 19), ('enabled', 'D'), ('internal', True), ('constraint', True),
                           ('argument_count', 1), ('argument_bytes', 1), ('has_when', True)]:
            doc = copy.deepcopy(self.document); doc['observations']['triggers'][0][key] = value
            with self.subTest(key=key):
                self.assertEqual(self.check(doc)['status'], 'GUARD_CONTRACT_MISMATCH')

    def test_trigger_arguments_and_when_need_explicit_v2_evidence(self):
        for key in ('argument_count', 'argument_bytes', 'has_when'):
            doc = copy.deepcopy(self.document); del doc['observations']['triggers'][0][key]
            self.assertEqual(self.check(doc)['status'], 'UNKNOWN')
        doc = dict(self.document, format='slc-pg16-catalog-observation-v1')
        self.assertEqual(self.check(doc)['status'], 'UNKNOWN')

    def test_duplicates_extra_selected_overloads_and_wrong_group_names_reject(self):
        for group in ('functions', 'triggers'):
            doc = copy.deepcopy(self.document)
            doc['observations'][group].append(copy.deepcopy(doc['observations'][group][0]))
            self.assertNotEqual(self.check(doc)['status'], 'GUARD_CONTRACT_MATCHED')
        doc = copy.deepcopy(self.document)
        extra = dict(doc['observations']['functions'][0], identity_arguments='integer')
        doc['observations']['functions'].append(extra)
        self.assertEqual(self.check(doc)['status'], 'GUARD_CONTRACT_MISMATCH')
        doc['observations']['functions'][0]['name'] = 'unexpected'
        self.assertEqual(self.check(doc)['status'], 'UNKNOWN')

    def test_namespace_is_exact_and_never_rewritten(self):
        self.assertEqual(self.check(namespace='other')['status'], 'UNKNOWN')
        for namespace in ('', 'pg_catalog', 'information_schema', 'public; DROP', 'A', None, True):
            self.assertEqual(self.m.check_observation(self.document, namespace)['status'], 'UNKNOWN')
        doc = copy.deepcopy(self.document); doc['observations']['functions'][0]['namespace'] = 'public'
        self.assertEqual(self.check(doc)['status'], 'UNKNOWN')

    def test_boolean_integer_aliases_are_unknown(self):
        for group, key, value in [('functions', 'body_bytes', True), ('functions', 'security_definer', 0),
                                  ('triggers', 'type_bits', True), ('triggers', 'argument_count', False),
                                  ('triggers', 'argument_bytes', False), ('triggers', 'has_when', 0)]:
            doc = copy.deepcopy(self.document); doc['observations'][group][0][key] = value
            self.assertEqual(self.check(doc)['status'], 'UNKNOWN')

    def test_envelope_types_and_flags_are_exact(self):
        for key, value in [('namespace_oid', True), ('namespace_oid', 0), ('server_version_num', 150000),
                           ('database_verified', True), ('complete_schema_verified', 0),
                           ('transaction_completed', True), ('status', 'ACCEPTED'), ('extra', 'SECRET')]:
            with self.subTest(key=key):
                self.assertEqual(self.check(dict(self.document, **{key: value}))['status'], 'UNKNOWN')
        for value in (None, [], True, 'SECRET'):
            self.assertEqual(self.m.check_observation(value, self.namespace)['status'], 'UNKNOWN')

    def test_bounds_and_malformed_data_are_unknown(self):
        cases = [('functions', 'body_bytes', -1), ('functions', 'body_bytes', catalog.MAX_TEXT + 1),
                 ('functions', 'body_sha256', 'G' * 64), ('functions', 'body_sha256', '0' * 65),
                 ('triggers', 'definition', 'x' * (catalog.MAX_TEXT + 1)),
                 ('triggers', 'definition', '\ud800'), ('triggers', 'definition', 'x\x00y')]
        for group, key, value in cases:
            doc = copy.deepcopy(self.document); doc['observations'][group][0][key] = value
            self.assertEqual(self.check(doc)['status'], 'UNKNOWN')
        doc = copy.deepcopy(self.document)
        doc['observations']['functions'] *= 20
        self.assertEqual(self.check(doc)['status'], 'UNKNOWN')

    def test_other_groups_are_validated_but_not_called_complete(self):
        doc = copy.deepcopy(self.document); doc['observations']['tables'] = [{'secret': 'SECRET'}]
        self.assertEqual(self.check(doc)['status'], 'UNKNOWN')
        doc = copy.deepcopy(self.document); del doc['observations']['columns']
        self.assertEqual(self.check(doc)['status'], 'UNKNOWN')

    def test_raw_trigger_definition_is_not_parsed_or_normalized(self):
        self.document['observations']['triggers'][0]['definition'] = 'Any raw PG rendering'
        self.assertEqual(self.check()['status'], 'GUARD_CONTRACT_MATCHED')

    def test_body_length_is_bounded_not_authenticated_from_manifest(self):
        for length in (0, 1, catalog.MAX_TEXT):
            self.document['observations']['functions'][0]['body_bytes'] = length
            self.assertEqual(self.check()['status'], 'GUARD_CONTRACT_MATCHED')

    def test_manifest_failure_is_sanitized_and_not_defaulted(self):
        with patch.object(self.m.schema, 'expected_facts', side_effect=OSError('SECRET')):
            result = self.check()
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertNotIn('SECRET', json.dumps(result))

    def test_control_exceptions_are_not_normalized_as_unknown(self):
        for exception in (KeyboardInterrupt(), SystemExit(3)):
            with patch.object(self.m.schema, 'expected_facts', side_effect=exception):
                with self.assertRaises(type(exception)) as caught: self.check()
                self.assertIs(caught.exception, exception)

    def test_import_does_not_read_manifest_and_no_expected_override_exists(self):
        import inspect
        with patch.object(self.m.schema, 'expected_facts') as reader:
            path = ROOT / 'scripts/offline_pg_guard_contracts.py'
            spec = importlib.util.spec_from_file_location('guard_import', path)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        reader.assert_not_called()
        self.assertEqual(list(inspect.signature(module.check_observation).parameters), ['document', 'namespace'])

    def test_total_observation_budget_is_not_just_selected_groups(self):
        doc = copy.deepcopy(self.document)
        doc['observations']['constraints'] = [dict(catalog.EXAMPLES['constraints'],
            namespace=self.namespace, name='check_' + str(i), definition='x' * 16000) for i in range(40)]
        self.assertEqual(self.check(doc)['status'], 'UNKNOWN')


class CollectorV2Tests(unittest.TestCase):
    def test_collects_structured_arguments_and_when_without_payload(self):
        sql = catalog.QUERIES['triggers']
        for fragment in ('t.tgnargs', 'pg_catalog.octet_length(t.tgargs)', 't.tgqual IS NOT NULL'):
            self.assertIn(fragment, sql)
        for key, value in [('argument_count', 0), ('argument_bytes', 0), ('has_when', False)]:
            self.assertIn(key, catalog.EXAMPLES['triggers'])
            self.assertIs(type(catalog.EXAMPLES['triggers'][key]), type(value))

    def test_new_fields_reject_boolean_aliases(self):
        for key, value in [('argument_count', True), ('argument_bytes', False), ('has_when', 0)]:
            row = dict(catalog.EXAMPLES['triggers'], namespace='public', **{key: value})
            with self.assertRaises(catalog.CatalogError): catalog.validate_record('triggers', row, 'public')

    def test_collection_preserves_structured_values_not_raw_arguments(self):
        from test_offline_pg_catalog_evidence import Connection
        context = dict(server_version_num=160015, read_only=True, isolation='repeatable read',
            search_path='pg_catalog', statement_timeout_ms=5000, lock_timeout_ms=1000,
            idle_timeout_ms=15000, namespace_oid=123)
        for count, size, when in ((0, 0, False), (1, 10, False), (0, 0, True)):
            row = dict(catalog.EXAMPLES['triggers'], namespace='public',
                argument_count=count, argument_bytes=size, has_when=when)
            connection = Connection([[(context,)]] + [[] for _ in range(5)] + [[(row,)]])
            result = catalog.collect(connection, 'public')
            self.assertEqual(result['format'], 'slc-pg16-catalog-observation-v2')
            self.assertEqual(result['observations']['triggers'], [row])


if __name__ == '__main__': unittest.main()
