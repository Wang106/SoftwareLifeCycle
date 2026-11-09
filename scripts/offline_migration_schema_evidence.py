#!/usr/bin/env python3
"""Offline comparison of an untrusted, bounded schema projection. No DB access."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

MAX_BYTES = 262144
MAX_FACTS = 160
MAX_NODES = 10000
MAX_DEPTH = 12
MAX_STRING = 512
EVIDENCE_FORMAT = 'slc-offline-migration-schema-evidence-v1'
CHECKLIST = '0029-core-history-subset-v1'
MANIFEST_PATH = Path(__file__).resolve().parents[1] / 'deploy/offline/migration-schema-0029.json'
MANIFEST_SHA256 = '0eabda2f0f69fc3cb49d2fde23d9134f62a4acd4071a74a159083e53de67ec54'
LIMITATIONS = (
    'Offline comparison of untrusted, self-reported evidence for a fixed subset only. '
    'A fabricated or stale document can match. No database connection, collector, '
    'source authentication, freshness, migration execution, complete schema, function '
    'behavior, privilege isolation, application readiness or deployment is verified.'
)
HELP = ('Usage: offline_migration_schema_evidence.py --evidence ABSOLUTE_JSON_FILE\n'
        'No database is contacted. Fixed subset; self-reported JSON only.\n'
        'Exit 0: STRUCTURE_CHECKLIST_MATCHED; 1: STRUCTURE_CHECKLIST_MISMATCH; 2: UNKNOWN.\n')


class Rejected(ValueError):
    """Never preserve rejected values in user-visible errors."""


def report(status='UNKNOWN', reason='INPUT_REJECTED', checks=None):
    return {'format': 'slc-offline-migration-schema-check-v1',
            'checklist': CHECKLIST, 'status': status, 'reason': reason,
            'database_verified': False, 'checks': checks or [], 'limitations': LIMITATIONS}


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise Rejected()
        result[key] = value
    return result


def reject_number(_value):
    raise Rejected()


def bounded(value, depth=0, budget=None):
    budget = [MAX_NODES] if budget is None else budget
    budget[0] -= 1
    if depth > MAX_DEPTH or budget[0] < 0:
        raise Rejected()
    kind = type(value)
    if kind is dict:
        if len(value) > MAX_FACTS:
            raise Rejected()
        for key, item in value.items():
            bounded(key, depth + 1, budget)
            bounded(item, depth + 1, budget)
    elif kind is list:
        if len(value) > 32:
            raise Rejected()
        for item in value:
            bounded(item, depth + 1, budget)
    elif kind is str:
        if len(value) > MAX_STRING or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise Rejected()
    elif kind is int:
        if not 0 <= value <= 2**63 - 1:
            raise Rejected()
    elif value is not None and kind is not bool:
        raise Rejected()


def decode(payload):
    if type(payload) is not bytes or not 1 <= len(payload) <= MAX_BYTES:
        raise Rejected()
    value = json.loads(payload.decode('utf-8'), object_pairs_hook=pairs,
                       parse_float=reject_number, parse_constant=reject_number)
    bounded(value)
    return value


def shape(actual, expected):
    """Types and fields are exact. Ordered structural arrays are not sets."""
    if type(actual) is not type(expected):
        raise Rejected()
    if type(expected) is dict:
        if actual.keys() != expected.keys():
            raise Rejected()
        for key in expected:
            shape(actual[key], expected[key])
    elif type(expected) is list:
        # All current lists contain strings. Empty lists also reject objects/bools.
        if any(type(item) is not str for item in actual):
            raise Rejected()


def supported():
    return (os.name == 'posix'
            and all(isinstance(getattr(os, name, None), int) and getattr(os, name) != 0
                    for name in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK'))
            and os.open in getattr(os, 'supports_dir_fd', ()))


def valid_path(path):
    if type(path) is not str or not 2 <= len(path) <= 4096 or not path.startswith('/'):
        return False
    if '\\' in path or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in path):
        return False
    parts = path[1:].split('/')
    return len(parts) <= 256 and all(part not in ('', '.', '..') for part in parts)


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_file(path):
    """Read one opened ordinary file, never reopen it or follow path symlinks."""
    if not valid_path(path) or not supported():
        raise Rejected()
    base = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
    fd = os.open('/', base | os.O_DIRECTORY)
    try:
        for part in path[1:].split('/')[:-1]:
            child = os.open(part, base | os.O_DIRECTORY, dir_fd=fd)
            old, fd = fd, child
            os.close(old)  # Never retry an uncertain close.
        child = os.open(path.rsplit('/', 1)[1], base | os.O_NONBLOCK, dir_fd=fd)
        old, fd = fd, child
        os.close(old)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not 1 <= before.st_size <= MAX_BYTES):
            raise Rejected()
        data = bytearray()
        while len(data) <= before.st_size:
            block = os.read(fd, min(65536, before.st_size + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        if len(data) != before.st_size or fingerprint(before) != fingerprint(os.fstat(fd)):
            raise Rejected()
        return bytes(data)
    finally:
        os.close(fd)


def expected_facts():
    payload = read_file(str(MANIFEST_PATH))
    if hashlib.sha256(payload).hexdigest() != MANIFEST_SHA256:
        raise Rejected()
    manifest = decode(payload)
    keys = {'format', 'checklist', 'facts_baseline_commit', 'repository_file_sha256', 'facts'}
    paths = {'backend/alembic/env.py', 'backend/alembic/versions/0001_core_and_snapshot.py',
             'backend/alembic/versions/0024_release_customer_scope.py',
             'backend/alembic/versions/0029_changeover_batch_history.py'}
    if (type(manifest) is not dict or set(manifest) != keys
            or manifest['format'] != 'slc-offline-migration-schema-manifest-v2'
            or manifest['checklist'] != CHECKLIST
            or manifest['facts_baseline_commit'] != '44e307a71a22f93f8c2ae611cf10678b0420499f'
            or type(manifest['facts']) is not dict
            or type(manifest['repository_file_sha256']) is not dict
            or set(manifest['repository_file_sha256']) != paths):
        raise Rejected()
    for digest in manifest['repository_file_sha256'].values():
        if (type(digest) is not str or len(digest) != 64
                or any(char not in '0123456789abcdef' for char in digest)):
            raise Rejected()
    return manifest['facts']


def check_bytes(payload):
    try:
        value = decode(payload)
        if (type(value) is not dict or set(value) != {'format', 'checklist', 'facts'}
                or value['format'] != EVIDENCE_FORMAT or value['checklist'] != CHECKLIST
                or type(value['facts']) is not dict):
            raise Rejected()
        expected = expected_facts()
        actual = value['facts']
        if not actual.keys() <= expected.keys():
            raise Rejected()
        checks = []
        for key, fact in expected.items():
            if key in actual:
                shape(actual[key], fact)
            checks.append({'check': key, 'matched': key in actual and actual[key] == fact})
        matched = all(check['matched'] for check in checks)
        return report('STRUCTURE_CHECKLIST_MATCHED' if matched else 'STRUCTURE_CHECKLIST_MISMATCH',
                      'FIXED_SUBSET_COMPARED', checks)
    except (OSError, ValueError, TypeError, RecursionError, OverflowError, NotImplementedError):
        return report()


def check_file(path):
    if not valid_path(path):
        return report()
    if not supported():
        return report(reason='UNSUPPORTED_PLATFORM')
    try:
        return check_bytes(read_file(path))
    except (OSError, ValueError, TypeError, OverflowError, NotImplementedError):
        return report(reason='FILE_UNAVAILABLE')


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ['--help']:
        sys.stdout.write(HELP)
        return 0
    result = check_file(argv[1]) if len(argv) == 2 and argv[0] == '--evidence' else report()
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return {'STRUCTURE_CHECKLIST_MATCHED': 0, 'STRUCTURE_CHECKLIST_MISMATCH': 1, 'UNKNOWN': 2}[result['status']]


if __name__ == '__main__':
    sys.exit(main())
