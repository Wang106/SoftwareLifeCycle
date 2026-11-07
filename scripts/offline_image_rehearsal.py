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
TOOLS = {'scripts/offline_image_rehearsal.py', 'scripts/offline_python_wheelhouse.py',
         'scripts/offline_npm_inventory.py', 'scripts/offline_npm_artifacts.py',
         'scripts/offline_readonly_preflight.py', 'deploy/offline/api.Dockerfile',
         'deploy/offline/web.Dockerfile', 'deploy/offline/base-images.json'}
require = preflight.require
RUN_ENV = None
LOG_ROOT = None
STEP = 'host prerequisites'


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
    identity = image_id(role, commit)
    archive = destination / (role + '.tar')
    command(['docker', 'image', 'save', '--output', str(archive), identity], timeout=600)
    with archive.open('rb') as stream:
        sha256 = preflight.digest(stream)
    item = {'archive': archive.name, 'size': archive.stat().st_size, 'sha256': sha256,
            'image_id': identity, 'platform': 'linux/amd64', 'source_commit': commit}
    # Never rewrite an OCI/containerd export or relax the existing preflight.
    preflight.archive_image(archive, item, commit)
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
    secret = destination / 'database.env'
    secret.touch(mode=0o600, exist_ok=False)  # Empty parser input, not a database credential.
    document = preflight.compose(manifest, secret)
    path = destination / 'compose.json'
    path.write_text(json.dumps(document, indent=2) + '\n')
    parsed = json.loads(command(['docker', 'compose', '--env-file', str(secret), '-f', str(path),
                                  'config', '--format', 'json', '--no-env-resolution']))
    require(set(parsed['services']) == {'api', 'web'}, 'Compose service mismatch')
    for role, service in document['services'].items():
        actual = parsed['services'][role]
        require(not any(k in actual for k in ('build', 'ports', 'volumes', 'secrets', 'configs')),
                'unexpected Compose source or mount')
        for key, value in service.items():
            if key != 'env_file':
                require(actual.get(key) == value, 'effective Compose policy changed')
        require(actual.get('env_file', []) == service.get('env_file', []), 'raw env-file policy changed')
    return {'status': 'COMPOSE_PARSED_ONLY', 'operator_approval': False, 'application_started': False}


def run(root=ROOT):
    global RUN_ENV, LOG_ROOT, STEP
    STEP = 'host prerequisites'
    host = check_host()  # Must precede directories, downloads, pulls and builds.
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
    return evidence


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, 'offline image rehearsal: invalid arguments\n')


def main(argv=None):
    parser = SafeParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-host', action='store_true')
    mode.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = check_host() if args.check_host else run()
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
