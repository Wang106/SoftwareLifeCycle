#!/usr/bin/env python3
"""Prepare or verify local migration image inputs; never build or contact a DB.

Only the existing wheel verifier may invoke pip's offline, hash-locked dry run.
An independently supplied commit/digest binds consistency, not authenticity.
Incomplete or uncertain output is retained, never automatically removed/retried.
"""
import argparse
import ast
import configparser
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import signal
import selectors
import stat
import subprocess
import sys
import time

import offline_python_wheelhouse as wheels

REVISION = '0030_private_upload_sessions'
BASE = 'docker.io/library/python@sha256:1aaa65a85fda306ffb8b910824d4e93bdce61e212c7e87168123ea3073b41a1a'
BASE_CONFIG = 'sha256:febd0be41adb897a0ab8f1f1c693d8912669ea60c4940e076e9946b60e210ef0'
MANIFEST = 'migration-inputs.json'
FORMAT = 'slc-offline-migration-inputs-v1'
MAX_SOURCE_FILE = 4 * 1024**2
MAX_SOURCE_TOTAL = 16 * 1024**2
MAX_SOURCE_FILES = 512
MAX_MANIFEST = 1024**2
MAX_GIT_OUTPUT = 8 * 1024**2
MAX_CONTEXT_FILES = 544
MAX_CONTEXT_BYTES = MAX_SOURCE_TOTAL + wheels.MAX_TOTAL + MAX_MANIFEST
FIXED_SOURCES = frozenset({
    'backend/alembic.ini', 'backend/alembic/env.py', 'backend/app/core/config.py',
    'backend/requirements.txt', 'backend/requirements-linux-cp312.lock',
    'backend/offline-python-wheelhouse.json', 'scripts/offline_python_wheelhouse.py',
    'deploy/offline/base-images.json', 'deploy/offline/migration.Dockerfile',
    'scripts/offline_migration_context.py',
})
HEX40 = re.compile('[0-9a-f]{40}')
HEX64 = re.compile('[0-9a-f]{64}')


class Blocked(ValueError):
    pass


def require(ok):
    if not ok:
        raise Blocked('MIGRATION_INPUTS_BLOCKED')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return info.st_dev, info.st_ino, info.st_mode


def close_fds(fds):
    failure = None
    while fds:
        fd = fds.pop()  # Relinquish ownership before close, even if outcome is uncertain.
        try:
            os.close(fd)
        except BaseException as error:
            failure = failure or error
    if failure is not None:
        raise failure


@contextlib.contextmanager
def directory(path):
    path = Path(path)
    require(os.name == 'posix' and hasattr(os, 'O_NOFOLLOW') and '..' not in path.parts)
    path = path if path.is_absolute() else Path.cwd() / path
    require(len(str(path)) <= 4096 and len(path.parts) <= 64)
    descriptors = [os.open('/', os.O_RDONLY | os.O_DIRECTORY)]
    links = []
    try:
        root_identity = identity(os.fstat(descriptors[0]))
        for part in path.parts[1:]:
            parent = descriptors[-1]
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            descriptors.append(child)
            links.append((parent, part, identity(os.fstat(child))))
        yield descriptors[-1]
        require(identity(os.stat('/')) == root_identity)
        for parent, name, expected in links:
            require(identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected)
    finally:
        close_fds(descriptors)


@contextlib.contextmanager
def wheel_directories():
    # Adapt the unchanged legacy verifier's directory dependency locally.
    original = wheels.directory
    wheels.directory = directory
    try:
        yield
    finally:
        wheels.directory = original


def safe_read(path, limit):
    try:
        path = Path(path)
        with directory(path.parent) as fd:
            return read_at(fd, path.name, limit)
    except (Exception, KeyboardInterrupt):
        raise Blocked('MIGRATION_INPUTS_BLOCKED') from None


def path_parts(name):
    require(type(name) is str and 0 < len(name) <= 512 and '\\' not in name)
    parts = name.split('/')
    require(len(parts) <= 16 and all(re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_.-]*', p)
                                   and not p.startswith('.') and p not in ('.', '..') for p in parts))
    require(not any(p.lower() in {'auth.json', 'npmrc'} or re.search(
        r'(?:^|[_.-])(?:secrets?|credentials?)(?:$|[_.-])', p.lower()) for p in parts))
    return parts


def source_name(name):
    path_parts(name)
    return (name in FIXED_SOURCES or
            name.startswith('backend/app/') and PurePosixPath(name).suffix in {'.py', '.json'} or
            re.fullmatch(r'backend/alembic/versions/[0-9]{4}_[a-z0-9_]+\.py', name) is not None)


def context_name(source):
    require(source_name(source))
    if source.startswith('backend/'):
        return source[len('backend/'):]
    return {'scripts/offline_python_wheelhouse.py': 'offline_python_wheelhouse.py',
            'scripts/offline_migration_context.py': 'offline_migration_context.py',
            'deploy/offline/base-images.json': 'base-images.json',
            'deploy/offline/migration.Dockerfile': 'Dockerfile'}[source]


def json_value(raw):
    require(type(raw) is bytes)
    return json.loads(raw, object_pairs_hook=wheels.unique_object,
                      parse_constant=lambda _: require(False))


def declarations(tree, fields, body):
    values, permitted = {}, set()
    for node in body:
        targets = node.targets if isinstance(node, ast.Assign) else ([node.target] if isinstance(node, ast.AnnAssign) else [])
        for target in targets:
            if isinstance(target, ast.Name) and target.id in fields:
                require(len(targets) == 1 and target.id not in values)
                values[target.id] = ast.literal_eval(node.value)
                permitted.add(id(target))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in fields and isinstance(node.ctx, (ast.Store, ast.Del)):
            require(id(node) in permitted)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            require(node.name not in fields)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            require(not any(a.name == '*' or (a.asname or a.name.split('.')[0]) in fields for a in node.names))
        if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
            require(node.name not in fields)
        if isinstance(node, ast.MatchMapping):
            require(node.rest not in fields)
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            require(not fields.intersection(node.names))
    require(set(values) == fields)
    return values


def revision_values(raw):
    tree = ast.parse(raw)
    values = declarations(tree, {'revision', 'down_revision', 'branch_labels', 'depends_on'}, tree.body)
    require(values['branch_labels'] is None and values['depends_on'] is None)
    require(type(values['revision']) is str and
            (values['down_revision'] is None or type(values['down_revision']) is str))
    return values


def validate_sources(sources):
    try:
        require(type(sources) is dict and FIXED_SOURCES <= set(sources) and
                0 < len(sources) <= MAX_SOURCE_FILES)
        require(all(source_name(name) and type(raw) is bytes and len(raw) <= MAX_SOURCE_FILE
                    for name, raw in sources.items()))
        require(sum(map(len, sources.values())) <= MAX_SOURCE_TOTAL)
        versions = sorted(name for name in sources if name.startswith('backend/alembic/versions/'))
        require(len(versions) == 30)
        predecessor = None
        for index, name in enumerate(versions, 1):
            item = revision_values(sources[name])
            require(PurePosixPath(name).stem == item['revision'] and
                    item['revision'].startswith(f'{index:04d}_') and item['down_revision'] == predecessor)
            predecessor = item['revision']
        require(predecessor == REVISION)
        settings_tree = ast.parse(sources['backend/app/core/config.py'])
        settings = [n for n in settings_tree.body if isinstance(n, ast.ClassDef) and n.name == 'Settings']
        require(len(settings) == 1)
        heads = declarations(settings_tree, {'required_db_revision'}, settings[0].body)
        require(heads == {'required_db_revision': REVISION})
        ini = configparser.RawConfigParser()
        ini.read_string(sources['backend/alembic.ini'].decode('utf-8'))
        require(ini.sections() == ['alembic'] and not ini.defaults() and
                set(ini['alembic']) == {'script_location', 'sqlalchemy.url'} and
                ini['alembic']['script_location'] == 'alembic' and
                ini['alembic']['sqlalchemy.url'] ==
                'postgresql+psycopg://slc:slc_dev_password@localhost:5432/software_lifecycle')
        bases = json_value(sources['deploy/offline/base-images.json'])
        base = bases['images']['api']
        require(bases['format'] == 'slc-offline-base-images-v1' and
                base['reference'] == BASE and base['config_digest'] == BASE_CONFIG and
                base['platform'] == 'linux/amd64')
        inventory = json_value(sources['backend/offline-python-wheelhouse.json'])
        wheels.validate_manifest(inventory, sources['backend/requirements.txt'])
        require(len(inventory['artifacts']) == 30 and
                sources['backend/requirements-linux-cp312.lock'] == wheels.lock_text(inventory).encode())
        return {'migration_count': 30, 'required_db_revision': REVISION, 'inventory': inventory}
    except (Exception, KeyboardInterrupt):
        raise Blocked('MIGRATION_INPUTS_BLOCKED') from None


def child_limits():
    # Limits apply only to this verification child and its descendants.
    for kind, maximum in ((resource.RLIMIT_AS, 1024**3), (resource.RLIMIT_CPU, 120),
                          (resource.RLIMIT_FSIZE, wheels.MAX_WHEEL)):
        soft, hard = resource.getrlimit(kind)
        hard = maximum if hard == resource.RLIM_INFINITY else min(maximum, hard)
        soft = hard if soft == resource.RLIM_INFINITY else min(soft, hard)
        resource.setrlimit(kind, (soft, hard))


def bounded_command(command, *, env, cwd=None, pass_fds=(), limit=MAX_GIT_OUTPUT,
                    timeout=20, confined=False):
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=cwd, pass_fds=pass_fds, env=env,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True, preexec_fn=child_limits if confined else None)
    output = bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, True)
            selector.register(process.stderr, selectors.EVENT_READ, False)
            total = 0
            while selector.get_map():
                remaining = timeout - (time.monotonic() - started)
                require(remaining > 0)
                for key, _ in selector.select(min(remaining, .1)):
                    chunk = os.read(key.fileobj.fileno(), min(65536, limit + 1 - total))
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        total += len(chunk)
                        require(total <= limit)
                        if key.data:
                            output.extend(chunk)
        require(process.wait(timeout=max(.01, timeout - (time.monotonic() - started))) == 0)
    finally:
        # Until wait succeeds the leader has not been reaped, so its PID cannot
        # be reused. Kill this session's group once on failure, without retry.
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)
        process.stdout.close()
        process.stderr.close()
    return bytes(output)


def git_read(repo_fd, args, limit=MAX_GIT_OUTPUT):
    """Bound both pipes before accumulating; never fetch or use inherited Git config."""
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': '/nonexistent',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'}
    command = ['/usr/bin/git', '--no-pager', '--no-replace-objects', '--no-lazy-fetch',
               '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', *args]
    return bounded_command(command, env=env, cwd=f'/proc/self/fd/{repo_fd}', pass_fds=(repo_fd,), limit=limit)


def check_wheels_only(context):
    context = Path(context)
    with wheel_directories():
        result = wheels.verify(context / 'requirements.txt', context / 'offline-python-wheelhouse.json',
                               context / 'requirements-linux-cp312.lock', context / 'wheels')
    print(json.dumps(result))


def verify_wheel_closure(context, trusted_checker_bytes, trusted_driver_bytes):
    # Only import the two checked local tools, never context copies.
    checker = Path(wheels.__file__).absolute()
    driver = Path(__file__).absolute()
    require(safe_read(checker, MAX_SOURCE_FILE) == trusted_checker_bytes and
            safe_read(driver, MAX_SOURCE_FILE) == trusted_driver_bytes)
    program = ('import sys; sys.path.insert(0, sys.argv[1]); '
               'import offline_migration_context as m; m.check_wheels_only(sys.argv[2])')
    result = bounded_command([sys.executable, '-I', '-B', '-c', program, str(driver.parent), str(context)],
        env={'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'PIP_CONFIG_FILE': '/dev/null',
             'LANG': 'C.UTF-8'}, limit=65536, timeout=150, confined=True)
    return json_value(result)


def read_at(root_fd, name, limit):
    parts = path_parts(name)
    fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            previous, fd = fd, child
            os.close(previous)
        with wheels.regular_file(fd, parts[-1]) as (stream, info):
            require(info.st_size <= limit)
            raw = stream.read(limit + 1)
            require(len(raw) == info.st_size and len(raw) <= limit)
        return raw
    finally:
        os.close(fd)


def snapshot(repository, expected_commit):
    require(type(expected_commit) is str and HEX40.fullmatch(expected_commit))
    with directory(repository) as fd:
        # Filter drivers may execute commands during status. Never allow them.
        config = git_read(fd, ['config', '--includes', '--null', '--list'])
        require(not any(item.split(b'\n', 1)[0].lower().startswith(b'filter.')
                        for item in config.split(b'\0') if item))
        require(git_read(fd, ['rev-parse', 'HEAD'], 128).decode().strip() == expected_commit)
        require(not git_read(fd, ['status', '--porcelain', '--untracked-files=all']).strip())
        records = git_read(fd, ['ls-tree', '-r', '-z', expected_commit]).split(b'\0')
        sources = {}
        for record in filter(None, records):
            header, raw_name = record.split(b'\t', 1)
            name = raw_name.decode('utf-8')
            relevant = name in FIXED_SOURCES or name.startswith(('backend/app/', 'backend/alembic/'))
            if not relevant:
                continue
            if not source_name(name):
                require(not name.startswith('backend/alembic/') and PurePosixPath(name).suffix not in {'.py', '.json'})
                continue
            mode, kind, oid = header.split(b' ')
            require(mode == b'100644' and kind == b'blob' and HEX40.fullmatch(oid.decode()))
            require(name not in sources and len(sources) < MAX_SOURCE_FILES)
            raw = git_read(fd, ['cat-file', 'blob', oid.decode()], MAX_SOURCE_FILE)
            require(read_at(fd, name, MAX_SOURCE_FILE) == raw)
            sources[name] = raw
            require(sum(map(len, sources.values())) <= MAX_SOURCE_TOTAL)
        require(not git_read(fd, ['status', '--porcelain', '--untracked-files=all']).strip())
        require(git_read(fd, ['rev-parse', 'HEAD'], 128).decode().strip() == expected_commit)
    validate_sources(sources)
    return sources


def write_file(root_fd, name, raw):
    parts = path_parts(name)
    fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, mode=0o755, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            previous, fd = fd, child
            os.close(previous)
        output = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=fd)
        with os.fdopen(output, 'wb') as stream:
            require(stream.write(raw) == len(raw))
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)


def inventory_tree(root_fd):
    files, directories = set(), set()
    identities = {}
    total = 0
    def walk(fd, prefix):
        nonlocal total
        with os.scandir(fd) as entries:
            for entry in entries:
                name = prefix + entry.name
                path_parts(name)
                info = entry.stat(follow_symlinks=False)
                identities[name] = (*identity(info), info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                if stat.S_ISDIR(info.st_mode):
                    require(name not in directories and len(directories) < MAX_CONTEXT_FILES)
                    directories.add(name)
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try: walk(child, name + '/')
                    finally: os.close(child)
                else:
                    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and name not in files)
                    files.add(name); total += info.st_size
                    require(len(files) <= MAX_CONTEXT_FILES and total <= MAX_CONTEXT_BYTES)
    walk(root_fd, '')
    return files, directories, identities


def canonical(data):
    return (json.dumps(data, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode()


def verify(context, expected_commit, expected_manifest_sha256):
    try:
        require(type(expected_commit) is str and HEX40.fullmatch(expected_commit) and
                type(expected_manifest_sha256) is str and HEX64.fullmatch(expected_manifest_sha256))
        with directory(context) as fd:
            raw = read_at(fd, MANIFEST, MAX_MANIFEST)
            require(digest(raw) == expected_manifest_sha256)
            manifest = json_value(raw)
            require(type(manifest) is dict and set(manifest) == {
                'format', 'source_commit', 'platform', 'base_image', 'base_config_digest',
                'required_db_revision', 'migration_count', 'source_file_count', 'source_size_bytes',
                'closure_report_sha256', 'files', 'database_connected', 'image_built'})
            require(raw == canonical(manifest) and manifest['format'] == FORMAT and
                    manifest['source_commit'] == expected_commit and manifest['platform'] == 'linux/amd64' and
                    manifest['base_image'] == BASE and manifest['base_config_digest'] == BASE_CONFIG and
                    manifest['required_db_revision'] == REVISION and type(manifest['migration_count']) is int and
                    manifest['migration_count'] == 30 and manifest['database_connected'] is False and
                    manifest['image_built'] is False and type(manifest['closure_report_sha256']) is str and
                    HEX64.fullmatch(manifest['closure_report_sha256']))
            entries = manifest['files']
            require(type(entries) is dict and 0 < len(entries) <= MAX_CONTEXT_FILES - 1)
            files, directories, identities = inventory_tree(fd)
            expected_dirs = set()
            sources = {}; wheel_entries = {}
            for name, item in entries.items():
                path_parts(name)
                expected_dirs.update(str(p) for p in PurePosixPath(name).parents if str(p) != '.')
                require(type(item) is dict and set(item) == {'source', 'size_bytes', 'sha256'} and
                        type(item['size_bytes']) is int and 0 <= item['size_bytes'] and
                        type(item['sha256']) is str and HEX64.fullmatch(item['sha256']))
                source = item['source']
                if source is None:
                    require(name.startswith('wheels/') and name.count('/') == 1 and
                            item['size_bytes'] <= wheels.MAX_WHEEL)
                    wheel_entries[name] = item
                else:
                    require(type(source) is str and source_name(source) and context_name(source) == name and
                            source not in sources and item['size_bytes'] <= MAX_SOURCE_FILE)
                    content = read_at(fd, name, MAX_SOURCE_FILE)
                    require(len(content) == item['size_bytes'] and digest(content) == item['sha256'])
                    sources[source] = content
            require(files == set(entries) | {MANIFEST} and directories == expected_dirs)
            checked = validate_sources(sources)
            require(type(manifest['source_file_count']) is int and manifest['source_file_count'] == len(sources) and
                    type(manifest['source_size_bytes']) is int and
                    manifest['source_size_bytes'] == sum(map(len, sources.values())))
            expected_wheels = {'wheels/' + a['filename']: {'source': None, 'size_bytes': a['size_bytes'], 'sha256': a['sha256']}
                               for a in checked['inventory']['artifacts']}
            require(wheel_entries == expected_wheels)
            for name, item in wheel_entries.items():
                content = read_at(fd, name, wheels.MAX_WHEEL)
                require(len(content) == item['size_bytes'] and digest(content) == item['sha256'])
            require(inventory_tree(fd) == (files, directories, identities))
            require(read_at(fd, MANIFEST, MAX_MANIFEST) == raw)
        return {'status': 'MIGRATION_INPUTS_VERIFIED_NOT_EXECUTED', 'source_commit': expected_commit,
                'manifest_sha256': expected_manifest_sha256, 'migration_count': 30,
                'database_connected': False, 'image_built': False}
    except (Exception, KeyboardInterrupt):
        raise Blocked('MIGRATION_INPUTS_BLOCKED') from None


def prepare(repository, expected_commit, wheelhouse, destination):
    try:
        require(type(expected_commit) is str and HEX40.fullmatch(expected_commit))
        sources = snapshot(repository, expected_commit)
        checked = validate_sources(sources)
        with wheel_directories():
            wheels.verify_artifacts(checked['inventory'], wheelhouse)
        destination = Path(destination)
        require(destination.name not in ('', '.', '..') and '..' not in destination.parts)
        # Retain every partial directory, including mkdir/open/write/close uncertainty.
        with directory(destination.parent) as parent_fd:
            os.mkdir(destination.name, mode=0o700, dir_fd=parent_fd)
            fd = os.open(destination.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
            try:
                output_identity = identity(os.fstat(fd))
                entries = {}
                for source, raw in sorted(sources.items()):
                    name = context_name(source)
                    write_file(fd, name, raw)
                    entries[name] = {'source': source, 'size_bytes': len(raw), 'sha256': digest(raw)}
                with directory(wheelhouse) as wheel_fd:
                    for artifact in checked['inventory']['artifacts']:
                        raw = read_at(wheel_fd, artifact['filename'], wheels.MAX_WHEEL)
                        require(len(raw) == artifact['size_bytes'] and digest(raw) == artifact['sha256'])
                        name = 'wheels/' + artifact['filename']
                        write_file(fd, name, raw)
                        entries[name] = {'source': None, 'size_bytes': len(raw), 'sha256': digest(raw)}
                # Existing verifier operates on the completed, no-follow copied bytes.
                closure = verify_wheel_closure(destination.absolute(), sources['scripts/offline_python_wheelhouse.py'],
                                               sources['scripts/offline_migration_context.py'])
                require(type(closure) is dict and closure.get('status') == 'OFFLINE_PIP_CLOSURE_VERIFIED' and
                        type(closure.get('wheel_count')) is int and closure['wheel_count'] == 30 and
                        type(closure.get('closure_report_sha256')) is str and HEX64.fullmatch(closure['closure_report_sha256']))
                manifest = {'format': FORMAT, 'source_commit': expected_commit, 'platform': 'linux/amd64',
                            'base_image': BASE, 'base_config_digest': BASE_CONFIG, 'required_db_revision': REVISION,
                            'migration_count': 30, 'source_file_count': len(sources),
                            'source_size_bytes': sum(map(len, sources.values())),
                            'closure_report_sha256': closure['closure_report_sha256'], 'files': entries,
                            'database_connected': False, 'image_built': False}
                raw = canonical(manifest)
                require(len(raw) <= MAX_MANIFEST)
                write_file(fd, MANIFEST, raw)
                os.fsync(fd)
                receipt = verify(destination, expected_commit, digest(raw))
                require(identity(os.stat(destination.name, dir_fd=parent_fd, follow_symlinks=False)) == output_identity)
            finally:
                os.close(fd)
        return {**receipt, 'status': 'MIGRATION_INPUTS_PREPARED_NOT_EXECUTED'}
    except (Exception, KeyboardInterrupt):
        raise Blocked('MIGRATION_INPUTS_BLOCKED') from None


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Blocked('MIGRATION_INPUTS_BLOCKED')


def main(argv=None):
    parser = Parser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    prepare_parser = actions.add_parser('prepare')
    for name in ('repository', 'wheelhouse', 'destination'):
        prepare_parser.add_argument('--' + name, required=True, type=Path)
    prepare_parser.add_argument('--expected-commit', required=True)
    verify_parser = actions.add_parser('verify')
    verify_parser.add_argument('--context', required=True, type=Path)
    verify_parser.add_argument('--expected-commit', required=True)
    verify_parser.add_argument('--expected-manifest-sha256', required=True)
    try:
        args = parser.parse_args(argv)
        result = (prepare(args.repository, args.expected_commit, args.wheelhouse, args.destination)
                  if args.action == 'prepare' else verify(args.context, args.expected_commit, args.expected_manifest_sha256))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print('MIGRATION_INPUTS_BLOCKED', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
