"""Synthetic evidence only; no PostgreSQL, SQL execution or application imports."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/offline_migration_schema_evidence.py'
MANIFEST = ROOT / 'deploy/offline/migration-schema-0029.json'


class SchemaEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), 'new schema checker is not implemented')
        spec = importlib.util.spec_from_file_location('schema_evidence', SCRIPT)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.manifest = json.loads(MANIFEST.read_text())
        self.document = {'format': self.m.EVIDENCE_FORMAT,
                         'checklist': self.m.CHECKLIST,
                         'facts': copy.deepcopy(self.manifest['facts'])}

    def check(self, document=None):
        return self.m.check_bytes(json.dumps(document or self.document).encode())

    def test_matching_self_report_has_explicit_limitations(self):
        result = self.check()
        self.assertEqual(result['status'], 'STRUCTURE_CHECKLIST_MATCHED')
        self.assertFalse(result['database_verified'])
        self.assertIn('self-reported', result['limitations'])
        self.assertNotIn('ready', result)

    def test_empty_fact_set_mismatches_not_accepts(self):
        self.document['facts'] = {}
        self.assertEqual(self.check()['status'], 'STRUCTURE_CHECKLIST_MISMATCH')

    def test_every_missing_fact_mismatches(self):
        for key in self.document['facts']:
            with self.subTest(key=key):
                doc = copy.deepcopy(self.document)
                del doc['facts'][key]
                self.assertEqual(self.check(doc)['status'], 'STRUCTURE_CHECKLIST_MISMATCH')

    def test_each_mutated_scalar_does_not_match(self):
        def paths(value, path=()):
            if type(value) is dict:
                for key, item in value.items():
                    yield from paths(item, path + (key,))
            elif type(value) is list:
                for i, item in enumerate(value):
                    yield from paths(item, path + (i,))
            else:
                yield path, value
        for key, fact in self.document['facts'].items():
            for path, value in paths(fact):
                with self.subTest(key=key, path=path):
                    doc = copy.deepcopy(self.document)
                    obj = doc['facts'][key]
                    for part in path[:-1]:
                        obj = obj[part]
                    obj[path[-1]] = (not value if type(value) is bool else
                                    value + 1 if type(value) is int else
                                    'changed' if value is None else value + '_changed')
                    self.assertNotEqual(self.check(doc)['status'], 'STRUCTURE_CHECKLIST_MATCHED')

    def test_unknown_fact_is_unknown_and_not_echoed(self):
        self.document['facts']['SECRET_TARGET'] = {'secret': 'PASSWORD'}
        result = self.check()
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertNotIn('SECRET_TARGET', json.dumps(result))
        self.assertNotIn('PASSWORD', json.dumps(result))

    def test_top_level_and_nested_unknown_fields_rejected(self):
        self.document['extra'] = 1
        self.assertEqual(self.check()['status'], 'UNKNOWN')
        del self.document['extra']
        next(iter(self.document['facts'].values()))['extra'] = 1
        self.assertEqual(self.check()['status'], 'UNKNOWN')

    def test_bool_cannot_substitute_for_integer(self):
        self.document['facts']['version']['row_count'] = True
        self.assertEqual(self.check()['status'], 'UNKNOWN')

    def test_wrong_format_and_checklist_rejected(self):
        for key in ('format', 'checklist'):
            with self.subTest(key=key):
                doc = copy.deepcopy(self.document)
                doc[key] = 'other'
                self.assertEqual(self.check(doc)['status'], 'UNKNOWN')

    def test_duplicate_keys_rejected_at_any_level(self):
        for raw in (b'{"format":1,"format":1}',
                    json.dumps(self.document).encode().replace(b'"facts": {', b'"facts": {"version": {},', 1)):
            self.assertEqual(self.m.check_bytes(raw)['status'], 'UNKNOWN')

    def test_numbers_unicode_depth_and_size_fail_closed(self):
        for raw in (b'', b'null', b'[]', b'{}{}', b'\xff', b'\xef\xbb\xbf{}',
                    b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e2}',
                    b'[' * 1000 + b'0' + b']' * 1000,
                    b' ' * (self.m.MAX_BYTES + 1)):
            with self.subTest(raw=raw[:30]):
                self.assertEqual(self.m.check_bytes(raw)['status'], 'UNKNOWN')

    def test_regular_file_and_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'evidence.json'
            for facts, status, code in ((self.document['facts'], 'STRUCTURE_CHECKLIST_MATCHED', 0),
                                        ({}, 'STRUCTURE_CHECKLIST_MISMATCH', 1)):
                doc = dict(self.document, facts=facts)
                path.write_text(json.dumps(doc))
                result = subprocess.run([sys.executable, '-I', str(SCRIPT), '--evidence', str(path)],
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode, code)
                self.assertEqual(json.loads(result.stdout)['status'], status)
                self.assertEqual(result.stderr, b'')
            path.write_text('invalid SECRET')
            result = subprocess.run([sys.executable, '-I', str(SCRIPT), '--evidence', str(path)], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b'SECRET', result.stdout + result.stderr)

    def test_parent_and_leaf_symlinks_and_fifo_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / 'real'; real.mkdir()
            path = real / 'evidence.json'; path.write_text(json.dumps(self.document))
            (root / 'link').symlink_to(real, target_is_directory=True)
            (root / 'leaf').symlink_to(path)
            os.mkfifo(root / 'fifo')
            for target in (root / 'link/evidence.json', root / 'leaf', root / 'fifo', real):
                self.assertEqual(self.m.check_file(str(target))['status'], 'UNKNOWN')

    def test_bad_paths_and_platform_fail_closed(self):
        for path in ('relative', '/tmp/../x', '/tmp//x', '/tmp/./x', '/tmp/x\n', '/', '/tmp/\\x'):
            self.assertEqual(self.m.check_file(path)['status'], 'UNKNOWN')
        with mock.patch.object(self.m, 'supported', return_value=False):
            self.assertEqual(self.m.check_file('/tmp/file')['reason'], 'UNSUPPORTED_PLATFORM')

    def test_file_mutation_read_error_and_close_error_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'evidence.json'; path.write_text(json.dumps(self.document))
            with mock.patch.object(self.m.os, 'read', side_effect=OSError('SECRET')):
                self.assertEqual(self.m.check_file(str(path))['status'], 'UNKNOWN')
            original = self.m.fingerprint
            calls = []
            def changed(info):
                calls.append(1)
                return original(info) + (len(calls),)
            with mock.patch.object(self.m, 'fingerprint', side_effect=changed):
                self.assertEqual(self.m.check_file(str(path))['status'], 'UNKNOWN')

    def test_missing_or_tampered_trusted_manifest_is_unknown(self):
        with mock.patch.object(self.m, 'MANIFEST_PATH', Path('/tmp/no-schema-manifest')):
            self.assertEqual(self.check()['status'], 'UNKNOWN')
        with mock.patch.object(self.m, 'MANIFEST_SHA256', '0' * 64):
            self.assertEqual(self.check()['status'], 'UNKNOWN')

    def test_manifest_provenance_bytes_are_bound(self):
        self.assertEqual(hashlib.sha256(MANIFEST.read_bytes()).hexdigest(), self.m.MANIFEST_SHA256)
        for path, digest in self.manifest['sources'].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)
        self.assertEqual(self.manifest['source_commit'], '44e307a71a22f93f8c2ae611cf10678b0420499f')

    def test_scope_includes_tables_columns_constraints_indexes_functions_triggers(self):
        facts = self.manifest['facts']
        for table in ('changeover_baselines', 'changeover_corrections', 'batch_baselines', 'batch_corrections'):
            self.assertIn('table:' + table, facts)
            self.assertIn('column:' + table + '.id', facts)
            self.assertIn('trigger:' + table + '_append_only', facts)
        self.assertEqual(sum(k.startswith('function:') for k in facts), 3)
        self.assertEqual(sum(k.startswith('trigger:') for k in facts), 6)
        self.assertEqual(sum(k.startswith('index:') for k in facts), 4)
        self.assertIn('column:releases.software_id', facts)
        self.assertIn('column:release_snapshots.content_hash', facts)
        self.assertEqual(facts['version']['column_type'], 'character varying(64)')

    def test_no_side_effecting_runtime_imports_or_commands(self):
        import ast
        tree = ast.parse(SCRIPT.read_text())
        allowed = {'hashlib', 'json', 'os', 'pathlib', 'stat', 'sys'}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertTrue(all(item.name in allowed for item in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertIn(node.module, allowed)
        result = subprocess.run([sys.executable, '-I', str(SCRIPT), '--help'], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b'No database', result.stdout)


    def test_source_columns_and_function_bodies_are_independently_derived(self):
        import ast
        import re
        source = ROOT / 'backend/alembic/versions/0029_changeover_batch_history.py'
        tree = ast.parse(source.read_text())
        upgrade = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'upgrade')
        facts = self.manifest['facts']
        tables = {}
        functions = {}
        for stmt in upgrade.body:
            if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
                continue
            call = stmt.value
            if not isinstance(call.func, ast.Attribute):
                continue
            if call.func.attr == 'create_table':
                table = ast.literal_eval(call.args[0])
                columns = {}
                for arg in call.args[1:]:
                    if not isinstance(arg, ast.Call) or arg.func.attr != 'Column':
                        continue
                    name = ast.literal_eval(arg.args[0])
                    options = {k.arg: k.value for k in arg.keywords}
                    kind = arg.args[1].func.attr
                    expected_type = {'UUID': 'uuid', 'Integer': 'integer', 'Text': 'text',
                                     'DateTime': 'timestamp with time zone', 'JSONB': 'jsonb'}.get(kind)
                    if kind == 'String':
                        expected_type = 'character varying(%d)' % ast.literal_eval(arg.args[1].args[0])
                    nullable = not ('primary_key' in options and ast.literal_eval(options['primary_key']))
                    if 'nullable' in options:
                        nullable = ast.literal_eval(options['nullable'])
                    columns[name] = (expected_type, nullable)
                tables[table] = columns
            if call.func.attr == 'execute':
                sql = ast.literal_eval(call.args[0])
                for name, body in re.findall(r'CREATE FUNCTION (\w+)\(\) RETURNS trigger(?:\s+LANGUAGE plpgsql)? AS \$\$(.*?)\$\$', sql, re.S):
                    functions[name] = hashlib.sha256(body.encode('utf-8')).hexdigest()
        self.assertEqual(len(tables), 4)
        for table, columns in tables.items():
            observed = {fact['name']: (fact['data_type'], fact['nullable'])
                        for key, fact in facts.items() if key.startswith('column:' + table + '.')}
            self.assertEqual(observed, columns)
        self.assertEqual(len(functions), 3)
        for name, digest in functions.items():
            self.assertEqual(facts['function:' + name]['body_sha256'], digest)

    def test_composite_predecessor_and_partial_unique_contracts(self):
        facts = self.manifest['facts']
        for prefix, table, target in (('changeover', 'changeover_corrections', 'changeover_id'),
                                      ('batch', 'batch_corrections', 'batch_id')):
            fk = facts['constraint:' + table + '.fk_' + prefix + '_corr_predecessor']
            self.assertEqual(fk['columns'], [target, 'predecessor_id'])
            self.assertEqual(fk['target_columns'], [target, 'id'])
            self.assertEqual(fk['target_table'], table)
            index = facts['index:ux_' + prefix + '_corr_single_successor']
            self.assertTrue(index['unique'])
            self.assertEqual(index['columns'], ['predecessor_id'])
            self.assertEqual(index['predicate'], 'predecessor_id IS NOT NULL')
        self.assertNotIn('constraint:releases.unique:software_id,release_type,version', facts)

    def test_hardlink_short_read_growth_and_uncertain_close_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'evidence.json'; path.write_text(json.dumps(self.document))
            alias = Path(tmp) / 'alias'; os.link(path, alias)
            self.assertEqual(self.m.check_file(str(path))['status'], 'UNKNOWN')
            alias.unlink()
            with mock.patch.object(self.m.os, 'read', return_value=b''):
                self.assertEqual(self.m.check_file(str(path))['status'], 'UNKNOWN')
            close = self.m.os.close
            closed = []
            def uncertain(fd):
                closed.append(fd)
                close(fd)
                raise OSError('SECRET_CLOSE')
            with mock.patch.object(self.m.os, 'close', side_effect=uncertain):
                result = self.m.check_file(str(path))
            self.assertEqual(result['status'], 'UNKNOWN')
            self.assertEqual(len(closed), len(set(closed)))
            self.assertNotIn('SECRET_CLOSE', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
