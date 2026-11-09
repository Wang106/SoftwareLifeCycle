#!/usr/bin/env python3
"""Explicit connected migration-image preparation; never run Alembic or a DB.

Only --run performs approved downloads/builds/two fixed isolated containers.
No upload, image export, installer, retry, arbitrary target or resumable state.
Digests prove consistency, not publisher authenticity or hostile-host isolation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid

import offline_migration_context as migration
import offline_image_rehearsal as fetcher

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 'slc-offline-migration-image-rehearsal-v1'
SUCCESS = 'MIGRATION_IMAGE_SMOKE_PASSED_NOT_DATABASE_ACCEPTANCE'
MIN_FREE = 20 * 1024**3
MAX_TAR = migration.MAX_CONTEXT_BYTES + 8 * 1024**2
BUILD_SOURCES = frozenset({
    '.github/workflows/offline-migration-image-rehearsal.yml',
    'scripts/offline_migration_image_rehearsal.py', 'scripts/offline_migration_context.py',
    'scripts/offline_python_wheelhouse.py', 'scripts/offline_image_rehearsal.py',
    'scripts/offline_image_bundle.py', 'scripts/offline_readonly_preflight.py',
    'scripts/offline_npm_artifacts.py', 'scripts/offline_npm_inventory.py',
})
SAFE_ENV = frozenset({'PATH', 'LANG', 'PYTHON_VERSION', 'PYTHON_SHA256', 'PYTHON_PIP_VERSION',
                      'PYTHON_SETUPTOOLS_VERSION', 'GPG_KEY'})
FORBIDDEN_ENV = ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH',
                 'DOCKER_API_VERSION', 'BUILDX_BUILDER', 'BUILDKIT_HOST')
LABEL = 'org.software-lifecycle.migration-image-rehearsal'
TMPFS = {'/tmp': 'rw,noexec,nosuid,nodev,size=16777216,uid=65532,gid=65532,mode=0700'}
LIMITATIONS = ('Connected image preparation only; no Alembic command, SQL, database, application, '
               'physical host network isolation, backup/restore or company acceptance. '
               'Caller trusts the reviewed checkout and local daemon; hashes are not signatures. '
               'No hostile same-UID protection, exact base-layer bandwidth claim or retained download.')


class Blocked(ValueError):
    pass


def require(ok, code='MIGRATION_IMAGE_BLOCKED'):
    if not ok:
        raise Blocked(code)


def exact(a, b):
    if type(a) is not type(b): return False
    if type(a) is dict: return set(a) == set(b) and all(exact(a[k], b[k]) for k in a)
    if type(a) is list: return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    return a == b


def document(raw, *, array=False):
    try:
        require(type(raw) is bytes and 0 < len(raw) <= 65536)
        def reject(_): raise ValueError()
        value = json.loads(raw, object_pairs_hook=migration.wheels.unique_object,
                           parse_constant=reject, parse_float=reject)
        require(type(value) is (list if array else dict))
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise Blocked('JSON_REJECTED') from None


class Budget:
    def __init__(self, started):
        require(type(started) in (int, float) and 0 <= time.monotonic() - started < 3300, 'BUDGET_REJECTED')
        self.deadline = started + 3300

    @classmethod
    def from_environment(cls):
        stamp = os.environ.get('MIGRATION_REHEARSAL_STARTED_NS')
        if stamp is None: return cls(time.monotonic())
        require(re.fullmatch('[1-9][0-9]{0,19}', stamp) is not None, 'BUDGET_REJECTED')
        now = time.monotonic_ns()
        require(0 <= now - int(stamp) < 3300 * 10**9, 'BUDGET_REJECTED')
        return cls(int(stamp) / 10**9)

    def allowance(self, cap, reserve=0):
        available = self.deadline - time.monotonic() - 30 - reserve
        require(available > 0, 'BUDGET_EXHAUSTED')
        return min(cap, available)

    def reserve(self, seconds):
        require(self.deadline - time.monotonic() >= seconds + 30, 'BUDGET_EXHAUSTED')


def command(args, *, env, timeout, limit=65536, stdin=None, cwd=ROOT):
    """Bound output before accumulating; stderr is discarded, never published.

    Killing the CLI does not prove daemon-side build/pull work stopped. A timeout
    is an uncertain failure, never permission to repeat or prune daemon objects.
    """
    require(0 < timeout <= 3300 and type(limit) is int and 0 < limit <= 1024**2)
    process = subprocess.Popen(args, cwd=cwd, env=env, stdin=stdin or subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + timeout
    output = bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                require(time.monotonic() < deadline, 'COMMAND_TIMEOUT_UNCERTAIN')
                for key, _ in selector.select(min(.1, max(.001, deadline - time.monotonic()))):
                    block = os.read(key.fileobj.fileno(), min(65536, limit + 1 - len(output)))
                    if not block: selector.unregister(key.fileobj)
                    else:
                        output.extend(block)
                        require(len(output) <= limit, 'COMMAND_OUTPUT_LIMIT')
        require(time.monotonic() < deadline, 'COMMAND_TIMEOUT_UNCERTAIN')
        try: code = process.wait(timeout=max(.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired: raise Blocked('COMMAND_TIMEOUT_UNCERTAIN') from None
        return code, bytes(output)
    finally:
        if process.returncode is None:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait(timeout=2)
        process.stdout.close()


def source_inputs(commit):
    require(type(commit) is str and migration.HEX40.fullmatch(commit), 'SOURCE_REJECTED')
    sources = migration.snapshot(ROOT, commit)
    # Bind every imported fetch/context implementation, not just the recipe.
    with migration.directory(ROOT) as fd:
        records = migration.git_read(fd, ['ls-tree', '-r', '-z', commit, '--', *sorted(BUILD_SOURCES)])
        checked = set()
        for record in filter(None, records.split(b'\0')):
            header, raw_name = record.split(b'\t', 1)
            name = raw_name.decode()
            mode, kind, oid = header.split(b' ')
            require(name in BUILD_SOURCES and name not in checked and mode == b'100644' and kind == b'blob')
            require(migration.HEX40.fullmatch(oid.decode()))
            expected = migration.git_read(fd, ['cat-file', 'blob', oid.decode()], migration.MAX_SOURCE_FILE)
            # Workflow path intentionally contains a dot directory; read parent
            # descriptors separately instead of relaxing context path rules.
            require(migration.safe_read(ROOT / name, migration.MAX_SOURCE_FILE) == expected, 'BUILD_SOURCE_MISMATCH')
            checked.add(name)
        require(checked == BUILD_SOURCES, 'BUILD_SOURCE_MISSING')
        require(not migration.git_read(fd, ['status', '--porcelain', '--untracked-files=all']).strip())
        require(migration.git_read(fd, ['rev-parse', 'HEAD'], 128).decode().strip() == commit)
    modules = {'offline_migration_image_rehearsal': Path(__file__),
               **{name: Path(sys.modules[name].__file__) for name in (
                   'offline_migration_context', 'offline_python_wheelhouse', 'offline_image_rehearsal',
                   'offline_image_bundle', 'offline_readonly_preflight', 'offline_npm_artifacts', 'offline_npm_inventory')}}
    require(all(path.absolute() == ROOT / 'scripts' / (name + '.py') for name, path in modules.items()),
            'BUILD_TOOL_LOCATION_REJECTED')
    return sources, migration.validate_sources(sources)['inventory']


def source_report(commit):
    sources, inventory = source_inputs(commit)
    return {'source_commit': commit, 'requirements': sources['backend/requirements.txt'].decode('utf-8'),
            'inventory': inventory, 'expected': probe_expectations(sources, inventory)}


def source_child(commit, env, timeout):
    program = ('import json, sys; sys.path.insert(0, sys.argv[1]); '
               'import offline_migration_image_rehearsal as m; '
               'print(json.dumps(m.source_report(sys.argv[2]), sort_keys=True))')
    code, raw = command([sys.executable, '-I', '-B', '-c', program, str(ROOT / 'scripts'), commit],
                        env=env, timeout=timeout)
    require(code == 0, 'SOURCE_CHILD_FAILED')
    value = document(raw)
    require(set(value) == {'source_commit', 'requirements', 'inventory', 'expected'}
            and value['source_commit'] == commit and type(value['requirements']) is str,
            'SOURCE_RECEIPT_REJECTED')
    inventory, expected = value['inventory'], value['expected']
    migration.wheels.validate_manifest(inventory, value['requirements'].encode('utf-8'))
    require(len(inventory['artifacts']) == 30 and type(expected) is dict
            and set(expected) == {'files', 'versions'} and type(expected['files']) is dict
            and 0 < len(expected['files']) <= migration.MAX_SOURCE_FILES, 'SOURCE_RECEIPT_REJECTED')
    versions = {item['name']: item['version'] for item in inventory['artifacts']}
    require(exact(expected['versions'], versions), 'SOURCE_RECEIPT_REJECTED')
    files = expected['files']; total = 0
    require({'alembic.ini', 'alembic/env.py', 'app/core/config.py'} <= set(files)
            and len([name for name in files if name.startswith('alembic/versions/')]) == 29,
            'SOURCE_RECEIPT_REJECTED')
    for name, item in files.items():
        require(type(name) is str and (name.startswith(('app/', 'alembic/')) or name == 'alembic.ini')
                and migration.source_name('backend/' + name) and type(item) is dict
                and set(item) == {'sha256', 'size'} and type(item['size']) is int
                and 0 <= item['size'] <= migration.MAX_SOURCE_FILE and type(item['sha256']) is str
                and migration.HEX64.fullmatch(item['sha256']), 'SOURCE_RECEIPT_REJECTED')
        total += item['size']
    require(total <= migration.MAX_SOURCE_TOTAL, 'SOURCE_RECEIPT_REJECTED')
    return inventory, expected


def host(root, budget):
    require(sys.platform == 'linux' and platform.machine() == 'x86_64'
            and sys.version_info[:2] == (3, 12), 'HOST_PLATFORM_REJECTED')
    require(not any(key in os.environ for key in FORBIDDEN_ENV), 'HOST_OVERRIDE_REJECTED')
    fetcher.reject_inherited_proxy()
    require(shutil.disk_usage(root).free >= MIN_FREE, 'HOST_SPACE_REQUIRED')
    docker = shutil.which('docker', path=os.defpath)
    require(docker is not None, 'EXISTING_DOCKER_REQUIRED')
    config = root / 'docker-config'; config.mkdir(mode=0o700)
    env = {'PATH': os.defpath, 'HOME': str(root), 'DOCKER_CONFIG': str(config),
           'DOCKER_BUILDKIT': '1', 'LANG': 'C.UTF-8', 'PIP_CONFIG_FILE': '/dev/null'}
    prefix = [docker, '--host=unix:///var/run/docker.sock']
    def read(args):
        code, value = command(prefix + args, env=env, timeout=budget.allowance(30))
        require(code == 0, 'HOST_CAPABILITY_REJECTED')
        return value
    info = document(read(['info', '--format', '{{json .}}']))
    require(info.get('OSType') == 'linux' and info.get('Architecture') in ('amd64', 'x86_64'), 'DAEMON_REJECTED')
    location = info.get('DockerRootDir')
    require(type(location) is str and Path(location).is_absolute(), 'DAEMON_REJECTED')
    require(shutil.disk_usage(location).free >= MIN_FREE, 'HOST_SPACE_REQUIRED')
    read(['version', '--format', '{{json .}}'])
    help_text = read(['build', '--help']).decode('utf-8')
    for flag in ('iidfile', 'network', 'platform', 'pull', 'no-cache'):
        require(re.search(r'^\s+(?:-\w,\s+)?--' + flag + r'(?:\s|$)', help_text, re.M), 'BUILDKIT_CAPABILITY_REQUIRED')
    return prefix, env


def acquire_wheels(inventory, destination):
    # Caller validates the full exact-commit inventory before creating this dir.
    require(type(inventory) is dict and len(inventory['artifacts']) == 30)
    fetcher.reject_inherited_proxy()
    # Batches bound in-flight work after failure. No retry/mirror/fallback.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for offset in range(0, 30, 4):
            futures = [pool.submit(fetcher.fetch, item, destination, 'sha256')
                       for item in inventory['artifacts'][offset:offset + 4]]
            for future in futures: future.result()


def acquire_child(inventory, destination, env, timeout):
    # A separate process bounds the whole batch, including urllib reads and the
    # executor's wait for active threads. There is no exposed downloader CLI.
    program = ('import json, sys; sys.path.insert(0, sys.argv[1]); '
               'import offline_migration_image_rehearsal as m; '
               'm.acquire_wheels(json.loads(sys.argv[2]), m.Path(sys.argv[3]))')
    code, raw = command([sys.executable, '-I', '-B', '-c', program, str(ROOT / 'scripts'),
                         json.dumps(inventory, sort_keys=True), str(destination)],
                        env=env, timeout=timeout, limit=1024)
    require(code == 0 and raw == b'', 'WHEEL_ACQUISITION_FAILED')


def input_receipt(commit, digest, *, prepared):
    return {'status': 'MIGRATION_INPUTS_PREPARED_NOT_EXECUTED' if prepared else 'MIGRATION_INPUTS_VERIFIED_NOT_EXECUTED',
            'source_commit': commit, 'manifest_sha256': digest, 'migration_count': 29,
            'database_connected': False, 'image_built': False}


def validate_input_receipt(value, commit, *, prepared):
    require(type(value) is dict and type(value.get('manifest_sha256')) is str
            and migration.HEX64.fullmatch(value['manifest_sha256']), 'INPUT_RECEIPT_REJECTED')
    digest = value['manifest_sha256']
    require(exact(value, input_receipt(commit, digest, prepared=prepared)), 'INPUT_RECEIPT_REJECTED')
    return digest


def context_child(args, env, timeout):
    program = ('import sys; sys.path.insert(0, sys.argv[1]); '
               'import offline_migration_context as m; raise SystemExit(m.main(sys.argv[2:]))')
    code, raw = command([sys.executable, '-I', '-B', '-c', program, str(ROOT / 'scripts'), *args],
                        env=env, timeout=timeout)
    require(code == 0, 'CONTEXT_CHILD_FAILED')
    return document(raw)


def build_snapshot(context, commit, digest, target):
    """Copy only verified bytes into a new local tar; never build from a live dir.

    Recheck identities and hashes around copying. A private trusted runner is
    still required: this is not isolation from an attacker with the same UID.
    """
    migration.verify(context, commit, digest)
    with migration.directory(context) as fd:
        before = migration.inventory_tree(fd)
        raw = migration.read_at(fd, migration.MANIFEST, migration.MAX_MANIFEST)
        require(hashlib.sha256(raw).hexdigest() == digest, 'CONTEXT_DIGEST_MISMATCH')
        manifest = migration.json_value(raw)
        entries = manifest['files'] | {migration.MANIFEST: {'size_bytes': len(raw), 'sha256': digest}}
        with target.open('xb') as output:
            os.chmod(target, 0o600)
            with tarfile.open(fileobj=output, mode='w', format=tarfile.PAX_FORMAT) as archive:
                for name, item in sorted(entries.items()):
                    content = migration.read_at(fd, name, max(migration.MAX_SOURCE_FILE, migration.wheels.MAX_WHEEL))
                    require(len(content) == item['size_bytes'] and hashlib.sha256(content).hexdigest() == item['sha256'],
                            'CONTEXT_BYTES_CHANGED')
                    info = tarfile.TarInfo(name); info.size = len(content); info.mode = 0o644
                    archive.addfile(info, io.BytesIO(content))
                    require(output.tell() <= MAX_TAR, 'BUILD_INPUT_TOO_LARGE')
            require(output.tell() <= MAX_TAR, 'BUILD_INPUT_TOO_LARGE')
            output.flush(); os.fsync(output.fileno())
        require(migration.inventory_tree(fd) == before, 'CONTEXT_IDENTITY_CHANGED')
    migration.verify(context, commit, digest)
    with target.open('rb') as stream: result = hashlib.file_digest(stream, 'sha256').hexdigest()
    return result


def build_snapshot_child(context, commit, digest, target, env, timeout):
    program = ('import json, sys; sys.path.insert(0, sys.argv[1]); '
               'import offline_migration_image_rehearsal as m; '
               'value = m.build_snapshot(m.Path(sys.argv[2]), sys.argv[3], sys.argv[4], m.Path(sys.argv[5])); '
               "print(json.dumps({'source_commit': sys.argv[3], 'context_manifest_sha256': sys.argv[4], "
               "'build_context_sha256': value}, sort_keys=True))")
    code, raw = command([sys.executable, '-I', '-B', '-c', program, str(ROOT / 'scripts'),
                         str(context), commit, digest, str(target)], env=env, timeout=timeout)
    require(code == 0, 'BUILD_SNAPSHOT_CHILD_FAILED')
    value = document(raw)
    require(set(value) == {'source_commit', 'context_manifest_sha256', 'build_context_sha256'}
            and value['source_commit'] == commit and value['context_manifest_sha256'] == digest
            and type(value['build_context_sha256']) is str
            and migration.HEX64.fullmatch(value['build_context_sha256']), 'BUILD_SNAPSHOT_RECEIPT_REJECTED')
    return value['build_context_sha256']


def bounded_digest(stream, timeout):
    require(0 < timeout <= 120, 'HASH_BUDGET_REJECTED')
    deadline = time.monotonic() + timeout
    digest = hashlib.sha256(); size = 0
    while True:
        require(time.monotonic() < deadline, 'HASH_TIMEOUT')
        block = stream.read(1024**2)
        require(time.monotonic() < deadline, 'HASH_TIMEOUT')
        if not block: return digest.hexdigest()
        size += len(block)
        require(size <= MAX_TAR, 'BUILD_INPUT_TOO_LARGE')
        digest.update(block)


def environment(values):
    require(type(values) is list, 'IMAGE_ENV_REJECTED')
    result = {}
    for value in values:
        require(type(value) is str and len(value) <= 2048 and '=' in value
                and all(32 <= ord(c) <= 126 for c in value), 'IMAGE_ENV_REJECTED')
        key, value = value.split('=', 1)
        require(key in SAFE_ENV and key not in result, 'IMAGE_ENV_REJECTED')
        result[key] = value
    require(result.get('PYTHON_VERSION') == '3.12.14', 'IMAGE_ENV_REJECTED')
    require('GPG_KEY' not in result or re.fullmatch('[0-9A-Fa-f]{40}', result['GPG_KEY']), 'IMAGE_ENV_REJECTED')
    return result


def verify_image(data, image_id, commit):
    require(type(image_id) is str and re.fullmatch('sha256:[0-9a-f]{64}', image_id))
    require(type(data) is list and len(data) == 1 and type(data[0]) is dict, 'IMAGE_REJECTED')
    item = data[0]; config = item.get('Config')
    require(type(config) is dict and type(config.get('Labels')) is dict, 'IMAGE_REJECTED')
    require(item.get('Id') == image_id and item.get('Os') == 'linux' and item.get('Architecture') == 'amd64'
            and item.get('Variant') in (None, '') and config['Labels'].get('org.opencontainers.image.revision') == commit
            and config.get('User') == '65532:65532' and config.get('WorkingDir') == '/app'
            and exact(config.get('Entrypoint'), ['/bin/false']) and config.get('Cmd') in (None, [])
            and config.get('Volumes') in (None, {}) and config.get('ExposedPorts') in (None, {})
            and config.get('Healthcheck') in (None, {}) and config.get('OnBuild') in (None, []), 'IMAGE_REJECTED')
    return environment(config.get('Env'))


def probe_expectations(sources, inventory):
    files = {name[8:]: {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}
             for name, raw in sources.items() if name.startswith(('backend/app/', 'backend/alembic/'))
             or name == 'backend/alembic.ini'}
    return {'files': files, 'versions': {a['name']: a['version'] for a in inventory['artifacts']}}


PROBE = '''import ast, hashlib, importlib, importlib.metadata, importlib.util, json, os, pathlib, stat, subprocess, sys

def main():
    expected = json.loads(sys.argv[1])
    assert os.getuid() == os.getgid() == 65532 and sys.version_info[:3] == (3, 12, 14)
    for name, version in expected['versions'].items():
        assert importlib.metadata.version(name) == version
    for name in ('fastapi', 'uvicorn', 'sqlalchemy', 'psycopg', 'alembic', 'pydantic_settings', 'jwt',
                 'psycopg_binary._psycopg', 'cryptography.hazmat.bindings._rust', 'pydantic_core._pydantic_core',
                 '_cffi_backend', 'greenlet._greenlet', 'httptools.parser.parser', 'uvloop.loop',
                 'watchfiles._rust_notify', 'websockets.speedups', 'yaml._yaml', 'markupsafe._speedups',
                 'sqlalchemy.cyextension.collections'):
        importlib.import_module(name)
    import psycopg
    assert psycopg.pq.__impl__ == 'binary' and importlib.util.find_spec('alembic.__main__') is not None
    subprocess.run([sys.executable, '-I', '-m', 'pip', '--isolated', 'check'], check=True,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    files, directories = set(), set()
    for path in pathlib.Path('/app').rglob('*'):
        info = path.lstat(); name = path.relative_to('/app').as_posix()
        assert not path.is_symlink()
        if stat.S_ISDIR(info.st_mode): directories.add(name)
        else:
            assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            files.add(name)
    assert files == set(expected['files'])
    expected_directories = {str(parent) for name in files for parent in pathlib.PurePosixPath(name).parents if str(parent) != '.'}
    assert directories == expected_directories
    previous = None; count = 0
    for name, item in sorted(expected['files'].items()):
        path = pathlib.Path('/app') / name
        assert path.stat().st_size == item['size'] <= 4 * 1024**2
        raw = path.read_bytes()
        assert len(raw) == item['size'] and hashlib.sha256(raw).hexdigest() == item['sha256']
        if name.endswith('.py'): compile(raw, name, 'exec')
        if name.startswith('alembic/versions/'):
            declarations = {}
            for node in ast.parse(raw).body:
                targets = node.targets if isinstance(node, ast.Assign) else ([node.target] if isinstance(node, ast.AnnAssign) else [])
                for target in targets:
                    if isinstance(target, ast.Name) and target.id in ('revision', 'down_revision', 'branch_labels', 'depends_on'):
                        assert target.id not in declarations
                        declarations[target.id] = ast.literal_eval(node.value)
            assert declarations['revision'] == pathlib.Path(name).stem
            assert declarations['down_revision'] == previous
            assert declarations['branch_labels'] is None and declarations['depends_on'] is None
            previous = declarations['revision']; count += 1
    assert count == 29 and previous == '0029_changeover_batch_history'
    print(json.dumps({'status': 'MIGRATION_DEPENDENCIES_AND_SOURCE_VERIFIED', 'wheel_count': 30,
                      'migration_count': 29, 'source_file_count': len(files), 'database_connected': False,
                      'migrations_executed': False}, sort_keys=True))
try:
    main()
except BaseException:
    raise SystemExit(2) from None
'''


class Container:
    def __init__(self, root, child, image_id, commit, baked, kind, expected):
        require(kind in ('default', 'dependencies'))
        self.root, self.child, self.image_id, self.commit = root, child, image_id, commit
        self.kind, self.expected = kind, expected
        self.token = uuid.uuid4().hex; self.name = 'slc-migration-' + self.token
        self.cidfile = root / (kind + '.cid'); self.cid = None
        self.attempted = self.cleanup_attempted = self.cleaned = False
        self.env = environment(baked) | {'HOME': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1'}
        encoded = json.dumps(expected, sort_keys=True, separators=(',', ':'))
        require(len(encoded.encode()) <= 32768)
        self.args = [] if kind == 'default' else ['-I', '-B', '-c', PROBE, encoded]
        self.entrypoint = '/bin/false' if kind == 'default' else '/usr/local/bin/python'

    def create_args(self):
        args = ['create', '--cidfile', str(self.cidfile), '--name', self.name, '--label', LABEL + '=' + self.token,
                '--pull=never', '--platform=linux/amd64', '--network=none', '--log-driver=none', '--restart=no',
                '--read-only', '--user=65532:65532', '--workdir=/app', '--cap-drop=ALL',
                '--security-opt=no-new-privileges', '--pids-limit=64', '--memory=512m', '--memory-swap=512m',
                '--cpus=1', '--shm-size=8m', '--ipc=private', '--cgroupns=private', '--no-healthcheck']
        for name, options in TMPFS.items(): args += ['--tmpfs', name + ':' + options]
        for name in ('HOME', 'PYTHONDONTWRITEBYTECODE'): args += ['--env', name + '=' + self.env[name]]
        if self.kind == 'dependencies': args += ['--entrypoint', self.entrypoint]
        return args + [self.image_id, *self.args]

    def record(self):
        raw = migration.safe_read(self.cidfile, 65)
        require(re.fullmatch(b'[0-9a-f]{64}\n?', raw), 'CONTAINER_ID_UNCERTAIN')
        value = raw.decode().strip()
        require(self.cid in (None, value), 'CONTAINER_ID_UNCERTAIN')
        self.cid = value

    def inspect(self, child=None, *, exited=False):
        require(self.cid is not None, 'CONTAINER_ID_UNCERTAIN')
        code, raw = (child or self.child)(['container', 'inspect', self.cid], timeout=15)
        require(code == 0, 'CONTAINER_IDENTITY_UNCERTAIN')
        data = document(raw, array=True)
        require(len(data) == 1 and type(data[0]) is dict, 'CONTAINER_REJECTED')
        data = data[0]; config, host, state = (data.get(key) for key in ('Config', 'HostConfig', 'State'))
        require(all(type(value) is dict for value in (config, host, state)), 'CONTAINER_REJECTED')
        require(data.get('Id') == self.cid and data.get('Image') == self.image_id and data.get('Name') == '/' + self.name
                and data.get('Path') == self.entrypoint and exact(data.get('Args'), self.args)
                and config.get('Image') == self.image_id and type(config.get('Labels')) is dict
                and config['Labels'].get(LABEL) == self.token
                and config['Labels'].get('org.opencontainers.image.revision') == self.commit
                and config.get('User') == '65532:65532' and config.get('WorkingDir') == '/app'
                and exact(config.get('Entrypoint'), [self.entrypoint])
                and (exact(config.get('Cmd'), self.args) or not self.args and config.get('Cmd') is None)
                and config.get('Volumes') in (None, {}) and config.get('ExposedPorts') in (None, {})
                and exact(config.get('Healthcheck'), {'Test': ['NONE']}), 'CONTAINER_REJECTED')
        values = config.get('Env')
        require(type(values) is list and len(values) == len(self.env)
                and set(values) == {key + '=' + value for key, value in self.env.items()}, 'CONTAINER_REJECTED')
        required = {'NetworkMode': 'none', 'PublishAllPorts': False, 'Privileged': False, 'ReadonlyRootfs': True,
                    'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges'], 'Tmpfs': TMPFS,
                    'LogConfig': {'Type': 'none', 'Config': {}}, 'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0},
                    'PidMode': '', 'IpcMode': 'private', 'CgroupnsMode': 'private', 'Memory': 536870912,
                    'MemorySwap': 536870912, 'NanoCpus': 1000000000, 'PidsLimit': 64, 'ShmSize': 8388608}
        require(all(exact(host.get(key), value) for key, value in required.items()), 'CONTAINER_REJECTED')
        require(host.get('PortBindings') in (None, {}) and all(host.get(key) in (None, []) for key in (
                'Binds', 'Mounts', 'VolumesFrom', 'CapAdd', 'Devices', 'DeviceRequests', 'DeviceCgroupRules')), 'CONTAINER_REJECTED')
        mounts = data.get('Mounts')
        require(type(mounts) is list and len(mounts) <= 1 and all(type(item) is dict and item.get('Type') == 'tmpfs'
                and item.get('Destination') == '/tmp' for item in mounts), 'CONTAINER_REJECTED')
        network = data.get('NetworkSettings')
        require(type(network) is dict and network.get('Ports') in (None, {})
                and type(network.get('Networks')) is dict and set(network['Networks']) == {'none'}, 'CONTAINER_REJECTED')
        none = network['Networks']['none']
        require(type(none) is dict and all(none.get(key) == '' for key in ('IPAddress', 'GlobalIPv6Address', 'Gateway')),
                'CONTAINER_REJECTED')
        if exited:
            require(state.get('Status') == 'exited' and state.get('Running') is False
                    and all(state.get(key) is False for key in ('Paused', 'Restarting', 'Dead', 'OOMKilled'))
                    and state.get('Error') == ''
                    and exact(state.get('ExitCode'), 1 if self.kind == 'default' else 0), 'CONTAINER_EXIT_REJECTED')

    def execute(self):
        require(not self.attempted and not os.path.lexists(self.cidfile), 'CONTAINER_COLLISION')
        with (self.root / (self.kind + '-custody.json')).open('x') as handle:
            os.chmod(handle.name, 0o600)
            json.dump({'name': self.name, 'token': self.token, 'label': LABEL, 'image_id': self.image_id,
                       'source_commit': self.commit}, handle)
            handle.flush(); os.fsync(handle.fileno())
        self.attempted = True
        try: code, raw = self.child(self.create_args(), timeout=30, limit=1024)
        finally: self.record()
        self.inspect()
        require(code == 0 and raw.strip() == self.cid.encode(), 'CONTAINER_CREATE_FAILED')
        code, raw = self.child(['start', '--attach', self.cid], timeout=120)
        self.inspect(exited=True)
        if self.kind == 'default':
            require(code == 1 and raw == b'', 'DEFAULT_DID_NOT_REFUSE')
        else:
            expected = {'status': 'MIGRATION_DEPENDENCIES_AND_SOURCE_VERIFIED', 'wheel_count': 30,
                        'migration_count': 29, 'source_file_count': len(self.expected['files']),
                        'database_connected': False, 'migrations_executed': False}
            require(code == 0 and exact(document(raw), expected), 'DEPENDENCY_PROBE_REJECTED')

    def cleanup(self, child):
        if not self.attempted or self.cleaned: return
        require(not self.cleanup_attempted and self.cid is not None, 'CLEANUP_UNCERTAIN')
        self.cleanup_attempted = True
        try:
            self.inspect(child)
            code, raw = child(['rm', '--force', self.cid], timeout=15, limit=1024)
            require(code == 0 and raw.strip() == self.cid.encode(), 'CLEANUP_UNCERTAIN')
            self.cleaned = True
        except (Exception, KeyboardInterrupt):
            raise Blocked('CLEANUP_UNCERTAIN') from None


def run(commit, *, root=None):
    budget = Budget.from_environment()
    root = Path(tempfile.mkdtemp(prefix='slc-migration-image-')) if root is None else Path(root)
    source_env = {'PATH': os.defpath, 'HOME': '/nonexistent', 'LANG': 'C.UTF-8', 'PIP_CONFIG_FILE': '/dev/null'}
    inventory, expected = source_child(commit, source_env, budget.allowance(600, 460))
    prefix, env = host(root, budget)
    wheelhouse = root / 'wheelhouse'; wheelhouse.mkdir(mode=0o700)
    acquire_child(inventory, wheelhouse, env, budget.allowance(1200, 460))
    context = root / 'context'
    prepared = context_child(['prepare', '--repository', str(ROOT), '--expected-commit', commit,
                              '--wheelhouse', str(wheelhouse), '--destination', str(context)], env, budget.allowance(600, 460))
    digest = validate_input_receipt(prepared, commit, prepared=True)
    verified = context_child(['verify', '--context', str(context), '--expected-commit', commit,
                               '--expected-manifest-sha256', digest], env, budget.allowance(180, 460))
    require(exact(verified, input_receipt(commit, digest, prepared=False)), 'INDEPENDENT_VERIFY_REJECTED')
    archive = root / 'build-context.tar'
    budget.reserve(460)
    build_digest = build_snapshot_child(context, commit, digest, archive, env, budget.allowance(180, 460))
    def docker(args, *, timeout=30, limit=65536, stdin=None, reserve=460):
        return command(prefix + args, env=env, timeout=budget.allowance(timeout, reserve), limit=limit, stdin=stdin)
    code, _ = docker(['pull', '--platform=linux/amd64', migration.BASE], timeout=600)
    require(code == 0, 'BASE_PULL_FAILED_OR_UNCERTAIN')
    code, raw = docker(['image', 'inspect', migration.BASE])
    require(code == 0, 'BASE_INSPECT_FAILED')
    base = document(raw, array=True)
    require(len(base) == 1 and type(base[0]) is dict and base[0].get('Id') == migration.BASE_CONFIG
            and base[0].get('Os') == 'linux' and base[0].get('Architecture') == 'amd64'
            and base[0].get('Variant') in (None, ''), 'BASE_IDENTITY_REJECTED')
    iidfile = root / 'migration.iid'
    require(not os.path.lexists(iidfile), 'BUILD_OUTPUT_COLLISION')
    with migration.directory(root) as fd, migration.wheels.regular_file(fd, archive.name) as (stream, info):
        require(info.st_size <= MAX_TAR and bounded_digest(stream, budget.allowance(120, 460)) == build_digest)
        stream.seek(0)
        code, _ = docker(['build', '--platform=linux/amd64', '--pull=false', '--no-cache', '--network=none',
                           '--progress=plain', '--iidfile', str(iidfile), '--build-arg', 'SOURCE_COMMIT=' + commit, '-'],
                          timeout=1800, stdin=stream)
        require(code == 0, 'BUILD_FAILED_OR_UNCERTAIN')
        stream.seek(0)
        require(bounded_digest(stream, budget.allowance(120, 460)) == build_digest, 'BUILD_INPUT_CHANGED')
    raw_id = migration.safe_read(iidfile, 72)
    require(re.fullmatch(b'sha256:[0-9a-f]{64}\n?', raw_id), 'BUILD_ID_REJECTED')
    image_id = raw_id.decode().strip()
    code, raw = docker(['image', 'inspect', image_id])
    require(code == 0, 'IMAGE_INSPECT_FAILED')
    baked = verify_image(document(raw, array=True), image_id, commit)
    removed = 0
    for kind in ('default', 'dependencies'):
        budget.reserve(430 if kind == 'default' else 215)
        work_deadline = time.monotonic() + 180
        def work(args, *, timeout=30, limit=65536):
            remaining = work_deadline - time.monotonic()
            require(remaining > 0, 'PROBE_TIMEOUT')
            return command(prefix + args, env=env, timeout=min(timeout, remaining), limit=limit)
        container = Container(root, work, image_id, commit, [k + '=' + v for k, v in baked.items()], kind, expected)
        try:
            container.execute()
        finally:
            cleanup_deadline = time.monotonic() + 35
            def cleanup(args, *, timeout=15, limit=65536):
                remaining = cleanup_deadline - time.monotonic()
                require(remaining > 0, 'CLEANUP_UNCERTAIN')
                return command(prefix + args, env=env, timeout=min(timeout, remaining), limit=limit)
            container.cleanup(cleanup)
        require(container.cleaned, 'CLEANUP_UNCERTAIN')
        removed += 1
    budget.reserve(0)
    return {'format': FORMAT, 'status': SUCCESS, 'source_commit': commit, 'context_manifest_sha256': digest,
            'build_context_sha256': build_digest, 'image_id': image_id, 'platform': 'linux/amd64',
            'wheel_count': 30, 'migration_count': 29, 'source_file_count': len(expected['files']),
            'default_exit_code': 1, 'containers_removed': removed, 'database_connected': False,
            'migrations_executed': False, 'limitations': LIMITATIONS}


class Parser(argparse.ArgumentParser):
    def error(self, _message): raise Blocked('ARGUMENTS_REJECTED')


def main(argv=None):
    previous = None; handler_attempted = False
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('--run', action='store_true')
        parser.add_argument('--expected-commit', required=True)
        args = parser.parse_args(argv)
        require(args.run and migration.HEX40.fullmatch(args.expected_commit), 'ARGUMENTS_REJECTED')
        previous = signal.getsignal(signal.SIGTERM); handler_attempted = True
        def interrupted(_signum, _frame): raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, interrupted)
        result = run(args.expected_commit)
        summary = os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary, 'a') as output:
                output.write('## Migration image preparation\n\n' + SUCCESS + '\n\nSource: ' + result['source_commit']
                    + '\n\nImage: ' + result['image_id'] + '\n\nContext SHA256: ' + result['context_manifest_sha256']
                    + '\n\nBuild input SHA256: ' + result['build_context_sha256']
                    + '\n\nDefault exit 1; 30 dependencies and 29 migration source files checked; both owned containers removed.\n\n'
                    + LIMITATIONS + '\n')
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print('MIGRATION_IMAGE_BLOCKED_OR_UNCERTAIN; no database or offline acceptance; no automatic retry or broad cleanup.', file=sys.stderr)
        return 2
    finally:
        if handler_attempted: signal.signal(signal.SIGTERM, previous)


if __name__ == '__main__':
    sys.exit(main())
