"""Private, bounded guard transport for the same-run migrated API coordinator.

No CLI, connection or process on import. prepare binds the reviewed local sources
and carries the exact checked collector bytes into a fixed in-container program.
The caller owns approval, the live API/PG containers, pipe, original Budget and
cleanup. Byte/receipt consistency is not provenance authentication, full schema,
function behavior, a SELECT-only role or deployment acceptance.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import re

import offline_migration_image_rehearsal as builder
import offline_pg_catalog_evidence as catalog
import offline_pg_guard_contracts as comparator
import offline_migration_schema_evidence as schema

Blocked = builder.Blocked
ROOT = Path(__file__).parent.parent
MAX_SOURCE = 65536
MAX_OUTPUT = 524288
ENTRY_RESERVE = 1330
FORMAT = 'slc-migrated-api-guard-observation-v1'
SOURCES = frozenset({
    'scripts/offline_migrated_api_guard.py', 'scripts/offline_pg_catalog_evidence.py',
    'scripts/offline_pg_guard_contracts.py', 'scripts/offline_migration_schema_evidence.py',
    'deploy/offline/migration-schema-0029.json',
})
_CHECKS = (
    'function:reject_changeover_batch_history_mutation',
    'function:guard_changeover_physical_write', 'function:guard_batch_physical_write',
    'trigger:changeover_baselines_append_only', 'trigger:changeover_corrections_append_only',
    'trigger:batch_baselines_append_only', 'trigger:batch_corrections_append_only',
    'trigger:changeover_physical_write_guard', 'trigger:batch_physical_write_guard',
)


def _require(condition):
    if not condition:
        raise Blocked('API_GUARD_REJECTED')


def expected_checks():
    """Fresh, deterministic receipt shape; never substitutes for a comparison."""
    return [{'check': name, 'matched': True} for name in _CHECKS]


# Executed by the caller with python -I -B -c inside its already-running API
# container. The source literal is filled only from bytes verified by prepare.
# stderr is suppressed by the caller; no raw exception/definition is logged here.
_BOOTSTRAP = '''import json, os, re, sys
COLLECTOR_SOURCE = %r
OPTIONS = ('-c default_transaction_read_only=on -c statement_timeout=5000 '
           '-c lock_timeout=1000 -c idle_in_transaction_session_timeout=15000')
def require(value):
    if not value: raise ValueError()
def main():
    require(len(sys.argv) == 2 and re.fullmatch(r'net:\\[[1-9][0-9]{0,19}\\]', sys.argv[1]))
    require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 65532)
    require(os.readlink('/proc/self/ns/net') == sys.argv[1])
    require(os.readlink('/proc/1/ns/net') == sys.argv[1])
    require(set(os.listdir('/sys/class/net')) == {'lo'})
    require({key: value for key, value in os.environ.items() if key.startswith('PG')} ==
            {'PGCONNECT_TIMEOUT': '5', 'PGOPTIONS': OPTIONS})
    namespace = {'__name__': 'slc_bound_catalog'}
    exec(compile(COLLECTOR_SOURCE, '<slc-bound-catalog>', 'exec'), namespace)
    import psycopg
    connection = None
    rolled_back = closed = False
    try:
        connection = psycopg.connect(host='127.0.0.1', hostaddr='127.0.0.1', port=5432,
            dbname='slc_migration', user='postgres', connect_timeout=5, password='',
            passfile='/dev/null', sslmode='disable', gssencmode='disable',
            channel_binding='disable', options=OPTIONS, autocommit=True)
        cursor = connection.cursor()
        try:
            cursor.execute('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            cursor.execute('SET LOCAL search_path = pg_catalog')
            cursor.execute('SET LOCAL statement_timeout = 5000')
            cursor.execute('SET LOCAL lock_timeout = 1000')
            cursor.execute('SET LOCAL idle_in_transaction_session_timeout = 15000')
        finally:
            cursor.close()
        observation = namespace['collect'](connection, 'public')
        require(type(observation['server_version_num']) is int and observation['server_version_num'] == 160015)
    finally:
        if connection is not None:
            try:
                connection.rollback()
                rolled_back = True
            finally:
                connection.close()
                closed = True
    require(rolled_back and closed)
    envelope = {'format': 'slc-migrated-api-guard-observation-v1',
                'rollback_completed': True, 'connection_closed': True, 'observation': observation}
    payload = json.dumps(envelope, ensure_ascii=True, separators=(',', ':')).encode('utf-8')
    require(0 < len(payload) <= 524288)
    sys.stdout.write(payload.decode('ascii'))
try:
    main()
except BaseException:
    sys.exit(2)
'''


def prepare(commit, budget):
    """Bind five sources without downloads; never reset the caller's Budget.

    Reads are non-following, regular-file-only and bounded. Git is hardened and
    shares the original deadline plus downstream admission reserve. Only the
    checked collector bytes are embedded, with no later collector-file reread.
    The existing host comparator still uses its unchanged SHA-bound manifest
    loader at comparison time. A concurrent change fails its fixed digest check.
    """
    try:
        _require(type(commit) is str and re.fullmatch('[0-9a-f]{40}', commit))
        _require(type(budget) is builder.Budget and type(budget.deadline) in (int, float)
                 and math.isfinite(budget.deadline))
        _require(ROOT.is_absolute() and __name__ == 'offline_migrated_api_guard'
                 and Path(__file__).absolute() == ROOT / 'scripts/offline_migrated_api_guard.py')
        for module, name in ((catalog, 'offline_pg_catalog_evidence'),
                             (comparator, 'offline_pg_guard_contracts'),
                             (schema, 'offline_migration_schema_evidence')):
            _require(module.__name__ == name and Path(module.__file__).absolute() == ROOT / ('scripts/' + name + '.py'))
        _require(comparator.catalog is catalog and comparator.schema is schema
                 and schema.MANIFEST_PATH == ROOT / 'deploy/offline/migration-schema-0029.json')
        deadline = budget.deadline
        def check():
            _require(budget.deadline == deadline)
            budget.reserve(ENTRY_RESERVE)
        env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': '/nonexistent',
               'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
               'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'}
        prefix = ['/usr/bin/git', '--no-pager', '--no-replace-objects', '--no-lazy-fetch',
                  '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null']
        checked = {}
        check()
        with builder.migration.directory(ROOT) as root_fd:
            for path in sorted(SOURCES):
                check()
                raw = builder.migration.bounded_command(prefix + ['show', commit + ':' + path],
                    env=env, cwd=f'/proc/self/fd/{root_fd}', pass_fds=(root_fd,),
                    limit=MAX_SOURCE, timeout=budget.allowance(20, ENTRY_RESERVE))
                check()
                local = builder.migration.read_at(root_fd, path, MAX_SOURCE)
                _require(type(raw) is bytes and 0 < len(raw) <= MAX_SOURCE and raw == local)
                checked[path] = local
                check()
            check()
        _require(hashlib.sha256(checked['deploy/offline/migration-schema-0029.json']).hexdigest()
                 == schema.MANIFEST_SHA256)
        program = _BOOTSTRAP % checked['scripts/offline_pg_catalog_evidence.py']
        _require(len(program.encode('utf-8')) <= MAX_SOURCE)
        check()
        return program
    except Exception:
        raise Blocked('API_GUARD_SOURCE_REJECTED') from None


def _pairs(items):
    value = {}
    for key, item in items:
        _require(key not in value)
        value[key] = item
    return value


def _reject_number(_value):
    raise Blocked('API_GUARD_REJECTED')


def _integer(value):
    _require(len(value) <= 10 and value.isascii() and value.isdigit())
    number = int(value)
    _require(number <= 2**32 - 1)
    return number


def _bounded(value, depth=0, budget=None):
    budget = [10000] if budget is None else budget
    budget[0] -= 1
    _require(depth <= 12 and budget[0] >= 0)
    kind = type(value)
    if kind is dict:
        _require(len(value) <= 32)
        for key, item in value.items():
            _bounded(key, depth + 1, budget)
            _bounded(item, depth + 1, budget)
    elif kind is list:
        _require(len(value) <= 512)
        for item in value:
            _bounded(item, depth + 1, budget)
    elif kind is str:
        _require(len(value.encode('utf-8')) <= catalog.MAX_TEXT and '\x00' not in value)
    elif kind is int:
        _require(0 <= value <= 2**32 - 1)
    else:
        _require(value is None or kind is bool)


def parse_and_check(raw):
    """Accept private pipe bytes only; return no definitions or body metadata.

    Strict transport decoding precedes the existing nine-contract comparator.
    Call only after prepare and a successful bounded exec in the caller-owned
    API container. An independently supplied envelope is not runtime evidence.
    """
    try:
        _require(type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT)
        envelope = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
            parse_float=_reject_number, parse_constant=_reject_number, parse_int=_integer)
        _bounded(envelope)
        _require(type(envelope) is dict and set(envelope) ==
                 {'format', 'rollback_completed', 'connection_closed', 'observation'})
        _require(envelope['format'] == FORMAT and envelope['rollback_completed'] is True
                 and envelope['connection_closed'] is True)
        observation = envelope['observation']
        _require(type(observation) is dict and type(observation.get('server_version_num')) is int
                 and observation['server_version_num'] == 160015)
        result = comparator.check_observation(observation, 'public')
        _require(builder.exact(result, comparator.report('GUARD_CONTRACT_MATCHED', expected_checks())))
        return {'namespace_oid': observation['namespace_oid'], 'server_version_num': 160015,
                'checks': copy.deepcopy(result['checks'])}
    except Exception:
        raise Blocked('API_GUARD_OBSERVATION_REJECTED') from None


def checked_pair(before, after):
    """Require both exact successful receipts for the same namespace/version."""
    try:
        for receipt in (before, after):
            _require(type(receipt) is dict and set(receipt) == {'namespace_oid', 'server_version_num', 'checks'})
            _require(type(receipt['namespace_oid']) is int and 1 <= receipt['namespace_oid'] <= 2**32 - 1
                     and type(receipt['server_version_num']) is int and receipt['server_version_num'] == 160015
                     and builder.exact(receipt['checks'], expected_checks()))
        _require(builder.exact(before, after))
        return copy.deepcopy(after['checks'])
    except Exception:
        raise Blocked('API_GUARD_PAIR_REJECTED') from None
