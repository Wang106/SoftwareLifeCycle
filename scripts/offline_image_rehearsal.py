#!/usr/bin/env python3
"""Explicit manual image rehearsal, not an installer or disconnected acceptance.

Checks existing host, downloads audited public inputs, builds dedicated images,
validates untouched docker-save bytes, runs dependency-only smoke and parses
Compose. Never starts the app/database, uploads, changes host settings or retries.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import offline_image_bundle as bundle
import offline_npm_artifacts as npm
import offline_python_wheelhouse as wheels
import offline_readonly_preflight as preflight

MIN_FREE = 20 * 1024**3
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = {'backend/app': {'.py', '.json'}, 'frontend/app': {'.ts', '.tsx', '.css', '.json'},
               'frontend/components': {'.ts', '.tsx'}, 'frontend/lib': {'.ts', '.tsx', '.json'}}
SOURCE_FILES = {'frontend/package.json', 'frontend/package-lock.json', 'frontend/next.config.js',
                'frontend/next-env.d.ts', 'frontend/tsconfig.json', 'frontend/offline-npm-artifacts.json',
                'backend/requirements.txt', 'backend/requirements-linux-cp312.lock',
                'backend/offline-python-wheelhouse.json'}
TOOLS = {'scripts/offline_image_rehearsal.py', 'scripts/offline_image_bundle.py', 'scripts/offline_python_wheelhouse.py',
         'scripts/offline_npm_inventory.py', 'scripts/offline_npm_artifacts.py',
         'scripts/offline_readonly_preflight.py', 'deploy/offline/api.Dockerfile',
         'deploy/offline/web.Dockerfile', 'deploy/offline/base-images.json'}
require = preflight.require
RUN_ENV = None
LOG_ROOT = None
STEP = 'host prerequisites'


# Exact trusted validator messages are selectors, never public exception text.
ARCHIVE_REASON_CODES = {
    'duplicate JSON field': 'ARCHIVE_JSON_DUPLICATE_FIELD',
    'unexpected or missing fields': 'ARCHIVE_FIELDS_REJECTED',
    'unexpected or missing image item fields': 'ARCHIVE_ITEM_FIELDS_REJECTED',
    'invalid docker-save manifest record': 'ARCHIVE_MANIFEST_RECORD_REJECTED',
    'missing docker-save manifest fields': 'ARCHIVE_MANIFEST_FIELDS_MISSING',
    'unreviewed docker-save manifest fields': 'ARCHIVE_MANIFEST_FIELDS_REJECTED',
    'invalid LayerSources mapping': 'ARCHIVE_LAYER_SOURCES_MAPPING_REJECTED',
    'invalid LayerSources blob path': 'ARCHIVE_LAYER_SOURCES_PATH_REJECTED',
    'unreviewed LayerSources descriptor fields': 'ARCHIVE_LAYER_SOURCE_FIELDS_REJECTED',
    'unreviewed LayerSources media type': 'ARCHIVE_LAYER_SOURCE_MEDIA_TYPE_REJECTED',
    'LayerSources digest mismatch': 'ARCHIVE_LAYER_SOURCE_DIGEST_MISMATCH',
    'LayerSources size mismatch': 'ARCHIVE_LAYER_SOURCE_SIZE_MISMATCH',
    'invalid LayerSources uncompressed tar': 'ARCHIVE_LAYER_SOURCE_TAR_REJECTED',
    'image provenance mismatch': 'ARCHIVE_PROVENANCE_MISMATCH',
    'invalid archive checksum': 'ARCHIVE_CHECKSUM_FORMAT_REJECTED',
    'image must use immutable ID': 'ARCHIVE_IMAGE_ID_REJECTED',
    'archive size mismatch': 'ARCHIVE_SIZE_MISMATCH',
    'archive checksum mismatch': 'ARCHIVE_CHECKSUM_MISMATCH',
    'unsafe or duplicate archive path': 'ARCHIVE_PATH_REJECTED',
    'archive links or special files refused': 'ARCHIVE_ENTRY_TYPE_REJECTED',
    'missing or oversized image metadata': 'ARCHIVE_METADATA_REJECTED',
    'archive must contain exactly one image': 'ARCHIVE_IMAGE_COUNT_REJECTED',
    'image config digest mismatch': 'ARCHIVE_CONFIG_DIGEST_MISMATCH',
    'image platform mismatch': 'ARCHIVE_PLATFORM_MISMATCH',
    'image revision label mismatch': 'ARCHIVE_REVISION_MISMATCH',
    'invalid image environment': 'ARCHIVE_ENV_INVALID',
    'unreviewed baked image environment': 'ARCHIVE_ENV_REJECTED',
    'invalid public GPG fingerprint': 'ARCHIVE_GPG_FINGERPRINT_REJECTED',
    'image-declared writable volumes refused': 'ARCHIVE_VOLUMES_REJECTED',
    'invalid image layers': 'ARCHIVE_LAYERS_REJECTED',
    'missing image layer': 'ARCHIVE_LAYER_MISSING',
    'image layer digest mismatch': 'ARCHIVE_LAYER_DIGEST_MISMATCH',
}
EXPORT_CODES = frozenset(ARCHIVE_REASON_CODES.values()) | {
    'IMAGE_INSPECT_FAILED', 'IMAGE_INSPECT_TIMEOUT', 'IMAGE_INSPECT_ERROR',
    'SAVE_COMMAND_FAILED', 'SAVE_COMMAND_TIMEOUT', 'SAVE_COMMAND_ERROR',
    'ARCHIVE_READ_FAILED', 'ARCHIVE_TAR_INVALID', 'ARCHIVE_JSON_INVALID',
    'ARCHIVE_VALIDATION_FAILED',
}


def safe_export_code(code):
    return code if type(code) is str and code in EXPORT_CODES else 'ARCHIVE_VALIDATION_FAILED'


def safe_export_role(role):
    return role if type(role) is str and role in ('api', 'web') else 'unknown'


class ExportFailure(ValueError):
    def __init__(self, code, role='unknown'):
        self.code = safe_export_code(code)
        self.role = safe_export_role(role)
        super().__init__(self.code)


def fixed_preflight_reason(error):
    if type(error) is preflight.Invalid and len(error.args) == 1 and type(error.args[0]) is str:
        return error.args[0]
    return None


def export_command_code(error, prefix):
    if isinstance(error, subprocess.TimeoutExpired):
        return prefix + '_TIMEOUT'
    if fixed_preflight_reason(error) == 'command failed':
        return prefix + '_FAILED'
    # Includes local invocation/logging errors: command outcome may be uncertain.
    return prefix + '_ERROR'


COMPOSE_CODES = frozenset({
    'COMPOSE_COMMAND_FAILED', 'COMPOSE_COMMAND_TIMEOUT', 'COMPOSE_COMMAND_ERROR',
    'COMPOSE_JSON_INVALID', 'COMPOSE_POLICY_REJECTED', 'COMPOSE_CAPABILITY_MISSING',
    'COMPOSE_PREPARE_FAILED', 'COMPOSE_VALIDATION_FAILED',
})
COMPOSE_PHASES = frozenset({'capability', 'prepare', 'project', 'model'})
COMPOSE_FIELDS = frozenset({
    'document', 'name', 'services', 'platform', 'pull_policy', 'network_mode',
    'read_only', 'restart', 'cap_drop', 'security_opt', 'user', 'working_dir',
    'tmpfs', 'healthcheck', 'image', 'entrypoint', 'command', 'env_file',
    'environment', 'logging',
})


def safe_compose_part(value, allowed, fallback='unknown'):
    return value if type(value) is str and value in allowed else fallback


class ComposeFailure(ValueError):
    def __init__(self, code, *, phase='unknown', role='unknown', field='unknown'):
        self.code = safe_compose_part(code, COMPOSE_CODES, 'COMPOSE_VALIDATION_FAILED')
        self.phase = safe_compose_part(phase, COMPOSE_PHASES)
        self.role = safe_export_role(role)
        self.field = safe_compose_part(field, COMPOSE_FIELDS)
        super().__init__(self.code)


def compose_command(args, phase):
    try:
        return command(args, timeout=30)
    except Exception as error:
        if isinstance(error, subprocess.TimeoutExpired):
            code = 'COMPOSE_COMMAND_TIMEOUT'
        elif fixed_preflight_reason(error) == 'command failed':
            code = 'COMPOSE_COMMAND_FAILED'
        else:
            code = 'COMPOSE_COMMAND_ERROR'
        raise ComposeFailure(code, phase=phase) from None


def check_compose_capabilities():
    raw = compose_command(['docker', 'compose', 'config', '--help'], 'capability')
    try:
        help_text = raw.decode('utf-8')
        supported = all(re.search(r'(?m)^\s+--' + flag + r'(?=\s|$)', help_text)
                        for flag in ('no-env-resolution', 'no-interpolate'))
    except Exception:
        supported = False
    if not supported:
        raise ComposeFailure('COMPOSE_CAPABILITY_MISSING', phase='capability')


def compose_json(raw, phase):
    def reject_constant(_value):
        raise ValueError('nonfinite JSON number')
    try:
        return json.loads(raw, object_pairs_hook=preflight.object_pairs, parse_constant=reject_constant)
    except Exception:
        raise ComposeFailure('COMPOSE_JSON_INVALID', phase=phase) from None


def exact_compose_value(actual, expected):
    # Python equality alone aliases True with 1 and False with 0.
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(exact_compose_value(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(exact_compose_value(a, e) for a, e in zip(actual, expected))
    return actual == expected


def check_compose_view(actual, expected, phase):
    def blocked(role='unknown', field='unknown'):
        raise ComposeFailure('COMPOSE_POLICY_REJECTED', phase=phase, role=role, field=field)
    try:
        if type(actual) is not dict or set(actual) != set(expected):
            blocked(field='document')
        if not exact_compose_value(actual['name'], expected['name']):
            blocked(field='name')
        services = actual['services']
        if type(services) is not dict or set(services) != {'api', 'web'}:
            blocked(field='services')
        for role in ('api', 'web'):
            service = services[role]
            policy = expected['services'][role]
            if type(service) is not dict:
                blocked(role, 'services')
            # Proven Compose 2.38.2 project rendering discards this sole field.
            # The model view must still match the complete original policy.
            if phase == 'project' and role == 'api' and 'env_file' not in service:
                policy = {key: value for key, value in policy.items() if key != 'env_file'}
            if set(service) != set(policy):
                changed = set(service) ^ set(policy)
                known = sorted(changed & COMPOSE_FIELDS)
                blocked(role, known[0] if known else 'unknown')
            for key, value in policy.items():
                if not exact_compose_value(service[key], value):
                    blocked(role, key)
    except ComposeFailure:
        raise
    except Exception:
        raise ComposeFailure('COMPOSE_VALIDATION_FAILED', phase=phase) from None


def command(args, *, cwd=None, timeout=120):
    """No shell, inherited credentials, retries, or failure text in public output."""
    env = {**(RUN_ENV or {'PATH': os.environ.get('PATH', ''), 'LANG': 'C.UTF-8'}),
           'DOCKER_CONTEXT': 'default'}
    result = subprocess.run(args, cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False, timeout=timeout)
    if LOG_ROOT is not None:
        with (LOG_ROOT / 'commands.log').open('ab') as log:
            log.write(json.dumps(args).encode() + b'\n' + result.stdout + result.stderr + b'\n')
    require(result.returncode == 0, 'command failed')
    return result.stdout


def validate_host(info, compose_version, free_temp, free_docker):
    require(info.get('OSType') == 'linux' and info.get('Architecture') in ('amd64', 'x86_64'),
            'Linux amd64 Docker daemon required')
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:[-+][a-zA-Z0-9.-]+)?', compose_version)
    require(match is not None and tuple(map(int, match.groups())) >= (2, 30, 0),
            'Compose 2.30 or later required')
    require(min(free_temp, free_docker) >= MIN_FREE, '20 GiB free on both filesystems required')


def check_host():
    require(sys.platform == 'linux' and platform.machine() == 'x86_64'
            and sys.version_info[:2] == (3, 12), 'Linux amd64 Python 3.12 required')
    require(not os.environ.get('DOCKER_HOST') and not os.environ.get('DOCKER_CONTEXT'),
            'remote or overridden Docker target refused')
    version = json.loads(command(['docker', 'version', '--format', '{{json .}}']))
    info = json.loads(command(['docker', 'info', '--format', '{{json .}}']))
    compose_version = command(['docker', 'compose', 'version', '--short']).decode().strip()
    docker_root = Path(info['DockerRootDir'])
    require(docker_root.is_absolute(), 'local daemon filesystem required')
    temp_free = shutil.disk_usage(tempfile.gettempdir()).free
    docker_free = shutil.disk_usage(docker_root).free
    validate_host(info, compose_version, temp_free, docker_free)
    check_compose_capabilities()  # Before run directories, acquisition or image builds.
    return {'docker_client': version['Client']['Version'], 'docker_server': version['Server']['Version'],
            'compose': compose_version, 'platform': 'linux/amd64',
            'temporary_free_bytes': temp_free, 'docker_free_bytes': docker_free}


def load_bases(root):
    data = json.loads((root / 'deploy/offline/base-images.json').read_bytes(),
                      object_pairs_hook=preflight.object_pairs)
    require(data.get('format') == 'slc-offline-base-images-v1' and
            set(data.get('images', {})) == {'api', 'web'}, 'invalid base inventory')
    for role, repository in (('api', 'python'), ('web', 'node')):
        item = data['images'][role]
        require(item.get('platform') == 'linux/amd64' and
                all(isinstance(item.get(k), str) and DIGEST.fullmatch(item[k])
                    for k in ('index_digest', 'manifest_digest', 'config_digest')),
                'immutable platform digest required')
        require(item.get('reference') == 'docker.io/library/' + repository + '@' + item['manifest_digest']
                and item.get('manifest_url') == 'https://registry-1.docker.io/v2/library/' + repository
                + '/manifests/' + item['manifest_digest'], 'official pinned base required')
    return data


def source_allowed(name):
    parts = PurePosixPath(name).parts
    if ('\\' in name or name.startswith('/') or any(p in ('', '.', '..') or p.startswith('.') for p in name.split('/'))
            or any(p.lower() in {'auth.json', 'npmrc'} or
                   re.search(r'(?:^|[_.-])(?:secrets?|credentials?)(?:$|[_.-])', p.lower()) for p in parts)):
        return False
    if name in SOURCE_FILES:
        return True
    return any(name.startswith(directory + '/') and PurePosixPath(name).suffix in extensions
               for directory, extensions in SOURCE_DIRS.items())


def snapshot(root, target):
    require(not command(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=root).strip(),
            'clean committed checkout required')
    commit = command(['git', 'rev-parse', 'HEAD'], cwd=root).decode().strip()
    require(re.fullmatch(r'[0-9a-f]{40}', commit), 'exact commit required')
    records = command(['git', 'ls-tree', '-r', '-z', commit], cwd=root).split(b'\0')
    selected, hashes = set(), {}
    for record in filter(None, records):
        meta, raw_name = record.split(b'\t', 1)
        name = raw_name.decode('utf-8')
        if not (source_allowed(name) or name in TOOLS):
            continue
        require(meta.split()[0] == b'100644', 'source must be regular nonexecutable files')
        raw = command(['git', 'show', commit + ':' + name], cwd=root)
        require(len(raw) <= 4 * 1024**2, 'source file too large')
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        selected.add(name)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    require(SOURCE_FILES | TOOLS <= selected, 'missing explicit source input')
    for directory in SOURCE_DIRS:
        require(any(p.startswith(directory + '/') for p in selected), 'missing source directory')
    return commit, hashes


class ProxyBlocked(ValueError):
    pass


class CleanupUnconfirmed(RuntimeError):
    pass


def reject_inherited_proxy():
    # Do not silently bypass a required proxy or expose its possible credentials.
    # Empty values and no_proxy are overrides too; leave the environment unchanged.
    if any(name.lower().endswith('_proxy') for name in os.environ):
        raise ProxyBlocked('inherited proxy configuration requires review')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError('redirect refused')


def fetch(item, target, algorithm, opener=None):
    """Only called with validated, repository-pinned official artifact entries."""
    reject_inherited_proxy()
    opener = opener or urllib.request.build_opener(NoRedirect())
    h, size, started = hashlib.new(algorithm), 0, time.monotonic()
    request = urllib.request.Request(item['url'], headers={'Accept-Encoding': 'identity'})
    with (target / item['filename']).open('xb') as output:
        with opener.open(request, timeout=60) as response:
            require(response.status == 200 and response.url == item['url'], 'unexpected artifact response')
            while block := response.read(min(1024**2, item['size_bytes'] + 1 - size)):
                size += len(block)
                require(size <= item['size_bytes'] and time.monotonic() - started < 300,
                        'artifact download bounds exceeded')
                h.update(block)
                output.write(block)
    require(size == item['size_bytes'] and h.hexdigest() == item[algorithm], 'artifact bytes mismatch')


def acquire(source, api_context, web_context):
    reject_inherited_proxy()
    py = wheels.read_json(source / 'backend/offline-python-wheelhouse.json')[0]
    requirements = wheels.read_bytes(source / 'backend/requirements.txt')
    wheels.validate_manifest(py, requirements)
    require(wheels.read_bytes(source / 'backend/requirements-linux-cp312.lock') ==
            wheels.lock_text(py).encode() and len(py['artifacts']) == 30, 'wheel lock changed')
    lock, checksum = npm.inventory.read_lock(source / 'frontend/package-lock.json')
    expected = npm.inventory.inventory(lock, checksum)
    recorded = json.loads((source / 'frontend/offline-npm-artifacts.json').read_bytes(),
                          object_pairs_hook=preflight.object_pairs)
    require(recorded['artifact_count'] == expected['artifact_count'] == 399 and
            recorded['lockfile_sha256'] == checksum and len(recorded['artifacts']) == 399,
            'npm inventory changed')
    for actual, item in zip(recorded['artifacts'], expected['artifacts']):
        require(all(actual.get(k) == v for k, v in item.items()) and type(actual.get('size_bytes')) is int
                and 0 < actual['size_bytes'] <= npm.inventory.MAX_ARTIFACT_BYTES, 'npm artifact provenance mismatch')
    require(sum(a['size_bytes'] for a in recorded['artifacts']) <= npm.inventory.MAX_TOTAL_BYTES,
            'npm total size exceeded')
    wheel_dir, npm_dir = api_context / 'wheels', web_context / 'artifacts'
    wheel_dir.mkdir()
    npm_dir.mkdir()
    for manifest, destination, algorithm in ((py, wheel_dir, 'sha256'), (recorded, npm_dir, 'sha512')):
        # Bounded public-source GETs; no retry, mirror, credentials or redirects.
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(fetch, item, destination, algorithm) for item in manifest['artifacts']]
            try:
                for future in as_completed(futures):
                    future.result()
            except Exception:
                for future in futures:
                    future.cancel()  # In-flight GETs finish; queued requests are not retried.
                raise
    wheel_result = wheels.verify(source / 'backend/requirements.txt', source / 'backend/offline-python-wheelhouse.json',
                                 source / 'backend/requirements-linux-cp312.lock', wheel_dir)
    require(npm.audit_artifacts(source / 'frontend/package-lock.json', npm_dir) == recorded,
            'npm real archive audit differs from reviewed inventory')
    return {'python': wheel_result, 'npm_artifacts': 399, 'npm_bytes': recorded['total_size_bytes']}


def prepare_contexts(source, root):
    contexts = {}
    for role, directory in (('api', 'backend'), ('web', 'frontend')):
        target = root / (role + '-context')
        target.mkdir()
        for path in (source / directory).rglob('*'):
            if path.is_file():
                relative = path.relative_to(source / directory)
                if relative.name == 'offline-npm-artifacts.json':
                    continue
                (target / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target / relative)
        shutil.copyfile(source / f'deploy/offline/{role}.Dockerfile', target / 'Dockerfile')
        contexts[role] = target
    shutil.copyfile(source / 'scripts/offline_python_wheelhouse.py', contexts['api'] / 'offline_python_wheelhouse.py')
    return contexts


def image_id(role, commit):
    identity = command(['docker', 'image', 'inspect', '--format', '{{.Id}}',
                        'slc-rehearsal-' + role + ':' + commit]).decode().strip()
    require(DIGEST.fullmatch(identity), 'immutable image ID required')
    return identity


def export_image(role, commit, destination):
    try:
        identity = image_id(role, commit)
    except Exception as error:
        raise ExportFailure(export_command_code(error, 'IMAGE_INSPECT'), role) from None
    archive = destination / (role + '.tar')
    try:
        command(['docker', 'image', 'save', '--output', str(archive), identity], timeout=600)
    except Exception as error:
        raise ExportFailure(export_command_code(error, 'SAVE_COMMAND'), role) from None
    try:
        with archive.open('rb') as stream:
            sha256 = preflight.digest(stream)
        item = {'archive': archive.name, 'size': archive.stat().st_size, 'sha256': sha256,
                'image_id': identity, 'platform': 'linux/amd64', 'source_commit': commit}
    except Exception:
        raise ExportFailure('ARCHIVE_READ_FAILED', role) from None
    # Never rewrite an OCI/containerd export or relax the existing preflight.
    try:
        preflight.archive_image(archive, item, commit)
    except Exception as error:
        code = ARCHIVE_REASON_CODES.get(fixed_preflight_reason(error), 'ARCHIVE_VALIDATION_FAILED')
        if isinstance(error, preflight.tarfile.TarError):
            code = 'ARCHIVE_TAR_INVALID'
        elif isinstance(error, (json.JSONDecodeError, UnicodeDecodeError)):
            code = 'ARCHIVE_JSON_INVALID'
        elif isinstance(error, OSError):
            code = 'ARCHIVE_READ_FAILED'
        raise ExportFailure(code, role) from None
    return item


PYTHON_SMOKE = '''import importlib, json, os, pathlib, platform, sys, tempfile
assert os.getuid() == 65532 and os.getgid() == 65532
assert sys.version_info[:3] == (3, 12, 14)
print(json.dumps({'python': platform.python_version(), 'glibc': platform.libc_ver()}))
assert pathlib.Path('/app/app/main.py').is_file()
for name in ('fastapi', 'uvicorn', 'sqlalchemy', 'psycopg', 'alembic', 'pydantic_settings', 'jwt',
             'psycopg_binary._psycopg', 'cryptography.hazmat.bindings._rust', 'pydantic_core._pydantic_core',
             '_cffi_backend', 'greenlet._greenlet', 'httptools.parser.parser', 'uvloop.loop',
             'watchfiles._rust_notify', 'websockets.speedups', 'yaml._yaml', 'markupsafe._speedups',
             'sqlalchemy.cyextension.collections'):
    importlib.import_module(name)
import psycopg
assert psycopg.pq.__impl__ == 'binary'
for path in pathlib.Path('/app/app').rglob('*.py'):
    compile(path.read_bytes(), str(path), 'exec')
with tempfile.TemporaryFile(dir='/tmp') as handle:
    handle.write(b'synthetic')
print('API_DEPENDENCY_SMOKE_OK; no application import or database connection')
'''
NODE_SMOKE = '''const assert = require('node:assert/strict');
const fs = require('node:fs');
assert.equal(process.getuid(), 65532); assert.equal(process.getgid(), 65532);
assert.equal(process.versions.node, '22.23.4');
console.log(JSON.stringify({node: process.versions.node, glibc: process.report.getReport().header.glibcVersionRuntime}));
assert.ok(fs.existsSync('/app/.next/BUILD_ID'));
assert.ok(fs.existsSync('/app/node_modules/next/dist/bin/next'));
assert.ok(require('@next/swc-linux-x64-gnu').transformSync('const value: number = 1', false,
  Buffer.from(JSON.stringify({jsc:{parser:{syntax:'typescript'}},filename:'smoke.ts'}))).code);
assert.ok(require('@ast-grep/napi').parse('JavaScript', 'const a = 1').root().text());
assert.ok(require('esbuild').transformSync('const x: number = 1', {loader:'ts'}).code);
const child = require('node:child_process');
child.execFileSync(require('workerd').default, ['--version'], {timeout:30000});
(async () => { const sharp = require('sharp');
  const image = await sharp({create:{width:2,height:2,channels:4,background:'#336699'}}).png().toBuffer();
  assert.equal((await sharp(image).metadata()).width, 2);
  fs.writeFileSync('/tmp/slc-synthetic-smoke', 'synthetic');
  console.log('WEB_DEPENDENCY_SMOKE_OK; no Next server or application route started');
})().catch(() => process.exit(1));
'''


def smoke_command(role, identity, cidfile):
    common = ['docker', 'create', '--cidfile', str(cidfile), '--pull=never', '--platform=linux/amd64',
              '--read-only', '--user', '65532:65532', '--cap-drop=ALL',
              '--security-opt=no-new-privileges:true', '--workdir=/app',
              '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m', '--pids-limit=128',
              '--memory=2g', '--cpus=2', '--env', 'HOME=/tmp']
    if role == 'api':
        return common + ['--env', 'PYTHONDONTWRITEBYTECODE=1', '--entrypoint', '/usr/local/bin/python',
                         identity, '-I', '-B', '-c', PYTHON_SMOKE]
    return common + ['--env', 'NEXT_TELEMETRY_DISABLED=1', '--env', 'WRANGLER_SEND_METRICS=false',
                     '--entrypoint', '/usr/local/bin/node', identity, '-e', NODE_SMOKE]


def recorded_cid(path):
    value = wheels.read_bytes(path, limit=66).decode('ascii').strip()
    require(re.fullmatch(r'[0-9a-f]{64}', value), 'invalid container CID record')
    return value


def smoke(role, identity, destination):
    # Create first, without starting a process, so CID is durable before attach.
    record = Path(tempfile.mkdtemp(prefix=role + '-smoke-', dir=destination)) / 'container.cid'
    container = None
    try:
        created = command(smoke_command(role, identity, record), timeout=120).decode('ascii').strip()
        if re.fullmatch(r'[0-9a-f]{64}', created):
            container = created
        cid = recorded_cid(record)
        require(container == cid, 'container identity mismatch')
        output = command(['docker', 'start', '--attach', container], timeout=120)
        status = command(['docker', 'container', 'inspect', '--format', '{{.State.ExitCode}}', container], timeout=30)
        require(status.strip() == b'0', 'native smoke exited unsuccessfully')
        return output
    finally:
        # Includes failed/timeout attach and ordinary exceptions. Never prune or
        # address another image/container. Missing CID is an uncertain outcome.
        try:
            container = container or recorded_cid(record)
            removed = command(['docker', 'container', 'rm', '--force', container], timeout=30)
            require(removed.decode('ascii').strip() == container, 'container removal not confirmed')
        except Exception:
            raise CleanupUnconfirmed('smoke container cleanup failed or unconfirmed') from None


def parse_compose(manifest, destination):
    try:
        secret = destination / 'database.env'
        secret.touch(mode=0o600, exist_ok=False)  # Empty parser input, not a database credential.
        document = preflight.compose(manifest, secret)
        path = destination / 'compose.json'
        path.write_text(json.dumps(document, indent=2) + '\n')
    except Exception:
        raise ComposeFailure('COMPOSE_PREPARE_FAILED', phase='prepare') from None
    args = ['docker', 'compose', '--env-file', str(secret), '-f', str(path),
            'config', '--format', 'json', '--no-env-resolution']
    # Do not replace the normal project load: it performs consistency checks that
    # the non-interpolated model view does not. Neither call starts a service.
    project = compose_json(compose_command(args, 'project'), 'project')
    check_compose_view(project, document, 'project')
    model = compose_json(compose_command(args + ['--no-interpolate'], 'model'), 'model')
    check_compose_view(model, document, 'model')
    return {'status': 'COMPOSE_PARSED_ONLY', 'operator_approval': False, 'application_started': False}


def run(root=ROOT, *, bundle_destination=None):
    global RUN_ENV, LOG_ROOT, STEP
    STEP = 'host prerequisites'
    host = check_host()  # Must precede directories, downloads, pulls and builds.
    if bundle_destination is not None:
        bundle.check_destination(bundle_destination)
    run_dir = Path(tempfile.mkdtemp(prefix='slc-image-rehearsal-'))
    LOG_ROOT = run_dir
    home = run_dir / 'home'
    home.mkdir()
    docker_config = run_dir / 'docker-config'
    docker_config.mkdir()
    RUN_ENV = {'PATH': os.environ.get('PATH', ''), 'HOME': str(home), 'LANG': 'C.UTF-8',
               'DOCKER_CONFIG': str(docker_config), 'DOCKER_BUILDKIT': '1'}
    source = run_dir / 'source'
    source.mkdir()
    STEP = 'exact source snapshot'
    commit, source_hashes = snapshot(root, source)
    bases = load_bases(source)
    contexts = prepare_contexts(source, run_dir)
    STEP = 'official artifacts and existing audits'
    dependencies = acquire(source, contexts['api'], contexts['web'])
    manifest = {'format': 'slc-offline-readonly-v1', 'source_commit': commit,
                'required_db_revision': preflight.REVISION, 'images': {}}
    native_smoke = {}
    for role in ('api', 'web'):
        STEP = role + ' base pull and build'
        base = bases['images'][role]
        command(['docker', 'pull', '--platform=linux/amd64', base['reference']], timeout=600)
        base_config = json.loads(command(['docker', 'image', 'inspect', base['reference']]))[0]
        require(base_config['Id'] == base['config_digest'] and base_config['Os'] == 'linux'
                and base_config['Architecture'] == 'amd64', 'pulled base identity mismatch')
        command(['docker', 'build', '--platform=linux/amd64', '--pull=false', '--no-cache', '--progress=plain',
                 '--build-arg', 'SOURCE_COMMIT=' + commit, '--tag', 'slc-rehearsal-' + role + ':' + commit,
                 str(contexts[role])], timeout=1800)
        STEP = role + ' traditional docker-save validation'
        manifest['images'][role] = export_image(role, commit, run_dir)
        STEP = role + ' read-only nonroot native smoke'
        native_smoke[role] = smoke(role, manifest['images'][role]['image_id'], run_dir).decode()
    STEP = 'Compose parse only'
    compose = parse_compose(manifest, run_dir)
    evidence = {'status': 'IMAGE_REHEARSAL_PASSED_NOT_OFFLINE_ACCEPTANCE', 'source_commit': commit,
                'host': host, 'bases': bases, 'dependencies': dependencies, 'images': manifest['images'],
                'source_sha256': source_hashes, 'compose': compose, 'native_smoke': native_smoke,
                'limitations': 'Connected preparation only; no physical egress isolation, application/DB startup, '
                               'operator approval, security/license clearance, transfer or company acceptance.'}
    (run_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (run_dir / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    if bundle_destination is not None:
        STEP = 'optional local image handoff export'
        evidence['image_bundle'] = bundle.export_bundle(run_dir, manifest, evidence, bundle_destination)
    return evidence


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, 'offline image rehearsal: invalid arguments\n')


def bundle_failure(error):
    code = error.code if type(error.code) is str and error.code in bundle.CODES else 'BUNDLE_POLICY_REJECTED'
    print('BLOCKED: local image handoff export code=' + code +
          '; preserve output and inspect with read-only verification; do not retry uncertain completion; '
          'no offline or deployment acceptance claimed.', file=sys.stderr)
    receipt = bundle.safe_receipt(getattr(error, 'receipt', None))
    if code == 'BUNDLE_COMPLETION_UNCERTAIN' and receipt is not None:
        # These values were constructed and checked by this run before committing,
        # not read back from the potentially incomplete handoff directory.
        print('Trusted local run verification expectations: source_commit=' + receipt['source_commit'] +
              '; manifest_sha256=' + receipt['manifest_sha256'], file=sys.stderr)


def main(argv=None):
    parser = SafeParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-host', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--export-bundle', help='new absolute local directory; only with --run')
    args = parser.parse_args(argv)
    if args.export_bundle is not None and not args.run:
        parser.error('export requires run')
    try:
        result = (check_host() if args.check_host else
                  run() if args.export_bundle is None else run(bundle_destination=args.export_bundle))
    except bundle.CompletionInterrupted as error:
        bundle_failure(error)
        raise  # Still an interruption; safe fixed exception text only.
    except bundle.BundleError as error:
        bundle_failure(error)
        return 2
    except ComposeFailure as error:
        print('BLOCKED: offline image rehearsal Compose phase=' + safe_compose_part(error.phase, COMPOSE_PHASES) +
              '; role=' + safe_export_role(error.role) + '; field=' + safe_compose_part(error.field, COMPOSE_FIELDS) +
              '; code=' + safe_compose_part(error.code, COMPOSE_CODES, 'COMPOSE_VALIDATION_FAILED') +
              '; no offline or deployment acceptance claimed.', file=sys.stderr)
        return 2
    except ExportFailure as error:
        print('BLOCKED: offline image rehearsal export role=' + safe_export_role(error.role) +
              '; code=' + safe_export_code(error.code) +
              '; no offline or deployment acceptance claimed.', file=sys.stderr)
        return 2
    except ProxyBlocked:
        print('BLOCKED: inherited proxy configuration requires review; no proxy bypass or artifact request performed.',
              file=sys.stderr)
        return 2
    except CleanupUnconfirmed:
        print('BLOCKED: smoke container cleanup failed or unconfirmed; inspect this run’s CID record; no success claimed.',
              file=sys.stderr)
        return 2
    except (ValueError, OSError, KeyError, TypeError, AttributeError, RuntimeError,
            subprocess.SubprocessError, EOFError, wheels.zipfile.BadZipFile, npm.tarfile.TarError, npm.zlib.error):
        print('BLOCKED: offline image rehearsal failed at ' + STEP +
              '; no offline or deployment acceptance claimed.', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
