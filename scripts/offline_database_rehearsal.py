#!/usr/bin/env python3
"""Opt-in, disposable synthetic PG16 collector rehearsal; not offline acceptance.

Import, help and ordinary tests never invoke Docker. Actual --run execution needs
separate approval covering image download, container isolation/local trust,
synthetic role/fixture changes and removal of this run's own container.
"""
import json
import os
from pathlib import Path
import platform
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

import offline_database_readiness as checker

ROOT = Path(__file__).resolve().parents[1]
# Official library/postgres, 16.15-bookworm, linux/amd64; verified metadata only
# on 2026-11-08. Manifest/config bytes were independently SHA256 checked.
IMAGE = 'postgres@sha256:5983db9a9c6ad225a48a46cfe2e03e6680b1826662befd0465eb05b34cb1c64e'
IMAGE_ID = 'sha256:cadebe7c08430c896edac883fa92f8de2c36e330805e770fbee8a7eae13f144f'
LABEL = 'org.software-lifecycle.synthetic-database-rehearsal'
MIN_FREE = 20 * 1024**3
FORBIDDEN_ENV = ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS_VERIFY',
                 'DOCKER_CERT_PATH', 'DOCKER_API_VERSION')
TMPFS = {
    '/var/lib/postgresql/data': 'rw,noexec,nosuid,nodev,size=536870912,uid=999,gid=999,mode=0700',
    '/var/run/postgresql': 'rw,noexec,nosuid,nodev,size=16777216,uid=999,gid=999,mode=0770',
    '/tmp': 'rw,noexec,nosuid,nodev,size=16777216,mode=1777',
}
ROLE_FLAGS = {'role_superuser': 'SUPERUSER', 'role_create_db': 'CREATEDB',
              'role_create_role': 'CREATEROLE', 'role_replication': 'REPLICATION',
              'role_bypass_rls': 'BYPASSRLS'}
CASES = ('baseline', 'table_write', 'column_write', 'membership', 'owner',
         *ROLE_FLAGS, 'wrong_head', 'multiple_heads', 'migration_view',
         'expression_index', 'partial_index', 'no_select', 'missing_table',
         'sequence_write', 'routine_execute', 'extra_schema', 'unsupported_type')
SUCCESS = 'SYNTHETIC_PG16_REHEARSAL_PASSED_NOT_OFFLINE_ACCEPTANCE'
LIMITATIONS = ('Synthetic disposable PostgreSQL only. No application, backup/restore, '
               'physical host network isolation, production security, operator approval '
               'or company deployment acceptance. PUBLIC defaults are not revoked.')


class Blocked(ValueError):
    """Messages are fixed local codes, never external command or SQL text."""


def require(condition, code='CONTRACT_REJECTED'):
    if not condition:
        raise Blocked(code)


def strict_json(raw):
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=checker.object_pairs,
                          parse_constant=checker.reject_number, parse_float=checker.reject_number)
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise Blocked('JSON_REJECTED') from None


def exact(a, b):
    # bool must not alias int, including deeply nested receipt fields.
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return set(a) == set(b) and all(exact(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    return a == b


def run_child(args, *, env, input=b'', limit=65536, timeout=30):
    """Bound stdin/stdout/time while discarding stderr, without shell or log files."""
    require(type(input) is bytes and len(input) <= 65536, 'COMMAND_INPUT_LIMIT')
    require(timeout > 0 and 1 <= limit <= 1024**2, 'COMMAND_BOUNDS')
    deadline = time.monotonic() + timeout
    output = bytearray()
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, env=env, cwd=ROOT)
    try:
        with selectors.DefaultSelector() as select:
            os.set_blocking(process.stdout.fileno(), False)
            select.register(process.stdout, selectors.EVENT_READ)
            if input:
                os.set_blocking(process.stdin.fileno(), False)
                select.register(process.stdin, selectors.EVENT_WRITE)
            else:
                process.stdin.close()
            offset = 0
            while select.get_map():
                remaining = deadline - time.monotonic()
                require(remaining > 0, 'COMMAND_TIMEOUT')
                for key, _ in select.select(min(remaining, .1)):
                    if key.fileobj is process.stdout:
                        block = os.read(process.stdout.fileno(), min(65536, limit + 1 - len(output)))
                        if not block:
                            select.unregister(process.stdout)
                        else:
                            output.extend(block)
                            require(len(output) <= limit, 'COMMAND_OUTPUT_LIMIT')
                    else:
                        try:
                            offset += os.write(process.stdin.fileno(), input[offset:offset + 4096])
                        except BrokenPipeError:
                            offset = len(input)
                        if offset == len(input):
                            select.unregister(process.stdin)
                            process.stdin.close()
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'COMMAND_TIMEOUT')
            try:
                code = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                raise Blocked('COMMAND_TIMEOUT') from None
        return code, bytes(output)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stdin.close()


def host_environment(root):
    require(not any(os.environ.get(key) for key in FORBIDDEN_ENV), 'HOST_OVERRIDE_REJECTED')
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64', 'HOST_PLATFORM_REJECTED')
    require(sys.version_info[:2] == (3, 12), 'EXISTING_PYTHON_312_REQUIRED')
    require(shutil.disk_usage(root).free >= MIN_FREE, 'HOST_SPACE_REQUIRED')
    # Empty private Docker config: no saved auth, plugins, alternate contexts or
    # user settings. No inherited PG*, GIT*, PYTHON* or credential environment.
    config = root / 'docker-config'
    config.mkdir(mode=0o700)
    return {'PATH': os.defpath, 'HOME': str(root), 'DOCKER_CONFIG': str(config),
            'LANG': 'C', 'LC_ALL': 'C'}


def verify_image(raw):
    data = strict_json(raw)
    require(type(data) is list and len(data) == 1 and type(data[0]) is dict, 'IMAGE_IDENTITY_REJECTED')
    data = data[0]
    require(data.get('Id') == IMAGE_ID and data.get('Os') == 'linux'
            and data.get('Architecture') == 'amd64'
            and type(data.get('RepoDigests')) is list and IMAGE in data['RepoDigests'], 'IMAGE_IDENTITY_REJECTED')


class Container:
    def __init__(self, root, child, token):
        require(re.fullmatch('[0-9a-f]{32}', token) is not None)
        self.root, self.child, self.token = root, child, token
        self.name = 'slc-pg16-' + token
        self.cidfile = root / 'container.cid'
        self.cid = None
        self.attempted = False
        self.cleanup_attempted = False
        self.cleaned = False

    def record_cid(self):
        try:
            fd = os.open(self.cidfile, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                before = os.fstat(fd)
                require(stat.S_ISREG(before.st_mode) and before.st_size in (64, 65), 'CREATE_ID_UNCERTAIN')
                raw = os.read(fd, 66)
                require(checker.fingerprint(before) == checker.fingerprint(os.fstat(fd)), 'CREATE_ID_UNCERTAIN')
            finally:
                os.close(fd)
            cid = raw.decode('ascii').removesuffix('\n')
            require(re.fullmatch('[0-9a-f]{64}', cid) is not None, 'CREATE_ID_UNCERTAIN')
            require(self.cid is None or self.cid == cid, 'CREATE_ID_UNCERTAIN')
            self.cid = cid
        except (OSError, UnicodeError):
            raise Blocked('CREATE_ID_UNCERTAIN') from None

    def verify_identity(self, raw):
        data = strict_json(raw)
        require(type(data) is list and len(data) == 1 and type(data[0]) is dict, 'CONTAINER_IDENTITY_REJECTED')
        data = data[0]
        config, host = data.get('Config', {}), data.get('HostConfig', {})
        require(type(config) is dict and type(host) is dict, 'CONTAINER_IDENTITY_REJECTED')
        require(data.get('Id') == self.cid and data.get('Image') == IMAGE_ID
                and data.get('Name') == '/' + self.name and config.get('Image') == IMAGE
                and config.get('Labels', {}).get(LABEL) == self.token,
                'CONTAINER_IDENTITY_REJECTED')
        require(host.get('NetworkMode') == 'none' and host.get('PortBindings') in (None, {})
                and host.get('PublishAllPorts') is False and host.get('Binds') in (None, [])
                and host.get('Privileged') is False and host.get('ReadonlyRootfs') is True
                and exact(host.get('Tmpfs'), TMPFS), 'CONTAINER_IDENTITY_REJECTED')
        mounts = data.get('Mounts')
        require(type(mounts) is list and all(type(m) is dict and m.get('Type') == 'tmpfs'
                and m.get('Destination') in TMPFS for m in mounts), 'CONTAINER_IDENTITY_REJECTED')

    def inspect(self):
        require(self.cid is not None, 'CREATE_ID_UNCERTAIN')
        code, raw = self.child(['container', 'inspect', self.cid], limit=65536)
        require(code == 0, 'CONTAINER_IDENTITY_UNCERTAIN')
        self.verify_identity(raw)

    def create(self):
        require(not self.attempted and not os.path.lexists(self.cidfile), 'CREATE_COLLISION')
        with (self.root / 'custody.json').open('x') as handle:
            os.chmod(handle.name, 0o600)
            json.dump({'name': self.name, 'label': LABEL, 'token': self.token, 'image': IMAGE}, handle)
        self.attempted = True
        args = ['create', '--pull=never', '--platform=linux/amd64', '--name', self.name,
                '--cidfile', str(self.cidfile), '--label', LABEL + '=' + self.token,
                '--network=none', '--log-driver=none', '--read-only', '--user=postgres',
                '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=128',
                '--memory=1g', '--cpus=1', '--shm-size=64m',
                '--env=POSTGRES_HOST_AUTH_METHOD=trust',
                '--env=POSTGRES_INITDB_ARGS=--auth-local=trust --auth-host=reject']
        for path, options in TMPFS.items():
            args += ['--tmpfs', path + ':' + options]
        args += [IMAGE, 'postgres', '-c', 'listen_addresses=', '-c',
                 'unix_socket_directories=/var/run/postgresql', '-c', 'max_connections=10',
                 '-c', 'shared_buffers=32MB']
        try:
            code, raw = self.child(args, limit=1024, timeout=30)
        finally:
            # Record the full newly-created ID even when the client failed after
            # creation. Never find a container by name or use an external ID.
            self.record_cid()
        self.inspect()
        require(code == 0 and raw.strip() == self.cid.encode(), 'CREATE_FAILED')
        code, _ = self.child(['start', self.cid], limit=1024)
        require(code == 0, 'START_FAILED')

    def cleanup(self):
        if not self.attempted or self.cleaned:
            return
        require(not self.cleanup_attempted and self.cid is not None, 'CLEANUP_UNCERTAIN')
        self.cleanup_attempted = True
        try:
            self.inspect()
            code, raw = self.child(['rm', '--force', self.cid], limit=1024, timeout=30)
            require(code == 0 and raw.strip() == self.cid.encode(), 'CLEANUP_UNCERTAIN')
            self.cleaned = True
        except (Exception, KeyboardInterrupt):
            raise Blocked('CLEANUP_UNCERTAIN') from None


def known_case(case):
    require(type(case) is str and case in CASES, 'CASE_REJECTED')
    return 'slc_' + case


def fixture_sql(case):
    role = known_case(case)
    flags = ROLE_FLAGS.get(case, '')
    sql = ("SET statement_timeout = '5s';\n" +
           f'CREATE ROLE {role} NOLOGIN {flags};\n' +
           'CREATE TABLE public.fixture (id INTEGER, value TEXT);\n')
    if case == 'migration_view':
        sql += "CREATE VIEW public.alembic_version AS SELECT '0029_changeover_batch_history'::VARCHAR(64) AS version_num;\n"
    elif case != 'missing_table':
        sql += 'CREATE TABLE public.alembic_version (version_num VARCHAR(64) NOT NULL PRIMARY KEY);\n'
        head = 'not_the_expected_head' if case == 'wrong_head' else '0029_changeover_batch_history'
        sql += f"INSERT INTO public.alembic_version VALUES ('{head}');\n"
        if case == 'multiple_heads':
            sql += "INSERT INTO public.alembic_version VALUES ('another_head');\n"
    if case not in ('no_select', 'missing_table'):
        sql += f'GRANT SELECT ON public.alembic_version TO {role};\n'
    additions = {
        'table_write': f'GRANT INSERT ON public.fixture TO {role};',
        'column_write': f'GRANT UPDATE(value) ON public.fixture TO {role};',
        'membership': f'CREATE ROLE slc_member_parent NOLOGIN; GRANT slc_member_parent TO {role};',
        'owner': f'ALTER TABLE public.fixture OWNER TO {role};',
        'expression_index': 'CREATE INDEX fixture_expression ON public.alembic_version (lower(version_num));',
        'partial_index': "CREATE INDEX fixture_partial ON public.alembic_version (version_num) WHERE version_num <> '';",
        'sequence_write': f'CREATE SEQUENCE public.fixture_sequence; GRANT USAGE ON public.fixture_sequence TO {role};',
        'routine_execute': 'CREATE FUNCTION public.fixture_function() RETURNS INTEGER LANGUAGE sql AS $$ SELECT 1 $$;',
        'extra_schema': 'CREATE SCHEMA fixture_schema;',
        'unsupported_type': "CREATE TYPE public.fixture_enum AS ENUM ('synthetic');",
    }
    return sql + additions.get(case, '') + '\n'


def psql_args(cid, case=None):
    require(re.fullmatch('[0-9a-f]{64}', cid) is not None)
    database = known_case(case) if case is not None else 'postgres'
    return ['exec', '--interactive', '--user=postgres', '--env=PGCONNECT_TIMEOUT=5', cid, 'psql', '--no-psqlrc',
            '--quiet', '--tuples-only', '--no-align', '--no-password',
            '--set=ON_ERROR_STOP=1', '--host=/var/run/postgresql',
            '--username=postgres', '--dbname=' + database, '--file=-']


def collector_sql(case):
    # A NEW connection is made for every case. The synthetic NOLOGIN subject is
    # both SESSION_USER and CURRENT_USER before the unchanged collector begins.
    # This is not authenticating a production read-only account.
    return 'SET SESSION AUTHORIZATION ' + known_case(case) + ';\n' + (ROOT / 'deploy/offline/database-readiness.sql').read_text()


def collect_document(code, raw):
    require(code == 0, 'COLLECTOR_ERROR')
    result = checker.check_bytes(raw)
    require(result['status'] != 'UNKNOWN', 'COLLECTOR_DOCUMENT_REJECTED')
    return strict_json(raw)


def assert_case(case, value, baseline):
    known_case(case)
    require(checker.check_document(value)['status'] == 'CHECKLIST_MISMATCH', 'CASE_STATUS_REJECTED')
    # Exact typed schema is enforced above. Baseline system ACL counts are
    # observed, never assumed zero or ignored. Specific grants must add exactly
    # the expected table/column deltas even when PUBLIC already causes mismatch.
    common = {'transaction_read_only': True, 'session_role_unchanged': True,
              'role_count': 1, 'app_schema_count': 1, 'database_temp': True}
    require(value['server_version_num'] == 160015, 'SERVER_VERSION_REJECTED')
    expectations = {
        'baseline': dict(migration_table_present=True, migration_table_supported=True,
                         migration_select_permitted=True, migration_row_count=1,
                         migration_expected_head_count=1, role_membership_count=0,
                         owned_object_count=0, database_create=False,
                         schema_create_count=0, sequence_write_count=0,
                         routine_execute_count=0, unexpected_schema_count=0,
                         unsupported_relation_count=0, unsupported_type_count=0,
                         unsupported_object_count=0, large_object_count=0,
                         **{key: False for key in ROLE_FLAGS}),
        'table_write': {'table_write_count': baseline['table_write_count'] + 1,
                        'column_write_count': baseline['column_write_count'] + 2},
        'column_write': {'table_write_count': baseline['table_write_count'],
                         'column_write_count': baseline['column_write_count'] + 1},
        'membership': {'role_membership_count': 1},
        'owner': {'owned_object_count': 1, 'table_write_count': baseline['table_write_count'] + 1,
                  'column_write_count': baseline['column_write_count'] + 2},
        'wrong_head': {'migration_row_count': 1, 'migration_expected_head_count': 0},
        'multiple_heads': {'migration_row_count': 2, 'migration_expected_head_count': 1},
        'no_select': {'migration_table_supported': True, 'migration_select_permitted': False,
                      'migration_row_count': None, 'migration_expected_head_count': None},
        'missing_table': {'migration_table_present': False, 'migration_table_supported': False,
                          'migration_select_permitted': False, 'migration_row_count': None,
                          'migration_expected_head_count': None},
        'sequence_write': {'sequence_write_count': 1},
        'routine_execute': {'routine_execute_count': 1},
        'extra_schema': {'unexpected_schema_count': 1},
        'unsupported_type': {'unsupported_type_count': 2},
    }
    expectations.update({key: {key: True} for key in ROLE_FLAGS})
    for key in ('migration_view', 'expression_index', 'partial_index'):
        expectations[key] = {'migration_table_supported': False,
                             'migration_select_permitted': False,
                             'migration_row_count': None, 'migration_expected_head_count': None}
    expectations['migration_view']['unsupported_relation_count'] = 1
    require(baseline['table_write_count'] >= 1 and baseline['column_write_count'] >= 1,
            'BASELINE_PUBLIC_ACL_REJECTED')
    expected = baseline | common | expectations[case]
    if case == 'role_superuser':
        # Superuser access broadens the system catalog counts. Require that
        # broadening; do not pretend these are fixed ordinary-role ACL counts.
        expected['database_create'] = True
        for key in ('schema_create_count', 'table_write_count', 'column_write_count'):
            require(value[key] > baseline[key], 'CASE_FIELDS_REJECTED')
            expected[key] = value[key]
    require(exact(value, expected), 'CASE_FIELDS_REJECTED')


def verify_checker(code, raw, document):
    # Independently executed checker must return its entire exact report, not
    # merely contain a status substring or an arbitrary nonzero denial code.
    require(code == 1 and len(raw) <= 65536, 'CHECKER_ERROR')
    require(exact(strict_json(raw), checker.check_document(document)), 'CHECKER_RECEIPT_REJECTED')


def run_rehearsal():
    root = Path(tempfile.mkdtemp(prefix='slc-pg16-'))
    container = None
    completed = 0
    phase = 'HOST'
    reason = None
    source = None
    deadline = time.monotonic() + 1500
    try:
        env = host_environment(root)
        docker = shutil.which('docker', path=env['PATH'])
        require(docker is not None, 'EXISTING_DOCKER_REQUIRED')
        def docker_child(args, **kwargs):
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'REHEARSAL_TIMEOUT')
            return run_child([docker, '--context', 'default', *args], env=env,
                             **(kwargs | {'timeout': min(kwargs.get('timeout', 30), remaining)}))
        def checked(args, **kwargs):
            code, raw = docker_child(args, **kwargs)
            require(code == 0, 'COMMAND_FAILED')
            return raw
        contexts = strict_json(checked(['context', 'inspect', 'default']))
        require(type(contexts) is list and len(contexts) == 1
                and contexts[0]['Endpoints']['docker']['Host'] == 'unix:///var/run/docker.sock', 'LOCAL_DOCKER_REQUIRED')
        info = strict_json(checked(['info', '--format', '{{json .}}'], limit=1024**2))
        require(info.get('OSType') == 'linux' and info.get('Architecture') in ('amd64', 'x86_64'), 'DAEMON_PLATFORM_REJECTED')
        data_root = info.get('DockerRootDir')
        require(type(data_root) is str and data_root.startswith('/')
                and shutil.disk_usage(data_root).free >= MIN_FREE, 'DOCKER_SPACE_REQUIRED')
        code, raw = run_child(['git', 'rev-parse', 'HEAD'], env=env, limit=41)
        require(code == 0 and re.fullmatch(b'[0-9a-f]{40}\n', raw) is not None, 'SOURCE_REJECTED')
        source = raw.decode().strip()
        expected = os.environ.get('GITHUB_SHA')
        require(expected is None or expected == source, 'SOURCE_MISMATCH')
        phase = 'IMAGE'
        checked(['pull', '--platform=linux/amd64', IMAGE], limit=1024**2, timeout=300)
        verify_image(checked(['image', 'inspect', IMAGE], limit=65536))
        phase = 'CREATE'
        container = Container(root, docker_child, uuid.uuid4().hex)
        container.create()
        phase = 'STARTUP'
        # Readiness is bounded polling, not a retry of a fixture, collector or
        # uncertain mutation. The official entrypoint's initdb temp server can
        # answer early, so wait for final PID 1 postgres before using its socket.
        ready = False
        for _ in range(60):
            code, raw = docker_child(['exec', '--user=postgres', container.cid,
                                     'sh', '-c', 'test "$(cat /proc/1/comm)" = postgres && pg_isready -q -h /var/run/postgresql -U postgres -d postgres'], limit=1024, timeout=5)
            if code == 0:
                ready = True
                break
            time.sleep(1)
        require(ready, 'STARTUP_TIMEOUT')
        baseline = None
        for case in CASES:
            phase = 'FIXTURE'
            # CREATE DATABASE cannot run inside a transaction. Names and SQL
            # come only from the closed case list, not URLs/environment/CLI.
            checked(psql_args(container.cid), input=("SET statement_timeout = '5s';\nCREATE DATABASE " + known_case(case) + ' TEMPLATE template0;\n').encode())
            checked(psql_args(container.cid, case), input=fixture_sql(case).encode())
            phase = 'COLLECTOR'
            try:
                code, raw = docker_child(psql_args(container.cid, case), input=collector_sql(case).encode(), limit=checker.MAX_BYTES)
            except (Exception, KeyboardInterrupt):
                raise Blocked('COLLECTOR_ERROR') from None
            document = collect_document(code, raw)
            if baseline is None:
                baseline = document
            phase = 'ASSERTIONS'
            assert_case(case, document, baseline)
            path = root / (case + '.json')
            with path.open('xb') as handle:
                os.chmod(path, 0o600)
                handle.write(raw)
            phase = 'CHECKER'
            code, receipt = run_child([sys.executable, '-I', str(ROOT / 'scripts/offline_database_readiness.py'),
                                      '--evidence', str(path)], env=env, limit=65536)
            verify_checker(code, receipt, document)
            completed += 1
    except (Exception, KeyboardInterrupt) as error:
        reason = str(error) if isinstance(error, Blocked) else 'REHEARSAL_FAILED'
    finally:
        if container is not None:
            # Reserve an independent cleanup deadline, even after case timeout.
            deadline = time.monotonic() + 35
            try:
                container.cleanup()
            except (Exception, KeyboardInterrupt):
                reason = 'CLEANUP_UNCERTAIN'
        if container is None or not container.attempted or container.cleaned:
            try:
                shutil.rmtree(root)
            except OSError:
                reason = 'LOCAL_CLEANUP_UNCERTAIN'
        # An uncertain create/remove preserves private state for manual review.
        # Do not delete by name, scan other containers, prune, or retry removal.
    if reason is not None:
        return {'status': 'BLOCKED', 'reason': reason, 'phase': phase,
                'cases_passed': completed, 'cases_total': len(CASES), 'limitations': LIMITATIONS}, 2
    return {'status': SUCCESS, 'source_commit': source, 'image': IMAGE,
            'cases_passed': completed, 'cases_total': len(CASES),
            'checklist_mismatches': completed, 'container_removed': True,
            'limitations': LIMITATIONS}, 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ['--help']:
        print('Usage: offline_database_rehearsal.py --run\nSeparate explicit approval required. ' + LIMITATIONS)
        return 0
    if argv != ['--run']:
        result, code = {'status': 'BLOCKED', 'reason': 'RUN_REQUIRED', 'limitations': LIMITATIONS}, 2
    else:
        # SIGTERM gets the same one-attempt cleanup as Ctrl-C. Forced termination
        # or daemon failure can still leave state; never claim guaranteed cleanup.
        previous = signal.getsignal(signal.SIGTERM)
        def interrupted(_signum, _frame):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, interrupted)
        try:
            try:
                result, code = run_rehearsal()
            except (Exception, KeyboardInterrupt):
                result, code = {'status': 'BLOCKED', 'reason': 'REHEARSAL_FAILED', 'limitations': LIMITATIONS}, 2
        finally:
            signal.signal(signal.SIGTERM, previous)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return code


if __name__ == '__main__':
    sys.exit(main())
