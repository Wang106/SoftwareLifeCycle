"""Unwired API-only preparation for a future trusted same-run coordinator.

No CLI: import/direct invocation performs no acquisition or daemon work.
Explicit prepare() requires separate acquisition/build approval, a reviewed clean
checkout and trusted local daemon. Digests/receipts are consistency, not authority.
"""
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

import offline_migration_image_rehearsal as builder
import offline_api_startup_rehearsal as startup

ROOT = Path(__file__).resolve().parents[1]
migration = builder.migration
wheels = migration.wheels
require = builder.require
Blocked = builder.Blocked
DOWNSTREAM_RESERVE = 630
MAX_TAR = migration.MAX_CONTEXT_BYTES + 8 * 1024**2
FIXED = frozenset({'backend/requirements.txt', 'backend/requirements-linux-cp312.lock',
    'backend/offline-python-wheelhouse.json', 'deploy/offline/api.Dockerfile',
    'deploy/offline/base-images.json', 'scripts/offline_python_wheelhouse.py'})
TOOLS = builder.BUILD_SOURCES | frozenset({
    'scripts/offline_api_image_preparation.py', 'scripts/offline_api_startup_rehearsal.py',
    'scripts/offline_database_rehearsal.py', 'scripts/offline_database_readiness.py'})
LIMITATIONS = ('Trusted reviewed checkout/local daemon only; hashes, labels and receipts do not '
    'authenticate provenance or authorize operations. API image preparation only, no application, '
    'database, migration, roles, web/npm build, export or deployment acceptance. '
    'CLI termination does not prove daemon work stopped; no retry or prune.')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def source_name(name):
    if name in FIXED:
        return True
    if name.startswith('backend/app/') and PurePosixPath(name).suffix in ('.py', '.json'):
        migration.path_parts(name)
        return True
    return False


def context_name(name):
    require(source_name(name), 'SOURCE_REJECTED')
    if name.startswith('backend/'):
        return name[len('backend/'):]
    return {'deploy/offline/api.Dockerfile': 'Dockerfile',
            'deploy/offline/base-images.json': 'base-images.json',
            'scripts/offline_python_wheelhouse.py': 'offline_python_wheelhouse.py'}[name]


def source_manifest(sources):
    return {name: {'sha256': digest(raw), 'size': len(raw)} for name, raw in sorted(sources.items())}


def source_inputs(commit):
    require(type(commit) is str and migration.HEX40.fullmatch(commit), 'SOURCE_REJECTED')
    for name in TOOLS:
        if name.startswith('scripts/'):
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
            require(migration.safe_read(ROOT / name, migration.MAX_SOURCE_FILE) == raw, 'SOURCE_CHANGED')
            checked.add(name)
            if selected:
                sources[name] = raw
                require(len(sources) <= migration.MAX_SOURCE_FILES
                        and sum(map(len, sources.values())) <= migration.MAX_SOURCE_TOTAL, 'SOURCE_LIMIT')
        require(FIXED | TOOLS <= checked and 'backend/app/main.py' in sources, 'SOURCE_MISSING')
        checkout()
    inventory = migration.json_value(sources['backend/offline-python-wheelhouse.json'])
    wheels.validate_manifest(inventory, sources['backend/requirements.txt'])
    require(len(inventory['artifacts']) == 30 and sources['backend/requirements-linux-cp312.lock'] ==
            wheels.lock_text(inventory).encode(), 'WHEEL_LOCK_REJECTED')
    bases = migration.json_value(sources['deploy/offline/base-images.json'])
    base = bases['images']['api']
    require(bases['format'] == 'slc-offline-base-images-v1' and base['reference'] == migration.BASE
            and base['config_digest'] == migration.BASE_CONFIG and base['platform'] == 'linux/amd64',
            'BASE_REJECTED')
    recipe = sources['deploy/offline/api.Dockerfile'].decode()
    require(re.findall(r'^FROM ([^\s]+)', recipe, re.M) == [migration.BASE, migration.BASE],
            'RECIPE_REJECTED')
    return sources, inventory


def build_context(commit, wheelhouse, target, expected_sources):
    sources, inventory = source_inputs(commit)
    require(digest(encoded(source_manifest(sources))) == expected_sources, 'SOURCE_CHANGED')
    with migration.wheel_directories():
        wheels.verify_artifacts(inventory, Path(wheelhouse))
    entries = {context_name(name): raw for name, raw in sources.items()}
    records = source_manifest(entries)
    for item in inventory['artifacts']:
        records['wheels/' + item['filename']] = {'sha256': item['sha256'], 'size': item['size_bytes']}
    manifest = encoded({'format': 'slc-api-build-context-v1', 'source_commit': commit,
                        'source_manifest_sha256': expected_sources, 'files': records})
    entries['api-build-context.json'] = manifest
    target = Path(target)
    with target.open('xb') as output:
        os.chmod(target, 0o600)
        with tarfile.open(fileobj=output, mode='w', format=tarfile.PAX_FORMAT) as archive:
            for name in sorted(set(records) | {'api-build-context.json'}):
                migration.path_parts(name)
                if name.startswith('wheels/'):
                    raw = migration.safe_read(Path(wheelhouse) / name.split('/', 1)[1], wheels.MAX_WHEEL)
                    require(len(raw) == records[name]['size'] and digest(raw) == records[name]['sha256'],
                            'WHEEL_CHANGED')
                else:
                    raw = entries[name]
                info = tarfile.TarInfo(name); info.size = len(raw); info.mode = 0o644
                archive.addfile(info, io.BytesIO(raw))
                require(output.tell() <= MAX_TAR, 'CONTEXT_LIMIT')
        require(output.tell() <= MAX_TAR, 'CONTEXT_LIMIT')
        output.flush(); os.fsync(output.fileno())
    with migration.directory(target.parent) as fd, wheels.regular_file(fd, target.name) as (stream, _):
        archive_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'source_commit': commit, 'source_manifest_sha256': expected_sources,
            'context_manifest_sha256': digest(manifest), 'build_context_sha256': archive_digest}


def receipt(commit, image, context_digest, build_digest):
    return {'format': 'slc-api-image-preparation-v1', 'status': 'API_IMAGE_PREPARED_NOT_STARTED',
            'source_commit': commit, 'image_id': image, 'context_manifest_sha256': context_digest,
            'build_context_sha256': build_digest, 'application_started': False,
            'database_connected': False, 'provenance_authenticated': False, 'limitations': LIMITATIONS}


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


def prepare(commit, *, root, budget):
    require(type(commit) is str and migration.HEX40.fullmatch(commit), 'SOURCE_REJECTED')
    require(type(budget) is builder.Budget and type(budget.deadline) in (int, float)
            and math.isfinite(budget.deadline), 'ORIGINAL_BUDGET_REQUIRED')
    deadline = budget.deadline
    def allowance(seconds):
        require(budget.deadline == deadline, 'BUDGET_CHANGED')
        return budget.allowance(seconds, DOWNSTREAM_RESERVE)
    budget.reserve(DOWNSTREAM_RESERVE)
    root = Path(root)
    require(not os.path.lexists(root), 'PREPARATION_COLLISION')
    root.mkdir(mode=0o700)
    source_env = {'PATH': os.defpath, 'HOME': '/nonexistent', 'LANG': 'C.UTF-8', 'PIP_CONFIG_FILE': '/dev/null'}
    program = ('import json,sys; sys.path.insert(0,sys.argv[1]); '
               'import offline_api_image_preparation as m; s,i=m.source_inputs(sys.argv[2]); '
               'print(json.dumps({"inventory":i,"source_manifest_sha256":m.digest(m.encoded(m.source_manifest(s)))}))')
    code, raw = builder.command([sys.executable, '-I', '-B', '-c', program, str(ROOT / 'scripts'), commit],
                                env=source_env, timeout=allowance(600))
    require(code == 0, 'SOURCE_CHILD_FAILED')
    source = builder.document(raw)
    require(type(source) is dict and set(source) == {'inventory', 'source_manifest_sha256'}
            and type(source['source_manifest_sha256']) is str
            and migration.HEX64.fullmatch(source['source_manifest_sha256']), 'SOURCE_RECEIPT_REJECTED')
    # The child checked inventory against exact-commit requirements; re-read it
    # again in context construction, never trust an external input receipt.
    inventory = source['inventory']
    require(type(inventory) is dict and type(inventory.get('artifacts')) is list
            and len(inventory['artifacts']) == 30, 'SOURCE_RECEIPT_REJECTED')
    prefix, env = builder.host(root, _HostBudget(allowance))
    wheelhouse = root / 'wheels'; wheelhouse.mkdir(mode=0o700)
    builder.acquire_child(inventory, wheelhouse, env, allowance(1200))
    archive = root / 'api-context.tar'
    program = ('import json,sys; sys.path.insert(0,sys.argv[1]); '
               'import offline_api_image_preparation as m; '
               'print(json.dumps(m.build_context(*sys.argv[2:])))')
    code, raw = builder.command([sys.executable, '-I', '-B', '-c', program, str(ROOT / 'scripts'), commit,
                                str(wheelhouse), str(archive), source['source_manifest_sha256']],
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
    code, _ = docker(['pull', '--platform=linux/amd64', migration.BASE], timeout=600)
    require(code == 0, 'BASE_PULL_FAILED_OR_UNCERTAIN')
    code, raw = docker(['image', 'inspect', migration.BASE])
    require(code == 0, 'BASE_REJECTED')
    base = builder.document(raw, array=True)
    require(len(base) == 1 and type(base[0]) is dict and base[0].get('Id') == migration.BASE_CONFIG
            and base[0].get('Os') == 'linux' and base[0].get('Architecture') == 'amd64'
            and base[0].get('Variant') in (None, ''), 'BASE_REJECTED')
    iid = root / 'api.iid'
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
    budget.reserve(DOWNSTREAM_RESERVE)
    return receipt(commit, image, context['context_manifest_sha256'], context['build_context_sha256'])
