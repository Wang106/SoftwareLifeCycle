#!/usr/bin/env python3
"""Explicitly approved, local-image API process smoke with no database.

The caller must independently establish the reviewed local build's immutable
image ID and source commit before supplying them. Labels/CLI inputs are not
provenance authentication. Import, help and mock tests never invoke Docker.
"""
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import stat
import sys
import tempfile
import time
import uuid

from offline_database_rehearsal import Blocked, exact, require, run_child, strict_json
from offline_database_readiness import fingerprint

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'org.software-lifecycle.api-startup-rehearsal'
SUCCESS = 'API_PROCESS_SMOKE_PASSED_DATABASE_NOT_READY'
LIMITATIONS = ('Caller must independently trust the exact reviewed local build; image IDs and labels '
               'do not authenticate provenance. No database, migration, seed, real authentication, '
               'browser, physical host network isolation or company deployment acceptance.')
UVICORN_ARGS = ['-B', '-m', 'uvicorn', 'app.main:app', '--app-dir', '/app',
                '--host', '127.0.0.1', '--port', '8000', '--no-access-log', '--log-level', 'error']
TMPFS = {'/tmp': 'rw,noexec,nosuid,nodev,size=16777216,uid=65532,gid=65532,mode=0700'}
ENVIRONMENT = {
    'PATH': '/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin',
    'HOME': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': '/app',
    'DATABASE_URL': 'postgresql+psycopg://slc_unavailable@127.0.0.1:5432/slc_unavailable',
    'PGCONNECT_TIMEOUT': '2', 'PGOPTIONS': '-c default_transaction_read_only=on',
    'READ_ONLY_MODE': 'true', 'AUTH_MODE': 'disabled', 'ADMIN_OPERATOR_ENABLED': 'false',
    'SEED_ON_STARTUP': 'false', 'SEED_ZFI_DEMO': 'false',
    'REQUEST_TELEMETRY_ENABLED': 'false', 'REQUIRED_DB_REVISION': '0030_private_upload_sessions',
    'CORS_ORIGINS': 'http://127.0.0.1:3000',
}
SAFE_IMAGE_ENV = {'PATH', 'LANG', 'PYTHON_VERSION', 'PYTHON_SHA256', 'PYTHON_PIP_VERSION',
                  'PYTHON_SETUPTOOLS_VERSION', 'GPG_KEY'}
FORBIDDEN_HOST_ENV = ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH',
                      'DOCKER_API_VERSION')
COMMAND_PATH = '/api/v1/releases/00000000-0000-0000-0000-000000000001/create-snapshot'
CASES = {
    'health': ('GET', '/health', 200, {'status': 'ok', 'version': '0.18.50'}, False),
    'live': ('GET', '/health/live', 200, {'status': 'ok', 'version': '0.18.50'}, False),
    'ready_unavailable': ('GET', '/health/ready', 503,
                          {'status': 'not_ready', 'reason': 'database_unavailable'}, False),
    **{'write_' + method.lower(): (method, COMMAND_PATH, 403, {'detail': 'read_only_mode'}, False)
       for method in ('POST', 'PUT', 'PATCH', 'DELETE')},
    'identity_disabled': ('GET', '/api/v1/security/me', 401, {'detail': 'oidc_not_enabled'}, True),
    'session_disabled': ('POST', '/api/v1/security/me/browser-sessions', 401,
                          {'detail': 'oidc_not_enabled'}, True),
    'session_revoke_disabled': ('POST', '/api/v1/security/me/browser-sessions/'
                                '00000000-0000-0000-0000-000000000001/revoke', 401,
                                {'detail': 'oidc_not_enabled'}, True),
}
ERROR_CODES = frozenset('''ARGUMENTS_REJECTED SOURCE_REJECTED SOURCE_MISMATCH CHECKOUT_DIRTY
HOST_OVERRIDE_REJECTED HOST_PLATFORM_REJECTED EXISTING_PYTHON_312_REQUIRED HOST_SPACE_REQUIRED
EXISTING_DOCKER_REQUIRED DAEMON_PLATFORM_REJECTED COMMAND_FAILED COMMAND_TIMEOUT COMMAND_OUTPUT_LIMIT
COMMAND_INPUT_LIMIT COMMAND_BOUNDS JSON_REJECTED IMAGE_IDENTITY_REJECTED CONTAINER_IDENTITY_REJECTED
CREATE_ID_UNCERTAIN CREATE_COLLISION CREATE_FAILED START_FAILED PROCESS_REJECTED STARTUP_TIMEOUT
PROBE_REJECTED REHEARSAL_TIMEOUT CLEANUP_UNCERTAIN LOCAL_CLEANUP_UNCERTAIN REHEARSAL_FAILED'''.split())


def document(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 65536, 'JSON_REJECTED')
    return strict_json(raw)


def environment(values, allowed):
    require(type(values) is list, 'IMAGE_IDENTITY_REJECTED')
    result = {}
    for item in values:
        require(type(item) is str and len(item) <= 2048 and '=' in item
                and all(32 <= ord(character) <= 126 for character in item), 'IMAGE_IDENTITY_REJECTED')
        key, value = item.split('=', 1)
        require(key in allowed and key not in result, 'IMAGE_IDENTITY_REJECTED')
        result[key] = value
    return result


def verify_image(raw, image_id, commit):
    data = document(raw)
    require(type(data) is list and len(data) == 1 and type(data[0]) is dict, 'IMAGE_IDENTITY_REJECTED')
    data = data[0]
    config = data.get('Config')
    require(type(config) is dict and type(config.get('Labels')) is dict, 'IMAGE_IDENTITY_REJECTED')
    require(data.get('Id') == image_id and data.get('Os') == 'linux'
            and data.get('Architecture') == 'amd64' and not data.get('Variant')
            and config['Labels'].get('org.opencontainers.image.revision') == commit
            and config.get('User') == '65532:65532' and config.get('WorkingDir') == '/app'
            and exact(config.get('Entrypoint'), ['/bin/false']) and config.get('Cmd') in (None, [])
            and config.get('Volumes') in (None, {}) and config.get('Healthcheck') in (None, {})
            and config.get('OnBuild') in (None, []), 'IMAGE_IDENTITY_REJECTED')
    result = environment(config.get('Env'), SAFE_IMAGE_ENV)
    require(result.get('PYTHON_VERSION') == '3.12.14', 'IMAGE_IDENTITY_REJECTED')
    require('GPG_KEY' not in result or re.fullmatch('[0-9A-Fa-f]{40}', result['GPG_KEY']) is not None,
            'IMAGE_IDENTITY_REJECTED')
    return result


# Runs in a separate docker-exec Python process. No app imports, proxy, redirects
# or arbitrary target. Only the exact small receipt escapes the container.
PROBE_PROGRAM = '''import http.client, json, sys
CASES = json.loads(%r)
def pairs(items):
    result = {}
    for key, value in items:
        if key in result: raise ValueError()
        result[key] = value
    return result
def reject(_value): raise ValueError()
def exact(a, b):
    if type(a) is not type(b): return False
    if type(a) is dict: return set(a) == set(b) and all(exact(a[k], b[k]) for k in a)
    if type(a) is list: return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    return a == b
def main():
    name = sys.argv[1]
    method, path, status, expected, private = CASES[name]
    http.client._MAXHEADERS = 32
    http.client._MAXLINE = 4096
    connection = http.client.HTTPConnection('127.0.0.1', 8000, timeout=2)
    try:
        body = b'{}' if method not in ('GET', 'HEAD') else None
        connection.request(method, path, body=body, headers={'Accept': 'application/json',
            'Content-Type': 'application/json', 'Connection': 'close'})
        response = connection.getresponse()
        if type(response.status) is not int or response.status != status: raise ValueError()
        headers = pairs([(key.lower(), value) for key, value in response.getheaders()])
        if headers.get('content-type') != 'application/json': raise ValueError()
        if 'transfer-encoding' in headers or 'content-encoding' in headers or 'location' in headers: raise ValueError()
        length = headers.get('content-length', '')
        if not length.isascii() or not length.isdecimal() or not 1 <= int(length) <= 4096: raise ValueError()
        payload = response.read(4097)
        if len(payload) != int(length): raise ValueError()
        actual = json.loads(payload.decode('utf-8'), object_pairs_hook=pairs,
                            parse_float=reject, parse_constant=reject)
        if not exact(actual, expected): raise ValueError()
        if private:
            for key, value in {'cache-control': 'private, no-store', 'pragma': 'no-cache',
                               'vary': 'Authorization', 'www-authenticate': 'Bearer'}.items():
                if headers.get(key) != value: raise ValueError()
        print(json.dumps({'case': name, 'passed': True}, sort_keys=True))
    finally:
        connection.close()
try:
    main()
except BaseException:
    sys.exit(2)
''' % json.dumps(CASES)


PROCESS_PROGRAM = '''import json, sys
EXPECTED = json.loads(%r)
def read(path):
    with open(path, 'rb') as handle: data = handle.read(65537)
    if len(data) > 65536: raise ValueError()
    return data
def main():
    if read('/proc/1/cmdline').split(b'\\0') != [v.encode() for v in EXPECTED] + [b'']: raise ValueError()
    status = dict(line.split(':', 1) for line in read('/proc/1/status').decode().splitlines() if ':' in line)
    for key in ('Uid', 'Gid'):
        if status[key].split() != ['65532'] * 4: raise ValueError()
    for key in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'):
        if int(status[key], 16) != 0: raise ValueError()
    if status['NoNewPrivs'].strip() != '1' or status['Seccomp'].strip() != '2': raise ValueError()
    listeners = []
    for path in ('/proc/net/tcp', '/proc/net/tcp6'):
        for line in read(path).decode().splitlines()[1:]:
            fields = line.split()
            if len(fields) < 4: raise ValueError()
            if fields[3] == '0A': listeners.append((path, fields[1]))
    if listeners != [('/proc/net/tcp', '0100007F:1F40')]: raise ValueError()
    print(json.dumps({'process': 'pid1_uvicorn', 'loopback_only': True, 'nonroot': True}, sort_keys=True))
try:
    main()
except BaseException:
    sys.exit(2)
''' % json.dumps(['/usr/local/bin/python', *UVICORN_ARGS])


def verify_probe(name, code, raw):
    require(name in CASES and code == 0 and exact(document(raw), {'case': name, 'passed': True}),
            'PROBE_REJECTED')


class Container:
    # Fixed class contracts let the separate Web probe reuse CID custody and
    # isolation validation. API defaults and its public interface are unchanged.
    label = LABEL
    name_prefix = 'slc-api-startup-'
    runtime_environment = ENVIRONMENT
    executable = '/usr/local/bin/python'
    command = UVICORN_ARGS

    def __init__(self, root, child, token, image_id, commit, baked_env):
        require(re.fullmatch('[0-9a-f]{32}', token) is not None, 'ARGUMENTS_REJECTED')
        self.root, self.child, self.token = root, child, token
        self.image_id, self.commit = image_id, commit
        self.environment = baked_env | self.runtime_environment
        self.name = self.name_prefix + token
        self.cidfile = root / 'container.cid'
        self.cid = None
        self.pid = None
        self.attempted = self.cleanup_attempted = self.cleaned = False

    def create_args(self):
        args = ['create', '--pull=never', '--platform=linux/amd64', '--name', self.name,
                '--cidfile', str(self.cidfile), '--label', self.label + '=' + self.token,
                '--network=none', '--log-driver=none', '--read-only', '--user=65532:65532',
                '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=64',
                '--memory=512m', '--memory-swap=512m', '--cpus=1', '--shm-size=8m',
                '--ipc=private', '--cgroupns=private', '--restart=no', '--no-healthcheck',
                '--workdir=/app', '--entrypoint=' + self.executable]
        for path, options in TMPFS.items(): args += ['--tmpfs', path + ':' + options]
        for key, value in self.runtime_environment.items(): args += ['--env', key + '=' + value]
        return args + [self.image_id, *self.command]

    def record_cid(self):
        try:
            fd = os.open(self.cidfile, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                before = os.fstat(fd)
                require(stat.S_ISREG(before.st_mode) and before.st_size in (64, 65), 'CREATE_ID_UNCERTAIN')
                value = os.read(fd, 66).decode('ascii').removesuffix('\n')
                require(fingerprint(before) == fingerprint(os.fstat(fd)), 'CREATE_ID_UNCERTAIN')
            finally:
                os.close(fd)
            require(re.fullmatch('[0-9a-f]{64}', value) is not None
                    and self.cid in (None, value), 'CREATE_ID_UNCERTAIN')
            self.cid = value
        except (OSError, UnicodeError):
            raise Blocked('CREATE_ID_UNCERTAIN') from None

    def verify_identity(self, raw, running=False):
        data = document(raw)
        require(type(data) is list and len(data) == 1 and type(data[0]) is dict, 'CONTAINER_IDENTITY_REJECTED')
        data = data[0]
        config, host, state = data.get('Config'), data.get('HostConfig'), data.get('State')
        require(all(type(value) is dict for value in (config, host, state)), 'CONTAINER_IDENTITY_REJECTED')
        require(type(config.get('Labels')) is dict and data.get('Id') == self.cid
                and data.get('Image') == self.image_id and data.get('Name') == '/' + self.name
                and config.get('Image') == self.image_id and config['Labels'].get(self.label) == self.token
                and config['Labels'].get('org.opencontainers.image.revision') == self.commit
                and data.get('Path') == self.executable and exact(data.get('Args'), self.command)
                and config.get('User') == '65532:65532' and config.get('WorkingDir') == '/app'
                and exact(config.get('Entrypoint'), [self.executable])
                and exact(config.get('Cmd'), self.command) and config.get('Volumes') in (None, {})
                and exact(config.get('Healthcheck'), {'Test': ['NONE']}), 'CONTAINER_IDENTITY_REJECTED')
        require(exact(environment(config.get('Env'), set(self.environment)), self.environment),
                'CONTAINER_IDENTITY_REJECTED')
        required = {'NetworkMode': 'none', 'PublishAllPorts': False, 'Privileged': False,
                    'ReadonlyRootfs': True, 'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges'],
                    'Tmpfs': TMPFS, 'LogConfig': {'Type': 'none', 'Config': {}},
                    'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0}, 'PidMode': '',
                    'IpcMode': 'private', 'CgroupnsMode': 'private', 'Memory': 536870912,
                    'MemorySwap': 536870912, 'NanoCpus': 1000000000, 'PidsLimit': 64, 'ShmSize': 8388608}
        require(all(exact(host.get(key), value) for key, value in required.items()), 'CONTAINER_IDENTITY_REJECTED')
        require(host.get('PortBindings') in (None, {}) and all(host.get(key) in (None, []) for key in
                ('Binds', 'Mounts', 'VolumesFrom', 'CapAdd', 'Devices', 'DeviceRequests', 'DeviceCgroupRules')),
                'CONTAINER_IDENTITY_REJECTED')
        mounts = data.get('Mounts')
        require(type(mounts) is list and len(mounts) <= 1 and all(type(m) is dict and
                m.get('Type') == 'tmpfs' and m.get('Destination') == '/tmp' for m in mounts), 'CONTAINER_IDENTITY_REJECTED')
        network = data.get('NetworkSettings')
        require(type(network) is dict and network.get('Ports') in (None, {})
                and type(network.get('Networks')) is dict and set(network['Networks']) == {'none'},
                'CONTAINER_IDENTITY_REJECTED')
        none = network['Networks']['none']
        require(type(none) is dict and all(none.get(key) == '' for key in
                ('IPAddress', 'GlobalIPv6Address', 'Gateway')), 'CONTAINER_IDENTITY_REJECTED')
        if running:
            pid = state.get('Pid')
            require(state.get('Running') is True and state.get('Status') == 'running'
                    and all(state.get(key) is False for key in ('Paused', 'Restarting', 'Dead', 'OOMKilled'))
                    and type(pid) is int and pid > 0 and self.pid in (None, pid), 'PROCESS_REJECTED')
            self.pid = pid

    def inspect(self, running=False):
        require(self.cid is not None, 'CREATE_ID_UNCERTAIN')
        code, value = self.child(['container', 'inspect', self.cid])
        require(code == 0, 'CONTAINER_IDENTITY_REJECTED')
        self.verify_identity(value, running)

    def create(self):
        require(not self.attempted and not os.path.lexists(self.cidfile), 'CREATE_COLLISION')
        with (self.root / 'custody.json').open('x') as handle:
            os.chmod(handle.name, 0o600)
            json.dump({'name': self.name, 'label': self.label, 'token': self.token,
                       'image_id': self.image_id, 'source_commit': self.commit}, handle)
        self.attempted = True
        try:
            code, value = self.child(self.create_args(), limit=1024)
        finally:
            self.record_cid()
        self.inspect()
        require(code == 0 and value.strip() == self.cid.encode(), 'CREATE_FAILED')
        code, _ = self.child(['start', self.cid], limit=1024)
        require(code == 0, 'START_FAILED')
        self.inspect(running=True)

    def execute(self, program, *args):
        self.inspect(running=True)
        return self.child(['exec', '--user=65532:65532', self.cid,
                           '/usr/local/bin/python', '-I', '-B', '-c', program, *args],
                          limit=4096, timeout=8)

    def process_ready(self):
        # Bounded readiness observation only, never a repeated create/start or
        # write request. PID1 must remain the same through all subsequent checks.
        for _ in range(20):
            code, value = self.execute(PROCESS_PROGRAM)
            if code == 0:
                require(exact(document(value), {'process': 'pid1_uvicorn', 'loopback_only': True,
                                               'nonroot': True}), 'PROCESS_REJECTED')
                return
            require(code == 2 and value == b'', 'PROCESS_REJECTED')
            time.sleep(.5)
        raise Blocked('STARTUP_TIMEOUT')

    def cleanup(self):
        if not self.attempted or self.cleaned: return
        require(not self.cleanup_attempted and self.cid is not None, 'CLEANUP_UNCERTAIN')
        self.cleanup_attempted = True
        try:
            self.inspect()
            code, value = self.child(['rm', '--force', self.cid], limit=1024)
            require(code == 0 and value.strip() == self.cid.encode(), 'CLEANUP_UNCERTAIN')
            self.cleaned = True
        except (Exception, KeyboardInterrupt):
            raise Blocked('CLEANUP_UNCERTAIN') from None


def prepare_runtime(root, expected):
    require(not any(os.environ.get(key) for key in FORBIDDEN_HOST_ENV), 'HOST_OVERRIDE_REJECTED')
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64', 'HOST_PLATFORM_REJECTED')
    require(sys.version_info[:2] == (3, 12), 'EXISTING_PYTHON_312_REQUIRED')
    require(shutil.disk_usage(root).free >= 512 * 1024**2, 'HOST_SPACE_REQUIRED')
    config = root / 'docker-config'; config.mkdir(mode=0o700)
    env = {'PATH': os.defpath, 'HOME': str(root), 'DOCKER_CONFIG': str(config), 'LANG': 'C', 'LC_ALL': 'C'}
    git = ['git', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null']
    code, value = run_child([*git, 'rev-parse', 'HEAD'], env=env, limit=41)
    require(code == 0 and re.fullmatch(b'[0-9a-f]{40}\n', value) is not None, 'SOURCE_REJECTED')
    require(value.decode().strip() == expected, 'SOURCE_MISMATCH')
    code, value = run_child([*git, 'status', '--porcelain', '--untracked-files=all'], env=env)
    require(code == 0 and not value, 'CHECKOUT_DIRTY')
    docker = shutil.which('docker', path=env['PATH'])
    require(docker is not None, 'EXISTING_DOCKER_REQUIRED')
    return env, docker


def run_rehearsal(image_id, source_commit):
    require(type(image_id) is str and re.fullmatch('sha256:[0-9a-f]{64}', image_id) is not None
            and type(source_commit) is str and re.fullmatch('[0-9a-f]{40}', source_commit) is not None,
            'ARGUMENTS_REJECTED')
    root = Path(tempfile.mkdtemp(prefix='slc-api-startup-'))
    container = None
    completed = 0
    phase, reason = 'HOST', None
    deadline = time.monotonic() + 180
    try:
        env, docker = prepare_runtime(root, source_commit)
        def child(args, **kwargs):
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'REHEARSAL_TIMEOUT')
            return run_child([docker, '--host=unix:///var/run/docker.sock', *args], env=env,
                             **(kwargs | {'timeout': min(kwargs.get('timeout', 15), remaining)}))
        code, value = child(['info', '--format', '{{json .}}'])
        require(code == 0, 'COMMAND_FAILED')
        info = document(value)
        require(type(info) is dict and info.get('OSType') == 'linux'
                and info.get('Architecture') in ('amd64', 'x86_64'), 'DAEMON_PLATFORM_REJECTED')
        phase = 'IMAGE'
        code, value = child(['image', 'inspect', image_id])
        require(code == 0, 'IMAGE_IDENTITY_REJECTED')
        baked_env = verify_image(value, image_id, source_commit)
        phase = 'CREATE'
        container = Container(root, child, uuid.uuid4().hex, image_id, source_commit, baked_env)
        container.create()
        phase = 'PROCESS'
        container.process_ready()
        phase = 'PROBES'
        for name in CASES:
            code, value = container.execute(PROBE_PROGRAM, name)
            verify_probe(name, code, value)
            completed += 1
        phase = 'FINAL_PROCESS'
        code, value = container.execute(PROCESS_PROGRAM)
        require(code == 0 and exact(document(value), {'process': 'pid1_uvicorn', 'loopback_only': True,
                                                    'nonroot': True}), 'PROCESS_REJECTED')
    except (Exception, KeyboardInterrupt) as error:
        reason = str(error) if isinstance(error, Blocked) and str(error) in ERROR_CODES else 'REHEARSAL_FAILED'
    finally:
        if container is not None:
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
        # Preserve private custody/CID for uncertain outcomes. No prune, lookup
        # by name, repeated removal or arbitrary user-supplied container ID.
    result = {'status': 'BLOCKED' if reason else SUCCESS, 'phase': phase,
              'cases_passed': completed, 'cases_total': len(CASES),
              'container_removed': bool(container is not None and container.cleaned),
              'limitations': LIMITATIONS}
    if reason:
        result['reason'] = reason
    else:
        result.update(image_id=image_id, source_commit=source_commit, database_ready=False,
                      provenance='caller_supplied_trusted_build_consistency_only')
    return result, 2 if reason else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ['--help']:
        print('Usage: offline_api_startup_rehearsal.py --run --image-id sha256:<64hex> '
              '--source-commit <40hex>\nSeparate runtime approval required. ' + LIMITATIONS)
        return 0
    if not (len(argv) == 5 and argv[0] == '--run' and argv[1] == '--image-id'
            and re.fullmatch('sha256:[0-9a-f]{64}', argv[2]) is not None
            and argv[3] == '--source-commit' and re.fullmatch('[0-9a-f]{40}', argv[4]) is not None):
        result, code = {'status': 'BLOCKED', 'reason': 'ARGUMENTS_REJECTED', 'limitations': LIMITATIONS}, 2
    else:
        previous = signal.getsignal(signal.SIGTERM)
        def interrupted(_signum, _frame): raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, interrupted)
        try:
            try:
                result, code = run_rehearsal(argv[2], argv[4])
            except (Exception, KeyboardInterrupt):
                result, code = {'status': 'BLOCKED', 'reason': 'REHEARSAL_FAILED', 'limitations': LIMITATIONS}, 2
        finally:
            signal.signal(signal.SIGTERM, previous)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return code


if __name__ == '__main__':
    sys.exit(main())
