"""Synthetic evidence and static SQL contracts only; never connects to PostgreSQL."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/offline_database_readiness.py'
SPEC = importlib.util.spec_from_file_location('database_readiness', SCRIPT)
diag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diag)


def evidence():
    # Fabricated numbers, not a database observation or security attestation.
    return {
        'format': 'slc-offline-database-evidence-v1', 'server_version_num': 160000,
        'transaction_read_only': True, 'session_role_unchanged': True,
        'role_count': 1, 'role_superuser': False, 'role_create_db': False,
        'role_create_role': False, 'role_replication': False, 'role_bypass_rls': False,
        'role_membership_count': 0, 'owned_object_count': 0,
        'database_create': False, 'database_temp': False, 'schema_create_count': 0,
        'table_write_count': 0, 'column_write_count': 0, 'sequence_write_count': 0,
        'routine_execute_count': 0, 'unexpected_schema_count': 0,
        'unsupported_relation_count': 0, 'unsupported_type_count': 0,
        'unsupported_object_count': 0, 'large_object_count': 0, 'app_schema_count': 1,
        'migration_table_present': True, 'migration_table_supported': True,
        'migration_select_permitted': True, 'migration_row_count': 1,
        'migration_expected_head_count': 1,
    }


class DatabaseEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'evidence.json'
        self.path.write_text(json.dumps(evidence()))

    def check(self, changes=None):
        value = evidence()
        value.update(changes or {})
        return diag.check_bytes(json.dumps(value).encode())

    def test_synthetic_matching_checklist_is_not_acceptance(self):
        report = self.check()
        self.assertEqual(report['status'], 'CHECKLIST_MATCHED')
        self.assertIn('self-reported', report['limitations'])
        self.assertIn('forged', report['limitations'])
        self.assertNotIn('DATABASE_SAFE', json.dumps(report))
        self.assertNotIn('server_version_num', report)

    def test_each_dangerous_boolean_mismatches(self):
        for key in ('role_superuser', 'role_create_db', 'role_create_role',
                    'role_replication', 'role_bypass_rls', 'database_create', 'database_temp'):
            with self.subTest(key=key):
                self.assertEqual(self.check({key: True})['status'], 'CHECKLIST_MISMATCH')

    def test_each_dangerous_count_mismatches(self):
        for key in ('role_membership_count', 'owned_object_count', 'schema_create_count',
                    'table_write_count', 'column_write_count', 'sequence_write_count',
                    'routine_execute_count', 'unexpected_schema_count',
                    'unsupported_relation_count', 'unsupported_type_count', 'unsupported_object_count', 'large_object_count'):
            with self.subTest(key=key):
                self.assertEqual(self.check({key: 1})['status'], 'CHECKLIST_MISMATCH')

    def test_required_flags_and_counts_mismatch(self):
        for changes in ({'transaction_read_only': False}, {'session_role_unchanged': False},
                        {'role_count': 0}, {'role_count': 2}, {'app_schema_count': 0},
                        {'app_schema_count': 2}, {'server_version_num': 159999},
                        {'server_version_num': 170000}):
            with self.subTest(changes=changes):
                self.assertEqual(self.check(changes)['status'], 'CHECKLIST_MISMATCH')
        self.assertEqual(self.check({'server_version_num': 169999})['status'], 'CHECKLIST_MATCHED')

    def test_missing_wrong_multiple_migration_versions_mismatch(self):
        for rows, matching in ((0, 0), (1, 0), (2, 0), (2, 1), (2, 2)):
            with self.subTest(rows=rows, matching=matching):
                self.assertEqual(self.check({'migration_row_count': rows,
                    'migration_expected_head_count': matching})['status'], 'CHECKLIST_MISMATCH')

    def test_missing_unsupported_unreadable_migration_mismatch(self):
        for present, supported in ((False, False), (True, False), (True, True)):
            report = self.check({'migration_table_present': present,
                'migration_table_supported': supported, 'migration_select_permitted': False,
                'migration_row_count': None, 'migration_expected_head_count': None})
            self.assertEqual(report['status'], 'CHECKLIST_MISMATCH')

    def test_inconsistent_migration_is_unknown(self):
        for changes in ({'migration_table_present': False},
                        {'migration_table_supported': False},
                        {'migration_select_permitted': False},
                        {'migration_row_count': None}, {'migration_expected_head_count': None},
                        {'migration_row_count': 3}, {'migration_expected_head_count': 2},
                        {'migration_row_count': 0, 'migration_expected_head_count': 1}):
            with self.subTest(changes=changes):
                self.assertEqual(self.check(changes)['status'], 'UNKNOWN')

    def test_exact_fields_and_format_required(self):
        for key in evidence():
            value = evidence()
            del value[key]
            with self.subTest(key=key):
                self.assertEqual(diag.check_bytes(json.dumps(value).encode())['status'], 'UNKNOWN')
        for value in ({}, [], None, True, {'format': 'slc-offline-database-evidence-v2'},
                      dict(evidence(), extra='PRIVATE'), dict(evidence(), format=1)):
            self.assertEqual(diag.check_bytes(json.dumps(value).encode())['status'], 'UNKNOWN')

    def test_strict_types_all_fields(self):
        for key, baseline in evidence().items():
            if key == 'format':
                continue
            invalid = (None, '0', [], {}, 0, 1) if type(baseline) is bool else (
                True, False, None, '0', [], {}, -1, 1.0, 2**63)
            for value in invalid:
                with self.subTest(key=key, value=value):
                    self.assertEqual(self.check({key: value})['status'], 'UNKNOWN')

    def test_duplicate_nonfinite_overflow_and_malformed_rejected(self):
        valid = json.dumps(evidence())
        for payload in ('', ' ', 'null', valid + valid, '\ufeff' + valid,
                        valid[:-1] + ',"role_count":1}',
                        valid.replace('160000', 'NaN'), valid.replace('160000', 'Infinity'),
                        valid.replace('160000', '-Infinity'), valid.replace('160000', '1e9999'),
                        valid.replace('160000', '1.6e5'), '[' * 2000 + ']' * 2000,
                        '"' + 'x' * 20000 + '"'):
            with self.subTest(payload=payload[:30]):
                self.assertEqual(diag.check_bytes(payload.encode())['status'], 'UNKNOWN')
        self.assertEqual(diag.check_bytes(b'\xff')['status'], 'UNKNOWN')

    def test_byte_limit_and_exact_boundary(self):
        valid = json.dumps(evidence()).encode()
        self.assertEqual(diag.check_bytes(valid + b' ' * (diag.MAX_BYTES - len(valid)))['status'], 'CHECKLIST_MATCHED')
        self.assertEqual(diag.check_bytes(valid + b' ' * diag.MAX_BYTES)['status'], 'UNKNOWN')

    def test_local_file_and_cli(self):
        self.assertEqual(diag.check_file(str(self.path))['status'], 'CHECKLIST_MATCHED')
        result = subprocess.run([sys.executable, str(SCRIPT), '--evidence', str(self.path)],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['status'], 'CHECKLIST_MATCHED')
        self.assertEqual(result.stderr, '')

    def test_cli_mismatch_unknown_and_private_inputs(self):
        self.path.write_text(json.dumps(dict(evidence(), role_superuser=True)))
        for args, expected in ((['--evidence', str(self.path)], 1),
                               (['--evidence', '/PRIVATE/not-found'], 2),
                               (['--dsn', 'postgresql://PRIVATE'], 2),
                               (['--evidence', str(self.path), '--evidence', 'PRIVATE'], 2),
                               ([], 2)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = diag.main(args)
            self.assertEqual(code, expected)
            self.assertNotIn('PRIVATE', output.getvalue())

    def test_path_rejections_do_not_open(self):
        for path in ('relative.json', '/', '/tmp/../secret', '//tmp/file', '/tmp/./file',
                     '/tmp/file/', '/tmp/\x00', '/tmp/\n', '/tmp/\\file', '/' + 'x' * 4096):
            with self.subTest(path=path), patch.object(diag.os, 'open') as opened:
                self.assertEqual(diag.check_file(path)['status'], 'UNKNOWN')
                opened.assert_not_called()

    def test_symlinks_directory_fifo_missing_rejected(self):
        leaf = self.root / 'leaf'
        leaf.symlink_to(self.path)
        parent = self.root / 'parent'
        parent.symlink_to(self.root, target_is_directory=True)
        fifo = self.root / 'fifo'
        os.mkfifo(fifo)
        for path in (leaf, parent / self.path.name, self.root, fifo, self.root / 'missing'):
            with self.subTest(path=path):
                self.assertEqual(diag.check_file(str(path))['status'], 'UNKNOWN')

    def test_empty_oversize_file_is_not_read(self):
        for size in (0, diag.MAX_BYTES + 1):
            self.path.write_bytes(b' ' * size)
            with patch.object(diag.os, 'read', side_effect=AssertionError('must not read')):
                self.assertEqual(diag.check_file(str(self.path))['status'], 'UNKNOWN')

    def test_platform_capabilities_fail_closed(self):
        for name, value in (('O_NOFOLLOW', 0), ('O_DIRECTORY', None), ('O_NONBLOCK', 0),
                            ('supports_dir_fd', set())):
            with self.subTest(name=name), patch.object(diag.os, name, value):
                self.assertEqual(diag.check_file(str(self.path))['reason'], 'UNSUPPORTED_PLATFORM')

    def test_opened_file_is_pinned_after_path_replacement(self):
        original = os.read
        replaced = False
        observed = []
        def replacing(fd, size):
            nonlocal replaced
            if not replaced:
                self.path.rename(self.root / 'original')
                self.path.write_text(json.dumps(dict(evidence(), role_superuser=True)))
                replaced = True
            data = original(fd, size)
            observed.append(data)
            return data
        with patch.object(diag.os, 'read', side_effect=replacing):
            report = diag.check_file(str(self.path))
        self.assertEqual(json.loads(b''.join(observed)), evidence())
        # Some filesystems change ctime on rename: refusing it is conservative.
        self.assertIn(report['status'], ('CHECKLIST_MATCHED', 'UNKNOWN'))

    def test_mutation_during_read_rejected(self):
        original = os.read
        changed = False
        def modifying(fd, size):
            nonlocal changed
            data = original(fd, size)
            if not changed:
                self.path.write_bytes(b' ' * len(self.path.read_bytes()))
                changed = True
            return data
        with patch.object(diag.os, 'read', side_effect=modifying):
            self.assertEqual(diag.check_file(str(self.path))['status'], 'UNKNOWN')

    def test_safe_read_flags_and_fd_cleanup(self):
        original = os.open
        opened = []
        def tracking(name, flags, **kwargs):
            self.assertEqual(flags & os.O_ACCMODE, os.O_RDONLY)
            self.assertTrue(flags & os.O_NOFOLLOW)
            self.assertFalse(flags & (os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            fd = original(name, flags, **kwargs)
            opened.append(fd)
            return fd
        with patch.object(diag, 'supported', return_value=True), patch.object(diag.os, 'open', side_effect=tracking):
            self.assertEqual(diag.check_file(str(self.path))['status'], 'CHECKLIST_MATCHED')
        for fd in opened:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_read_failure_diagnostic_is_private_and_closes(self):
        with patch.object(diag.os, 'read', side_effect=OSError('PRIVATE credentials/path')):
            report = diag.check_file(str(self.path))
        self.assertEqual(report['status'], 'UNKNOWN')
        self.assertNotIn('PRIVATE', json.dumps(report))

    def test_no_driver_network_subprocess_or_environment_reads(self):
        source = SCRIPT.read_text()
        for token in ('psycopg', 'sqlalchemy', 'subprocess', 'socket', 'urllib', 'getenv', 'environ'):
            self.assertNotIn(token, source)

    def test_sql_static_transaction_and_fail_stop_contract(self):
        sql = (ROOT / 'deploy/offline/database-readiness.sql').read_text()
        self.assertIn('\\set ON_ERROR_STOP on', sql)
        self.assertIn('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;', sql)
        self.assertIn("SET LOCAL statement_timeout = '5s';", sql)
        self.assertIn("SET LOCAL lock_timeout = '1s';", sql)
        self.assertIn('SET LOCAL search_path = pg_catalog;', sql)
        self.assertLess(sql.index('ROLLBACK;'), sql.index('\\echo :readiness_document'))
        code = re.sub(r'--[^\n]*', '', sql)
        for token in ('INSERT INTO', 'UPDATE ', 'DELETE FROM', 'TRUNCATE ', 'CREATE ',
                      'ALTER ', 'DROP ', 'GRANT ', 'REVOKE ', 'COPY ', 'CALL ', 'DO ',
                      '\\connect', '\\c ', '\\!', '\\include', '\\i ', '\\o '):
            self.assertNotIn(token, code)

    def test_sql_static_privilege_coverage_and_guarded_version(self):
        sql = (ROOT / 'deploy/offline/database-readiness.sql').read_text()
        for token in ('pg_catalog.pg_auth_members', 'pg_catalog.pg_shdepend',
                      'pg_catalog.has_table_privilege', 'pg_catalog.has_column_privilege',
                      'pg_catalog.has_sequence_privilege', 'pg_catalog.has_function_privilege',
                      'pg_catalog.has_schema_privilege', 'pg_catalog.has_database_privilege',
                      'rolsuper', 'rolcreatedb', 'rolcreaterole', 'rolreplication', 'rolbypassrls',
                      "'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'",
                      "'INSERT,UPDATE,REFERENCES'", "'USAGE,UPDATE'", "'TEMP'",
                      'relrowsecurity', 'relforcerowsecurity', 'relhasrules', 'pg_catalog.pg_inherits',
                      'pg_catalog.pg_largeobject_metadata', '0029_changeover_batch_history'):
            self.assertIn(token, sql)
        guard = sql.index('\\if :readiness_migration_readable')
        read = sql.index('FROM ONLY public.alembic_version')
        self.assertLess(guard, read)
        self.assertIn('LIMIT 2', sql[read:])
        self.assertIn("a.atttypmod = 68", sql)
        for key in evidence():
            self.assertIn("'" + key + "'", sql)

    def test_sql_write_privileges_include_system_schema_relations(self):
        sql = (ROOT / 'deploy/offline/database-readiness.sql').read_text()
        for field, end in (('table_write_count', 'column_write_count'),
                           ('column_write_count', 'sequence_write_count'),
                           ('sequence_write_count', 'routine_execute_count')):
            section = sql.split("'" + field + "'", 1)[1].split("'" + end + "'", 1)[0]
            with self.subTest(field=field):
                self.assertIn('FROM pg_catalog.pg_class AS c', section)
                self.assertNotIn('FROM relations', section)
                self.assertIn('CASE WHEN c.relkind', section)
                self.assertIn('ELSE false END', section)

    def test_sql_migration_shape_rejects_custom_index_planning_paths(self):
        sql = (ROOT / 'deploy/offline/database-readiness.sql').read_text()
        shape = sql.split('migration_shape AS (', 1)[1].split('migration_access AS (', 1)[0]
        for token in ('pg_catalog.pg_index', 'pg_catalog.pg_opclass', "'btree'",
                      'indexprs IS NOT NULL', 'indpred IS NOT NULL', 'NOT i.indisvalid',
                      'NOT i.indisready', 'NOT i.indislive', 'opcnamespace'):
            with self.subTest(token=token):
                self.assertIn(token, shape)


if __name__ == '__main__':
    unittest.main()
