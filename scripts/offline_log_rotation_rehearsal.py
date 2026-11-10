#!/usr/bin/env python3
"""Opt-in synthetic stdout/stderr retention observation, never disk-bound proof.

Import, help and ordinary tests do not invoke Docker. Runtime needs separately
approved use of a reviewed already-local image and removal of this run's own
container/logs. No API, database, image acquisition or daemon configuration.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

import offline_api_startup_rehearsal as startup
import offline_readonly_preflight as preflight
from offline_database_rehearsal import Blocked, exact, require, strict_json

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'org.software-lifecycle.synthetic-log-rotation'
POLICY = {'driver': 'local', 'options': {'max-size': '10m', 'max-file': '3', 'compress': 'true'}}
LINE_COUNT, LINE_BYTES = 8192, 8192
LOG_LIMIT = 65 * 1024**2
TOTAL_SECONDS, CLEANUP_RESERVE = 240, 30
ENVIRONMENT = {'PATH': '/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin',
               'HOME': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1'}
SUCCESS = 'SYNTHETIC_LOG_RETENTION_OBSERVED_NOT_DISK_OR_DEPLOYMENT_ACCEPTANCE'
LIMITATIONS = ('Synthetic stdout/stderr only. No hard disk bound, measured compression, '
               'physical log-file count, restart/recreation retention, application, database, '
               'backup, physical host network isolation or company deployment acceptance. '
               'Caller-supplied image/source consistency is not provenance authentication.')
ERROR_CODES = frozenset('''ARGUMENTS_REJECTED POLICY_REJECTED JSON_REJECTED COMMAND_BOUNDS
COMMAND_TIMEOUT COMMAND_OUTPUT_LIMIT COMMAND_FAILED HOST_OVERRIDE_REJECTED HOST_PLATFORM_REJECTED
EXISTING_PYTHON_312_REQUIRED HOST_SPACE_REQUIRED SOURCE_REJECTED SOURCE_MISMATCH CHECKOUT_DIRTY
EXISTING_DOCKER_REQUIRED DAEMON_PLATFORM_REJECTED IMAGE_IDENTITY_REJECTED
CONTAINER_IDENTITY_REJECTED CREATE_ID_UNCERTAIN CREATE_COLLISION CREATE_FAILED START_FAILED
PROCESS_REJECTED SEED_REJECTED SEED_TIMEOUT TRIGGER_REJECTED LOGS_REJECTED
REHEARSAL_TIMEOUT CLEANUP_UNCERTAIN LOCAL_CLEANUP_UNCERTAIN REHEARSAL_FAILED'''.split())


def document(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 65536, 'JSON_REJECTED')
    result = strict_json(raw)
    require(type(result) in (dict, list), 'JSON_REJECTED')
    return result


def verify_policy():
    # Synthetic inputs, pure generation only. Do not read operator/company files.
    config = preflight.compose({'images': {'api': {'image_id': 'sha256:' + '0'*64},
                                         'web': {'image_id': 'sha256:' + '1'*64}}},
                               Path('/synthetic/not-opened.env'))
    require(all(exact(config['services'][service]['logging'], POLICY)
                for service in ('api', 'web')), 'POLICY_REJECTED')


def marker(token, stream, stage):
    require(type(token) is str and re.fullmatch('[0-9a-f]{32}', token) is not None
            and stream in ('O', 'E') and stage in ('BEGIN', 'END'), 'ARGUMENTS_REJECTED')
    return ('SLCROT1:' + token + ':' + stream + ':' + stage + '\n').encode('ascii')


def line(token, number):
    require(type(number) is int and 0 <= number < LINE_COUNT, 'ARGUMENTS_REJECTED')
    marker(token, 'O', 'BEGIN')
    prefix = ('SLCROT1:%s:%s:%04d:' % (token, 'O' if number % 2 == 0 else 'E', number)).encode()
    size = LINE_BYTES - len(prefix) - 1
    return prefix + hashlib.shake_256(prefix).hexdigest((size + 1)//2)[:size].encode() + b'\n'


# The generator has no app imports, files, sockets, input data or arbitrary code.
# SIGALRM bounds blocked output too; a lost parent cannot leave an infinite writer.
GENERATOR = '''import hashlib, os, signal, sys, time
token = sys.argv[1]
if len(token) != 32 or any(c not in '0123456789abcdef' for c in token): sys.exit(2)
ready = False
def go(_s, _f):
    global ready
    ready = True
def expired(_s, _f):
    raise TimeoutError()
def write(fd, data):
    while data:
        n = os.write(fd, data)
        if n <= 0: raise ValueError()
        data = data[n:]
def marker(stream, stage):
    return ('SLCROT1:' + token + ':' + stream + ':' + stage + '\\n').encode('ascii')
def main():
    signal.signal(signal.SIGUSR1, go)
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(120)
    write(1, marker('O', 'BEGIN'))
    write(2, marker('E', 'BEGIN'))
    end = time.monotonic() + 45
    while not ready:
        if time.monotonic() >= end: raise TimeoutError()
        time.sleep(.05)
    for n in range(8192):
        prefix = ('SLCROT1:%s:%s:%04d:' % (token, 'O' if n % 2 == 0 else 'E', n)).encode()
        size = 8192 - len(prefix) - 1
        data = prefix + hashlib.shake_256(prefix).hexdigest((size + 1)//2)[:size].encode() + b'\\n'
        write(1 if n % 2 == 0 else 2, data)
    write(1, marker('O', 'END'))
    write(2, marker('E', 'END'))
try:
    main()
except BaseException:
    sys.exit(2)
'''


def seed_visible(code, out, err, token):
    require(code == 0 and out in (b'', marker(token, 'O', 'BEGIN'))
            and err in (b'', marker(token, 'E', 'BEGIN')), 'SEED_REJECTED')
    return bool(out and err)


def verify_logs(code, out, err, token):
    require(code == 0 and type(out) is bytes and type(err) is bytes
            and len(out) + len(err) <= LOG_LIMIT, 'LOGS_REJECTED')
    counts = []
    for raw, stream, parity in ((out, 'O', 0), (err, 'E', 1)):
        end = marker(token, stream, 'END')
        require(raw.endswith(end) and len(raw) > len(end), 'LOGS_REJECTED')
        size = len(raw) - len(end)
        require(size % LINE_BYTES == 0, 'LOGS_REJECTED')
        count = size // LINE_BYTES
        require(1 <= count < LINE_COUNT//2, 'LOGS_REJECTED')
        first = LINE_COUNT - count * 2 + parity
        for index, number in enumerate(range(first, LINE_COUNT, 2)):
            require(raw[index*LINE_BYTES:(index+1)*LINE_BYTES] == line(token, number), 'LOGS_REJECTED')
        counts.append(count)
    return {'stdout_retained_lines': counts[0], 'stderr_retained_lines': counts[1],
            'oldest_markers_absent': True, 'latest_markers_present': True}


def capture(args, *, env, limit=65536, timeout=15):
    """Drain both pipes fairly, with a shared byte ceiling and finite deadline."""
    require(type(limit) is int and 1 <= limit <= LOG_LIMIT
            and type(timeout) in (int, float) and math.isfinite(timeout) and 0 < timeout <= TOTAL_SECONDS,
            'COMMAND_BOUNDS')
    deadline = time.monotonic() + timeout
    output, error = bytearray(), bytearray()
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=env, cwd=ROOT)
    try:
        with selectors.DefaultSelector() as select:
            for stream, target in ((process.stdout, output), (process.stderr, error)):
                os.set_blocking(stream.fileno(), False)
                select.register(stream, selectors.EVENT_READ, target)
            while select.get_map():
                remaining = deadline - time.monotonic()
                require(remaining > 0, 'COMMAND_TIMEOUT')
                for key, _ in select.select(min(remaining, .1)):
                    block = os.read(key.fileobj.fileno(), min(65536, limit + 1 - len(output) - len(error)))
                    if not block:
                        select.unregister(key.fileobj)
                    else:
                        key.data.extend(block)
                        require(len(output) + len(error) <= limit, 'COMMAND_OUTPUT_LIMIT')
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'COMMAND_TIMEOUT')
            try:
                code = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                raise Blocked('COMMAND_TIMEOUT') from None
        return code, bytes(output), bytes(error)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


class Container:
    # Reuse the established full-CID/no-symlink/fingerprint reader only, not its
    # API launch, environment, logger, process probes or lifecycle orchestration.
    record_cid = startup.Container.record_cid

    def __init__(self, root, child, token, image_id, commit, baked_env):
        marker(token, 'O', 'BEGIN')
        self.root, self.child, self.token = root, child, token
        self.image_id, self.commit = image_id, commit
        self.environment = baked_env | ENVIRONMENT
        self.name = 'slc-log-rotation-' + token
        self.cidfile = root / 'container.cid'
        self.cid = None
        self.attempted = self.cleanup_attempted = self.cleaned = self.triggered = False
        self.program_args = ['-I', '-B', '-u', '-c', GENERATOR, token]

    def required_host(self):
        return {'NetworkMode': 'none', 'PublishAllPorts': False, 'Privileged': False,
                'ReadonlyRootfs': True, 'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges'],
                'LogConfig': {'Type': POLICY['driver'], 'Config': POLICY['options'] | {'mode': 'blocking'}},
                'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0}, 'PidMode': '',
                'IpcMode': 'private', 'CgroupnsMode': 'private', 'Memory': 268435456,
                'MemorySwap': 268435456, 'NanoCpus': 1000000000, 'PidsLimit': 32, 'ShmSize': 8388608}

    def create_args(self):
        args = ['create', '--pull=never', '--platform=linux/amd64', '--name', self.name,
                '--cidfile', str(self.cidfile), '--label', LABEL + '=' + self.token,
                '--network=none', '--log-driver=local', '--read-only', '--user=65532:65532',
                '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=32',
                '--memory=256m', '--memory-swap=256m', '--cpus=1', '--shm-size=8m',
                '--ipc=private', '--cgroupns=private', '--restart=no', '--no-healthcheck',
                '--workdir=/app', '--entrypoint=/usr/local/bin/python']
        for key, value in (POLICY['options'] | {'mode': 'blocking'}).items():
            args += ['--log-opt', key + '=' + value]
        for key, value in ENVIRONMENT.items():
            args += ['--env', key + '=' + value]
        return args + [self.image_id, *self.program_args]

    def verify_identity(self, raw, expected=None):
        data = document(raw)
        require(type(data) is list and len(data) == 1 and type(data[0]) is dict, 'CONTAINER_IDENTITY_REJECTED')
        data = data[0]
        config, host, state = (data.get(key) for key in ('Config', 'HostConfig', 'State'))
        require(all(type(value) is dict for value in (config, host, state)), 'CONTAINER_IDENTITY_REJECTED')
        require(data.get('Id') == self.cid and data.get('Image') == self.image_id
                and data.get('Name') == '/' + self.name and config.get('Image') == self.image_id
                and type(config.get('Labels')) is dict and config['Labels'].get(LABEL) == self.token
                and config['Labels'].get('org.opencontainers.image.revision') == self.commit
                and data.get('Path') == '/usr/local/bin/python' and exact(data.get('Args'), self.program_args)
                and config.get('User') == '65532:65532' and config.get('WorkingDir') == '/app'
                and exact(config.get('Entrypoint'), ['/usr/local/bin/python'])
                and exact(config.get('Cmd'), self.program_args) and config.get('Volumes') in (None, {})
                and config.get('Tty') is False and config.get('OpenStdin') is False
                and exact(config.get('Healthcheck'), {'Test': ['NONE']}), 'CONTAINER_IDENTITY_REJECTED')
        require(exact(startup.environment(config.get('Env'), set(self.environment)), self.environment),
                'CONTAINER_IDENTITY_REJECTED')
        require(all(exact(host.get(key), value) for key, value in self.required_host().items())
                and host.get('Tmpfs') in (None, {}) and host.get('PortBindings') in (None, {})
                and all(host.get(key) in (None, []) for key in ('Binds', 'Mounts', 'VolumesFrom',
                    'CapAdd', 'Devices', 'DeviceRequests', 'DeviceCgroupRules'))
                and data.get('Mounts') == [], 'CONTAINER_IDENTITY_REJECTED')
        network = data.get('NetworkSettings')
        require(type(network) is dict and network.get('Ports') in (None, {})
                and type(network.get('Networks')) is dict and set(network['Networks']) == {'none'},
                'CONTAINER_IDENTITY_REJECTED')
        none = network['Networks']['none']
        require(type(none) is dict and all(none.get(key) == '' for key in
                ('IPAddress', 'GlobalIPv6Address', 'Gateway')), 'CONTAINER_IDENTITY_REJECTED')
        if expected is not None:
            require(state.get('Status') == expected and state.get('Running') is (expected == 'running')
                    and all(state.get(key) is False for key in ('Paused', 'Restarting', 'Dead', 'OOMKilled'))
                    and state.get('Error') == '', 'PROCESS_REJECTED')
            if expected == 'exited':
                require(type(state.get('ExitCode')) is int and state['ExitCode'] == 0, 'PROCESS_REJECTED')

    def inspect(self, expected=None):
        require(self.cid is not None, 'CREATE_ID_UNCERTAIN')
        code, out, err = self.child(['container', 'inspect', self.cid])
        require(code == 0 and not err, 'CONTAINER_IDENTITY_REJECTED')
        self.verify_identity(out, expected)

    def create(self):
        require(not self.attempted and not os.path.lexists(self.cidfile), 'CREATE_COLLISION')
        with (self.root / 'custody.json').open('x') as handle:
            os.chmod(handle.name, 0o600)
            json.dump({'name': self.name, 'label': LABEL, 'token': self.token,
                       'image_id': self.image_id, 'source_commit': self.commit}, handle)
        self.attempted = True
        try:
            code, out, err = self.child(self.create_args(), limit=1024)
        finally:
            self.record_cid()
        self.inspect('created')
        require(code == 0 and out.strip() == self.cid.encode() and not err, 'CREATE_FAILED')
        code, out, err = self.child(['start', self.cid], limit=1024)
        require(code == 0 and out.strip() == self.cid.encode() and not err, 'START_FAILED')
        self.inspect('running')

    def trigger(self):
        require(not self.triggered, 'TRIGGER_REJECTED')
        self.inspect('running')
        self.triggered = True
        code, out, err = self.child(['kill', '--signal=USR1', self.cid], limit=1024)
        require(code == 0 and out.strip() == self.cid.encode() and not err, 'TRIGGER_REJECTED')

    def cleanup(self):
        if not self.attempted or self.cleaned:
            return
        require(not self.cleanup_attempted and self.cid is not None, 'CLEANUP_UNCERTAIN')
        self.cleanup_attempted = True
        try:
            self.inspect()
            code, out, err = self.child(['rm', '--force', self.cid], limit=1024, timeout=10)
            require(code == 0 and out.strip() == self.cid.encode() and not err, 'CLEANUP_UNCERTAIN')
            self.cleaned = True
        except (Exception, KeyboardInterrupt):
            raise Blocked('CLEANUP_UNCERTAIN') from None


def run_rehearsal(image_id, source_commit):
    require(type(image_id) is str and re.fullmatch('sha256:[0-9a-f]{64}', image_id) is not None
            and type(source_commit) is str and re.fullmatch('[0-9a-f]{40}', source_commit) is not None,
            'ARGUMENTS_REJECTED')
    verify_policy()
    root = Path(tempfile.mkdtemp(prefix='slc-log-rotation-'))
    container, reason, cleanup_reason = None, None, None
    phase, observation = 'HOST', {}
    deadline = time.monotonic() + TOTAL_SECONDS
    cleanup_phase = False
    try:
        env, docker = startup.prepare_runtime(root, source_commit)
        def child(args, **kwargs):
            remaining = deadline - time.monotonic() - (0 if cleanup_phase else CLEANUP_RESERVE)
            require(remaining > 0, 'REHEARSAL_TIMEOUT')
            return capture([docker, '--host=unix:///var/run/docker.sock', *args], env=env,
                           **(kwargs | {'timeout': min(kwargs.get('timeout', 15), remaining)}))
        code, out, err = child(['info', '--format', '{{json .}}'])
        require(code == 0 and not err, 'COMMAND_FAILED')
        info = document(out)
        require(type(info) is dict and info.get('OSType') == 'linux'
                and info.get('Architecture') in ('amd64', 'x86_64'), 'DAEMON_PLATFORM_REJECTED')
        phase = 'IMAGE'
        code, out, err = child(['image', 'inspect', image_id])
        require(code == 0 and not err, 'IMAGE_IDENTITY_REJECTED')
        baked_env = startup.verify_image(out, image_id, source_commit)
        phase = 'CREATE'
        container = Container(root, child, uuid.uuid4().hex, image_id, source_commit, baked_env)
        container.create()
        phase = 'SEED'
        for _ in range(20):
            container.inspect('running')
            if seed_visible(*child(['logs', container.cid], limit=1024), container.token):
                break
            time.sleep(.1)
        else:
            raise Blocked('SEED_TIMEOUT')
        phase = 'EMIT'
        container.trigger()
        code, out, err = child(['wait', container.cid], limit=1024, timeout=125)
        require(code == 0 and out == b'0\n' and not err, 'PROCESS_REJECTED')
        container.inspect('exited')
        phase = 'LOGS'
        observation = verify_logs(*child(['logs', container.cid], limit=LOG_LIMIT, timeout=30), container.token)
        container.inspect('exited')
    except (Exception, KeyboardInterrupt) as error:
        reason = str(error) if isinstance(error, Blocked) and str(error) in ERROR_CODES else 'REHEARSAL_FAILED'
    finally:
        cleanup_phase = True
        if container is not None:
            try:
                container.cleanup()
            except (Exception, KeyboardInterrupt):
                cleanup_reason = 'CLEANUP_UNCERTAIN'
        if container is None or not container.attempted or container.cleaned:
            try:
                shutil.rmtree(root)
            except OSError:
                cleanup_reason = 'LOCAL_CLEANUP_UNCERTAIN'
        # Preserve private custody/CID on uncertainty; never lookup by name/prune.
    failed = reason or cleanup_reason
    result = {'status': 'BLOCKED' if failed else SUCCESS, 'phase': phase,
              'container_removed': bool(container is not None and container.cleaned),
              'hard_disk_bound_verified': False, 'compression_measured': False,
              'physical_rotation_files_verified': False, 'restart_retention_verified': False,
              'company_acceptance': False, 'limitations': LIMITATIONS}
    if failed:
        result['reason'] = failed
    if cleanup_reason:
        result['cleanup_reason'] = cleanup_reason
    if not failed:
        result.update(observation, image_id=image_id, source_commit=source_commit,
                      synthetic_data_bytes=LINE_COUNT * LINE_BYTES, source='docker_logs')
    return result, 2 if failed else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ['--help']:
        print('Usage: offline_log_rotation_rehearsal.py --run --image-id sha256:<64hex> '
              '--source-commit <40hex>\nSeparate runtime approval required. ' + LIMITATIONS)
        return 0
    if not (len(argv) == 5 and argv[0] == '--run' and argv[1] == '--image-id'
            and re.fullmatch('sha256:[0-9a-f]{64}', argv[2]) is not None
            and argv[3] == '--source-commit' and re.fullmatch('[0-9a-f]{40}', argv[4]) is not None):
        result, code = {'status': 'BLOCKED', 'reason': 'ARGUMENTS_REJECTED'}, 2
    else:
        previous = signal.getsignal(signal.SIGTERM)
        def interrupted(_signum, _frame):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, interrupted)
        try:
            try:
                result, code = run_rehearsal(argv[2], argv[4])
            except (Exception, KeyboardInterrupt):
                result, code = {'status': 'BLOCKED', 'reason': 'REHEARSAL_FAILED'}, 2
        finally:
            signal.signal(signal.SIGTERM, previous)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return code


if __name__ == '__main__':
    sys.exit(main())
