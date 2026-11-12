"""Unwired Web-only preparation for a future trusted same-run coordinator.

No CLI: import or direct script execution performs no acquisition or daemon work.
Explicit prepare() requires separate acquisition/build approval, a reviewed clean
checkout and trusted local daemon. Digests/receipts are consistency, not authority.
"""
import hashlib
import io
import json
import math
import stat
from concurrent.futures import ThreadPoolExecutor
import offline_npm_artifacts as npm
import os
from pathlib import Path
import re
import sys
import tarfile

import offline_migration_image_rehearsal as builder
import offline_web_startup_rehearsal as startup

ROOT = Path(__file__).resolve().parents[1]
migration = builder.migration
wheels = migration.wheels
require = builder.require
Blocked = builder.Blocked
# Existing 1330-second pre-PG floor plus provisional 300-second Web allowance.
# The caller must still enforce all phase floors; preparation duration is unknown.
DOWNSTREAM_RESERVE = 1630
CLEANUP_RESERVE = 60
MAX_TAR = npm.inventory.MAX_TOTAL_BYTES + migration.MAX_SOURCE_TOTAL + 16 * 1024**2
BASE = 'docker.io/library/node@sha256:aaa4b5baf1ecff3b283486bb1f90405cdda225a3e6f79660d2c559fa510a7292'
BASE_CONFIG = 'sha256:8700da48cc6592503feabf399d242414f932197c3b44f43970d2cbc5671e06b0'
FIXED = frozenset(name for name in builder.fetcher.SOURCE_FILES if name.startswith('frontend/')) | frozenset({
    'deploy/offline/web.Dockerfile', 'deploy/offline/base-images.json'})
TOOLS = frozenset(name for name in builder.BUILD_SOURCES if name.startswith('scripts/')) | frozenset({
    'scripts/offline_web_image_preparation.py', 'scripts/offline_web_startup_rehearsal.py',
    'scripts/offline_web_startup_probe.cjs', 'scripts/offline_api_startup_rehearsal.py',
    'scripts/offline_database_rehearsal.py', 'scripts/offline_database_readiness.py'})
LIMITATIONS = ('Trusted reviewed checkout/local daemon only; hashes, labels and receipts do not '
    'authenticate provenance or authorize acquisition/build. Web image preparation only; no API image, '
    'application startup, database, migration, export, upload or deployment acceptance. '
    'Deadline reserves are admission floors, not build-duration guarantees. '
    'CLI termination does not prove daemon work stopped; no retry, removal or prune.')


def read_file(path, limit):
    # Unlike the legacy convenience wrapper, preserve interruption semantics.
    path = Path(path)
    with migration.directory(path.parent) as fd:
        return migration.read_at(fd, path.name, limit)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def source_name(name):
    return name in FIXED or (name.startswith('frontend/') and builder.fetcher.source_allowed(name))


def context_path(name):
    # Next route segments such as [scope]/[id] are canonical path components,
    # not traversal. Keep the shared migration-only grammar unchanged.
    require(type(name) is str and 0 < len(name) <= 512 and not name.startswith('/')
            and '\\' not in name, 'CONTEXT_PATH_REJECTED')
    parts = name.split('/')
    require(len(parts) <= 16 and all(re.fullmatch(r'[A-Za-z0-9_\[\](][A-Za-z0-9_.\[\]()-]*', part)
            and not part.startswith('.') and part not in ('.', '..') for part in parts),
            'CONTEXT_PATH_REJECTED')
    require(not any(part.lower() in {'auth.json', 'npmrc'} or re.search(
        r'(?:^|[_.-])(?:secrets?|credentials?)(?:$|[_.-])', part.lower()) for part in parts),
        'CONTEXT_PATH_REJECTED')
    return parts


def context_name(name):
    require(source_name(name), 'SOURCE_REJECTED')
    if name.startswith('frontend/'):
        return name[len('frontend/'):]
    return {'deploy/offline/web.Dockerfile': 'Dockerfile',
            'deploy/offline/base-images.json': 'base-images.json'}[name]


def source_manifest(sources):
    return {name: {'sha256': digest(raw), 'size': len(raw)} for name, raw in sorted(sources.items())}


def source_inputs(commit):
    require(type(commit) is str and migration.HEX40.fullmatch(commit), 'SOURCE_REJECTED')
    for name in TOOLS:
        if name.endswith('.py'):
            module = sys.modules.get(Path(name).stem)
            require(module is not None and Path(module.__file__).absolute() == ROOT / name,
                    'TOOL_LOCATION_REJECTED')
    with migration.directory(ROOT) as fd:
        config = migration.git_read(fd, ['config', '--includes', '--null', '--list'])
        require(not any(item.split(b'\n', 1)[0].lower().startswith(b'filter.')
                        for item in config.split(b'\0') if item), 'FILTER_REJECTED')
        def checkout():
            require(migration.git_read(fd, ['rev-parse', 'HEAD'], 128).decode().strip() == commit
                    and not migration.git_read(fd, ['status', '--porcelain', '--untracked-files=all']).strip(),
                    'CHECKOUT_REJECTED')
        checkout()
        records = migration.git_read(fd, ['ls-tree', '-r', '-z', commit]).split(b'\0')
        sources, checked = {}, set()
        for record in filter(None, records):
            header, raw_name = record.split(b'\t', 1)
            name = raw_name.decode('utf-8')
            selected = source_name(name)
            if not selected and name not in TOOLS:
                continue
            mode, kind, oid = header.split(b' ')
            require(mode == b'100644' and kind == b'blob' and migration.HEX40.fullmatch(oid.decode()),
                    'SOURCE_REJECTED')
            raw = migration.git_read(fd, ['cat-file', 'blob', oid.decode()], migration.MAX_SOURCE_FILE)
            require(read_file(ROOT / name, migration.MAX_SOURCE_FILE) == raw, 'SOURCE_CHANGED')
            checked.add(name)
            if selected:
                sources[name] = raw
                require(len(sources) <= migration.MAX_SOURCE_FILES
                        and sum(map(len, sources.values())) <= migration.MAX_SOURCE_TOTAL, 'SOURCE_LIMIT')
        require(FIXED | TOOLS <= checked and all(any(n.startswith('frontend/' + d + '/') for n in sources) for d in ('app', 'components', 'lib')), 'SOURCE_MISSING')
        checkout()
    raw_lock = sources['frontend/package-lock.json']
    expected = npm.inventory.inventory(migration.json_value(raw_lock), digest(raw_lock))
    inventory = migration.json_value(sources['frontend/offline-npm-artifacts.json'])
    require(type(inventory) is dict and inventory.get('artifact_count') == expected['artifact_count'] == 399
            and inventory.get('lockfile_sha256') == digest(raw_lock)
            and type(inventory.get('artifacts')) is list and len(inventory['artifacts']) == 399,
            'NPM_LOCK_REJECTED')
    for actual, item in zip(inventory['artifacts'], expected['artifacts']):
        require(type(actual) is dict and all(builder.exact(actual.get(k), v) for k, v in item.items())
                and type(actual.get('size_bytes')) is int
                and 0 < actual['size_bytes'] <= npm.inventory.MAX_ARTIFACT_BYTES, 'NPM_LOCK_REJECTED')
    require(sum(a['size_bytes'] for a in inventory['artifacts']) <= npm.inventory.MAX_TOTAL_BYTES,
            'NPM_LIMIT_REJECTED')
    bases = migration.json_value(sources['deploy/offline/base-images.json'])
    base = bases['images']['web']
    require(bases['format'] == 'slc-offline-base-images-v1' and base['reference'] == BASE
            and base['config_digest'] == BASE_CONFIG and base['platform'] == 'linux/amd64', 'BASE_REJECTED')
    require(re.findall(r'^FROM ([^\s]+)', sources['deploy/offline/web.Dockerfile'].decode(), re.M)
            == [BASE, BASE], 'RECIPE_REJECTED')
    return sources, inventory


def acquire(commit, destination, expected_sources):
    # Revalidate trusted source in this bounded child; caller JSON never authorizes URLs.
    sources, inventory = source_inputs(commit)
    require(digest(encoded(source_manifest(sources))) == expected_sources, 'SOURCE_CHANGED')
    builder.fetcher.reject_inherited_proxy()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for offset in range(0, 399, 4):
            futures = [pool.submit(builder.fetcher.fetch, item, Path(destination), 'sha512')
                       for item in inventory['artifacts'][offset:offset + 4]]
            for future in futures:
                future.result()


def build_context(commit, artifacts, target, expected_sources):
    sources, inventory = source_inputs(commit)
    require(digest(encoded(source_manifest(sources))) == expected_sources, 'SOURCE_CHANGED')
    # The repository lock was independently byte-bound above; audit actual tarball
    # metadata, expanded limits and integrity before packing any build input.
    require(builder.exact(npm.audit_artifacts(ROOT / 'frontend/package-lock.json', Path(artifacts)), inventory),
            'NPM_AUDIT_REJECTED')
    require(read_file(ROOT / 'frontend/package-lock.json', migration.MAX_SOURCE_FILE)
            == sources['frontend/package-lock.json'], 'SOURCE_CHANGED')
    entries = {context_name(name): raw for name, raw in sources.items()}
    records = source_manifest(entries)
    for item in inventory['artifacts']:
        records['artifacts/' + item['filename']] = {'sha512': item['sha512'], 'size': item['size_bytes']}
    manifest = encoded({'format': 'slc-web-build-context-v1', 'source_commit': commit,
                        'source_manifest_sha256': expected_sources, 'files': records})
    entries['web-build-context.json'] = manifest
    target = Path(target)
    with migration.directory(target.parent) as parent:
        fd = os.open(target.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as output, tarfile.open(fileobj=output, mode='w', format=tarfile.PAX_FORMAT) as archive:
            for name in sorted(set(records) | {'web-build-context.json'}):
                context_path(name)
                info = tarfile.TarInfo(name); info.mode = 0o644
                if name.startswith('artifacts/'):
                    with npm.inventory.directory(artifacts) as directory, npm.inventory.regular_file(directory, name.split('/', 1)[1]) as (stream, st):
                        require(st.st_size == records[name]['size'] and hashlib.file_digest(stream, 'sha512').hexdigest()
                                == records[name]['sha512'], 'NPM_CHANGED')
                        stream.seek(0); info.size = st.st_size
                        archive.addfile(info, stream)
                else:
                    raw = entries[name]; info.size = len(raw)
                    archive.addfile(info, io.BytesIO(raw))
                require(output.tell() <= MAX_TAR, 'CONTEXT_LIMIT')
        require(os.stat(target.name, dir_fd=parent, follow_symlinks=False).st_size <= MAX_TAR, 'CONTEXT_LIMIT')
    with migration.directory(target.parent) as fd, npm.inventory.regular_file(fd, target.name) as (stream, _):
        archive_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'source_commit': commit, 'source_manifest_sha256': expected_sources,
            'context_manifest_sha256': digest(manifest), 'build_context_sha256': archive_digest}


def receipt(commit, image, context_digest, build_digest):
    require(type(commit) is str and migration.HEX40.fullmatch(commit)
            and type(image) is str and re.fullmatch('sha256:[0-9a-f]{64}', image)
            and all(type(v) is str and migration.HEX64.fullmatch(v) for v in (context_digest, build_digest)),
            'RECEIPT_REJECTED')
    return {'format': 'slc-web-image-preparation-v1', 'status': 'WEB_IMAGE_PREPARED_NOT_STARTED',
            'source_commit': commit, 'image_id': image, 'context_manifest_sha256': context_digest,
            'build_context_sha256': build_digest, 'application_started': False,
            'database_connected': False, 'provenance_authenticated': False,
            'local_inputs_removed': True, 'limitations': LIMITATIONS}


class _HostBudget:
    """Only expose the coordinator's reserve-aware allowance to legacy host checks."""
    def __init__(self, allowance):
        self._allowance = allowance

    def allowance(self, cap, reserve=0):
        require(reserve == 0, 'HOST_RESERVE_REJECTED')
        return self._allowance(cap)


def read_iid(path):
    # Keep the legacy ordinary-error normalization, but never swallow a control
    # exception. Reads retain no-follow directory and single-link file checks.
    try:
        path = Path(path)
        with migration.directory(path.parent) as fd:
            return migration.read_at(fd, path.name, 72)
    except Exception:
        raise migration.Blocked('MIGRATION_INPUTS_BLOCKED') from None


def _prepare(commit, *, root, budget):
    require(type(commit) is str and migration.HEX40.fullmatch(commit), 'SOURCE_REJECTED')
    require(type(budget) is builder.Budget and type(budget.deadline) in (int, float)
            and math.isfinite(budget.deadline), 'ORIGINAL_BUDGET_REQUIRED')
    deadline = budget.deadline
    def allowance(seconds):
        require(budget.deadline == deadline, 'BUDGET_CHANGED')
        return budget.allowance(seconds, DOWNSTREAM_RESERVE + CLEANUP_RESERVE)
    budget.reserve(DOWNSTREAM_RESERVE + CLEANUP_RESERVE)
    root = Path(root)
    require(not os.path.lexists(root), 'PREPARATION_COLLISION')
    with migration.directory(root.parent) as parent:
        os.mkdir(root.name, mode=0o700, dir_fd=parent)
    with migration.directory(root) as fd:
        owned = migration.identity(os.fstat(fd))
        require(stat.S_IMODE(os.fstat(fd).st_mode) == 0o700 and os.fstat(fd).st_uid == os.getuid(), 'PATH_REJECTED')
    source_env = {'PATH': os.defpath, 'HOME': '/nonexistent', 'LANG': 'C.UTF-8', 'PIP_CONFIG_FILE': '/dev/null'}
    program = ('import json,sys; sys.path.insert(0,sys.argv[1]); '
               'import offline_web_image_preparation as m; s,i=m.source_inputs(sys.argv[2]); '
               'print(json.dumps({"source_manifest_sha256":m.digest(m.encoded(m.source_manifest(s)))}))')
    code, raw = builder.command([sys.executable, '-I', '-B', '-c', program, str(ROOT / 'scripts'), commit],
                                env=source_env, timeout=allowance(600))
    require(code == 0, 'SOURCE_CHILD_FAILED')
    source = builder.document(raw)
    require(type(source) is dict and set(source) == {'source_manifest_sha256'}
            and type(source['source_manifest_sha256']) is str
            and migration.HEX64.fullmatch(source['source_manifest_sha256']), 'SOURCE_RECEIPT_REJECTED')
    prefix, env = builder.host(root, _HostBudget(allowance))
    artifacts = root / 'artifacts'; artifacts.mkdir(mode=0o700)
    program = ('import sys; sys.path.insert(0,sys.argv[1]); '
               'import offline_web_image_preparation as m; m.acquire(*sys.argv[2:])')
    code, raw = builder.command([sys.executable, '-I', '-B', '-c', program, str(ROOT / 'scripts'), commit,
                                str(artifacts), source['source_manifest_sha256']],
                               env=env, timeout=allowance(1200), limit=1024)
    require(code == 0 and raw == b'', 'NPM_ACQUISITION_FAILED')
    archive = root / 'web-context.tar'
    program = ('import json,sys; sys.path.insert(0,sys.argv[1]); '
               'import offline_web_image_preparation as m; '
               'print(json.dumps(m.build_context(*sys.argv[2:])))')
    code, raw = builder.command([sys.executable, '-I', '-B', '-c', program, str(ROOT / 'scripts'), commit,
                                str(artifacts), str(archive), source['source_manifest_sha256']],
                               env=env, timeout=allowance(600))
    require(code == 0, 'CONTEXT_CHILD_FAILED')
    context = builder.document(raw)
    require(type(context) is dict and set(context) == {'source_commit', 'source_manifest_sha256',
            'context_manifest_sha256', 'build_context_sha256'} and context['source_commit'] == commit
            and context['source_manifest_sha256'] == source['source_manifest_sha256']
            and all(type(context[k]) is str and migration.HEX64.fullmatch(context[k])
                    for k in ('context_manifest_sha256', 'build_context_sha256')), 'CONTEXT_RECEIPT_REJECTED')
    def docker(args, *, timeout=30, stdin=None):
        return builder.command(prefix + args, env=env, timeout=allowance(timeout), stdin=stdin)
    code, _ = docker(['pull', '--platform=linux/amd64', BASE], timeout=600)
    require(code == 0, 'BASE_PULL_FAILED_OR_UNCERTAIN')
    code, raw = docker(['image', 'inspect', BASE])
    require(code == 0, 'BASE_REJECTED')
    base = builder.document(raw, array=True)
    require(len(base) == 1 and type(base[0]) is dict and base[0].get('Id') == BASE_CONFIG
            and base[0].get('Os') == 'linux' and base[0].get('Architecture') == 'amd64'
            and base[0].get('Variant') in (None, ''), 'BASE_REJECTED')
    iid = root / 'web.iid'
    require(not os.path.lexists(iid), 'BUILD_OUTPUT_COLLISION')
    with migration.directory(root) as fd, wheels.regular_file(fd, archive.name) as (stream, info):
        require(info.st_size <= MAX_TAR and builder.bounded_digest(stream, allowance(120)) ==
                context['build_context_sha256'], 'BUILD_INPUT_CHANGED')
        stream.seek(0)
        code, _ = docker(['build', '--platform=linux/amd64', '--pull=false', '--no-cache', '--network=none',
                           '--progress=plain', '--iidfile', str(iid), '--build-arg', 'SOURCE_COMMIT=' + commit, '-'],
                          timeout=1800, stdin=stream)
        require(code == 0, 'BUILD_FAILED_OR_UNCERTAIN')
        stream.seek(0)
        require(builder.bounded_digest(stream, allowance(120)) == context['build_context_sha256'], 'BUILD_INPUT_CHANGED')
    raw_id = read_iid(iid)
    require(re.fullmatch(b'sha256:[0-9a-f]{64}\n?', raw_id), 'BUILD_ID_REJECTED')
    image = raw_id.decode().strip()
    code, raw = docker(['image', 'inspect', image])
    require(code == 0, 'IMAGE_REJECTED')
    startup.verify_image(raw, image, commit)
    require(budget.deadline == deadline, 'BUDGET_CHANGED')
    budget.reserve(DOWNSTREAM_RESERVE + CLEANUP_RESERVE)
    cleanup(root, owned, budget, deadline)
    return receipt(commit, image, context['context_manifest_sha256'], context['build_context_sha256'])


def cleanup(root, owned, budget, deadline):
    """Only successful preparation removes its private local directory, never images.

    On earlier error/interruption retain partial local evidence; daemon outcomes may
    be uncertain. Failed cleanup is failure, not a success receipt or a retry.
    """
    require(budget.deadline == deadline, 'BUDGET_CHANGED')
    with migration.directory(root) as fd:
        require(migration.identity(os.fstat(fd)) == owned, 'CLEANUP_OWNERSHIP_REJECTED')
    program = ('import os,shutil,sys; sys.path.insert(0,sys.argv[1]); '
               'import offline_migration_context as m; p=m.Path(sys.argv[2]); '
               'expected=tuple(map(int,sys.argv[3:])); '
               'f=m.directory(p.parent); fd=f.__enter__(); '
               'm.require(m.identity(os.stat(p.name,dir_fd=fd,follow_symlinks=False))==expected); '
               'm.require(shutil.rmtree.avoids_symlink_attacks); '
               'shutil.rmtree(p.name,dir_fd=fd); f.__exit__(None,None,None)')
    code, raw = builder.command([sys.executable, '-I', '-B', '-c', program, str(ROOT / 'scripts'), str(root),
                                *map(str, owned)], env={'PATH': os.defpath, 'LANG': 'C.UTF-8'},
                               timeout=budget.allowance(CLEANUP_RESERVE, DOWNSTREAM_RESERVE), limit=1024)
    require(code == 0 and raw == b'' and not os.path.lexists(root), 'CLEANUP_FAILED_OR_UNCERTAIN')
    require(budget.deadline == deadline, 'BUDGET_CHANGED')
    budget.reserve(DOWNSTREAM_RESERVE)


def prepare(commit, *, root, budget):
    """Internal explicit entry point, not authorization or an externally supplied receipt API."""
    try:
        return _prepare(commit, root=root, budget=budget)
    except Exception:
        raise Blocked('WEB_PREPARATION_BLOCKED_OR_UNCERTAIN') from None
