#!/usr/bin/env python3
"""Compare a bounded local JSON document with a fixed, offline-only checklist."""
import json
import os
import stat
import sys

MAX_BYTES = 16384
MAX_INTEGER = 2**63 - 1
EVIDENCE_FORMAT = 'slc-offline-database-evidence-v1'
FALSE_FIELDS = (
    'role_superuser', 'role_create_db', 'role_create_role', 'role_replication',
    'role_bypass_rls', 'database_create', 'database_temp',
)
TRUE_FIELDS = ('transaction_read_only', 'session_role_unchanged',
               'migration_table_present', 'migration_table_supported',
               'migration_select_permitted')
ZERO_FIELDS = (
    'role_membership_count', 'owned_object_count', 'schema_create_count',
    'table_write_count', 'column_write_count', 'sequence_write_count',
    'routine_execute_count', 'unexpected_schema_count', 'unsupported_relation_count',
    'unsupported_type_count', 'unsupported_object_count', 'large_object_count',
)
ONE_FIELDS = ('role_count', 'app_schema_count')
MIGRATION_COUNTS = ('migration_row_count', 'migration_expected_head_count')
FIELDS = set(FALSE_FIELDS + TRUE_FIELDS + ZERO_FIELDS + ONE_FIELDS + MIGRATION_COUNTS) | {
    'format', 'server_version_num',
}
LIMITATIONS = (
    'Offline comparison of untrusted, self-reported evidence only. Evidence can be '
    'forged, stale or invalidated by concurrent changes. No database connection, '
    'source identity, collection exit status, freshness, privilege isolation, '
    'schema completeness, application readiness or deployment acceptance is verified.'
)
HELP = ('Usage: offline_database_readiness.py --evidence ABSOLUTE_JSON_FILE\n'
        'Offline evidence comparison only. No database is contacted.\n'
        'Exit 0: CHECKLIST_MATCHED; 1: CHECKLIST_MISMATCH; 2: UNKNOWN.\n')


class Rejected(ValueError):
    """Do not retain or expose rejected input in diagnostics."""


def report(status, reason, checks=None):
    return {'format': 'slc-offline-database-check-v1', 'status': status,
            'reason': reason, 'checks': checks or [], 'limitations': LIMITATIONS}


def unknown(reason='INPUT_REJECTED'):
    return report('UNKNOWN', reason)


def integer(value):
    return type(value) is int and 0 <= value <= MAX_INTEGER


def check_document(value):
    if (type(value) is not dict or set(value) != FIELDS
            or value['format'] != EVIDENCE_FORMAT
            or any(type(value[key]) is not bool for key in FALSE_FIELDS + TRUE_FIELDS)
            or any(not integer(value[key]) for key in ZERO_FIELDS + ONE_FIELDS + ('server_version_num',))):
        return unknown()
    present, supported_table, readable = (value[key] for key in (
        'migration_table_present', 'migration_table_supported', 'migration_select_permitted'))
    rows, matching = (value[key] for key in MIGRATION_COUNTS)
    if supported_table and not present or readable and not supported_table:
        return unknown()
    if readable:
        if not (integer(rows) and integer(matching) and matching <= rows <= 2):
            return unknown()
    elif rows is not None or matching is not None:
        return unknown()
    checks = []
    def add(name, matched):
        checks.append({'check': name, 'status': 'CHECKLIST_MATCHED' if matched else 'CHECKLIST_MISMATCH'})
    add('postgresql_16', 160000 <= value['server_version_num'] < 170000)
    for key in FALSE_FIELDS:
        add(key, not value[key])
    for key in TRUE_FIELDS:
        add(key, value[key])
    for key in ZERO_FIELDS:
        add(key, value[key] == 0)
    for key in ONE_FIELDS:
        add(key, value[key] == 1)
    add('migration_single_expected_head', readable and rows == matching == 1)
    matched = all(check['status'] == 'CHECKLIST_MATCHED' for check in checks)
    return report('CHECKLIST_MATCHED' if matched else 'CHECKLIST_MISMATCH', 'CHECKLIST_EVALUATED', checks)


def object_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise Rejected()
        value[key] = item
    return value


def reject_number(_value):
    # The schema has no floating-point fields, including finite exponent notation.
    raise Rejected()


def check_bytes(payload):
    if type(payload) is not bytes or not 1 <= len(payload) <= MAX_BYTES:
        return unknown()
    try:
        value = json.loads(payload.decode('utf-8'), object_pairs_hook=object_pairs,
                           parse_float=reject_number, parse_constant=reject_number)
        return check_document(value)
    except (ValueError, TypeError, RecursionError, OverflowError):
        return unknown()


def supported():
    return (os.name == 'posix'
            and all(isinstance(getattr(os, name, None), int) and getattr(os, name) != 0
                    for name in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK'))
            and os.open in getattr(os, 'supports_dir_fd', ()))


def valid_path(path):
    if type(path) is not str or not 2 <= len(path) <= 4096 or not path.startswith('/'):
        return False
    if '\\' in path or any(ord(c) < 32 or ord(c) == 127 for c in path):
        return False
    parts = path[1:].split('/')
    return len(parts) <= 256 and all(part not in ('', '.', '..') for part in parts)


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_file(path):
    """Pin each parent and the regular file; no path re-open, symlink or FIFO read."""
    base = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
    fd = os.open('/', base | os.O_DIRECTORY)
    try:
        for part in path[1:].split('/')[:-1]:
            child = os.open(part, base | os.O_DIRECTORY, dir_fd=fd)
            old, fd = fd, child
            os.close(old)
        child = os.open(path.rsplit('/', 1)[1], base | os.O_NONBLOCK, dir_fd=fd)
        old, fd = fd, child
        os.close(old)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= MAX_BYTES:
            raise Rejected()
        data = bytearray()
        # Reading one extra byte also rejects growth. No unbounded read/allocation.
        while len(data) <= before.st_size:
            block = os.read(fd, before.st_size + 1 - len(data))
            if not block:
                break
            data.extend(block)
        if len(data) != before.st_size or fingerprint(before) != fingerprint(os.fstat(fd)):
            raise Rejected()
        return bytes(data)
    finally:
        os.close(fd)


def check_file(path):
    if not valid_path(path):
        return unknown()
    if not supported():
        return unknown('UNSUPPORTED_PLATFORM')
    try:
        return check_bytes(read_file(path))
    except (OSError, ValueError, TypeError, OverflowError, NotImplementedError):
        return unknown('FILE_UNAVAILABLE')


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ['--help']:
        sys.stdout.write(HELP)
        return 0
    if len(argv) != 2 or argv[0] != '--evidence':
        result = unknown()
    else:
        result = check_file(argv[1])
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return {'CHECKLIST_MATCHED': 0, 'CHECKLIST_MISMATCH': 1, 'UNKNOWN': 2}[result['status']]


if __name__ == '__main__':
    sys.exit(main())
