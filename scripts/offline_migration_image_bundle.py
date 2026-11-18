#!/usr/bin/env python3
"""Default-off migration image transfer; independent read-only verify.

Export explicitly runs the unchanged connected builder, then saves its same-run
immutable ID once. No saved receipt input, load, push, retry or daemon cleanup.
Caller trusts reviewed clean source, local UID and daemon. Hashes are not signatures.
"""
from contextlib import ExitStack, contextmanager
import hashlib
import json
import argparse
import re
import tempfile
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import tarfile
import time

import offline_image_bundle as base

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 'slc-migration-image-handoff-v2'
IMAGE_SOURCE = 'e2038a9462770a29254674dd86c0e7b26b26a221'
REVISION = '0030_private_upload_sessions'
SOURCE_REVISIONS = {'e2038a9462770a29254674dd86c0e7b26b26a221': '0030_private_upload_sessions'}
BUILDER_FORMAT = 'slc-offline-migration-image-rehearsal-v1'
BUILDER_SUCCESS = 'MIGRATION_IMAGE_SMOKE_PASSED_NOT_DATABASE_ACCEPTANCE'
EXPORTED = 'MIGRATION_IMAGE_BUNDLE_EXPORTED_NOT_OFFLINE_ACCEPTANCE'
VERIFIED = 'MIGRATION_IMAGE_BUNDLE_VERIFIED_NOT_OFFLINE_ACCEPTANCE'
FILES = frozenset({'migration.tar', 'manifest.json', 'evidence.json'})
MAX_BYTES = base.MAX_TOTAL_BYTES
require = base.require

LIMITATIONS = ('Connected image preparation only; no Alembic command, SQL, database, application, '
               'physical host network isolation, backup/restore or company acceptance. '
               'Caller trusts the reviewed checkout and local daemon; hashes are not signatures. '
               'No hostile same-UID protection, exact base-layer bandwidth claim or retained download.')


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


def command(args, *, env, timeout, limit=65536, stdin=None, cwd=ROOT, cleanup_grace=0):
    """Bound output before accumulating; stderr is discarded, never published.

    Killing the CLI does not prove daemon-side build/pull work stopped. A timeout
    is an uncertain failure, never permission to repeat or prune daemon objects.
    """
    require(0 < timeout <= 3300 and type(limit) is int and 0 < limit <= 2*1024**2)
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
        except subprocess.TimeoutExpired: raise base.BundleError('COMMAND_TIMEOUT_UNCERTAIN') from None
        return code, bytes(output)
    finally:
        if process.returncode is None and cleanup_grace:
            # Give the original builder's SIGTERM handler/finally a bounded
            # opportunity to remove its own CIDs. Failure remains uncertain.
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=cleanup_grace)
            except subprocess.TimeoutExpired: pass
        if process.returncode is None:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait(timeout=2)
        process.stdout.close()


SAFE_ENV = {'LANG', 'PYTHON_SHA256', 'GPG_KEY', 'PYTHON_VERSION', 'PYTHON_PIP_VERSION', 'PATH', 'PYTHON_SETUPTOOLS_VERSION'}
exact = base.exact
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



@contextmanager
def bounded(seconds):
    """Bound filesystem/hash/parser work too; preserve rather than replace timers."""
    require(type(seconds) in (int, float) and 0 < seconds <= 3300)
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0))
    deadline = time.monotonic() + seconds
    previous = signal.getsignal(signal.SIGALRM)
    attempted = False
    def expired(_signum, _frame):
        raise base.BundleError('BUNDLE_IO_FAILED')
    try:
        attempted = True
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        if attempted:
            try:signal.setitimer(signal.ITIMER_REAL, 0)
            finally:signal.signal(signal.SIGALRM, previous)
    require(time.monotonic() < deadline, 'BUNDLE_IO_FAILED')


# The original builder's import closure, checked before Python imports it.
BUILD_FILES = (
    'offline_migration_image_rehearsal', 'offline_migration_context',
    'offline_python_wheelhouse', 'offline_image_rehearsal', 'offline_image_bundle',
    'offline_readonly_preflight', 'offline_npm_artifacts', 'offline_npm_inventory')


def clean_env():
    return {'PATH':os.defpath, 'LANG':'C.UTF-8', 'HOME':'/nonexistent',
            'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_GLOBAL':'/dev/null',
            'GIT_NO_REPLACE_OBJECTS':'1', 'GIT_OPTIONAL_LOCKS':'0',
            'GIT_NO_LAZY_FETCH':'1','GIT_TERMINAL_PROMPT':'0'}


def git(root, *args, limit=2*1024**2):
    code, raw = command(['/usr/bin/git','--no-pager','--no-replace-objects','--no-lazy-fetch',
                         '-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null','-C',str(root),*args],
                        env=clean_env(), timeout=30, limit=limit, cwd=root)
    require(code == 0)
    return raw


def checkout(root, commit, modules):
    require(base.hexadecimal(commit,40))
    root = Path(root)
    require(root.is_absolute() and root.resolve(strict=True) == root)
    config=git(root,'config','--includes','--null','--list')
    require(not any(item.split(b'\n',1)[0].lower().startswith(b'filter.')
                    for item in config.split(b'\0') if item))
    require(git(root,'rev-parse','HEAD').decode().strip() == commit)
    require(not git(root,'status','--porcelain','--untracked-files=all').strip())
    with ExitStack() as stack:
        directory = base.Directory.open(root/'scripts',stack)
        # Refuse ignored caches/shadow modules before any child imports source.
        expected=git(root,'ls-tree','--name-only','-z',commit+':scripts').split(b'\0')
        directory.names({name.decode() for name in expected if name})
        for name in modules:
            path='scripts/'+name+'.py'
            listing=git(root,'ls-tree',commit,'--',path).decode().strip()
            require(listing.startswith('100644 blob ') and listing.endswith('\t'+path))
            raw=git(root,'show',commit+':'+path,limit=1024**2)
            file=base.File(directory,name+'.py',stack)
            require(base.read_bytes(file,1024**2) == raw)
    return root


def source_binding(tool_commit, source_directory):
    require(Path(__file__).absolute() == ROOT/'scripts/offline_migration_image_bundle.py')
    require(Path(base.__file__).absolute() == ROOT/'scripts/offline_image_bundle.py')
    require(Path(base.preflight.__file__).absolute() == ROOT/'scripts/offline_readonly_preflight.py')
    checkout(ROOT,tool_commit,('offline_migration_image_bundle','offline_image_bundle','offline_readonly_preflight'))
    checkout(source_directory,IMAGE_SOURCE,BUILD_FILES)


def build_once(source_directory, budget):
    # No saved receipt input. Only stdout from this exact invocation is accepted.
    env=clean_env()
    env['MIGRATION_REHEARSAL_STARTED_NS']=os.environ['MIGRATION_REHEARSAL_STARTED_NS']
    program=('import sys; sys.path.insert(0, sys.argv[1]); '
             'import offline_migration_image_rehearsal as b; '
             'raise SystemExit(b.main(["--run","--expected-commit",sys.argv[2]]))')
    code, raw=command([sys.executable,'-I','-S','-B','-c',program,
                       str(Path(source_directory)/'scripts'),IMAGE_SOURCE],
                      env=env,timeout=budget.allowance(3300,1350),
                      cwd=source_directory,cleanup_grace=90)
    require(code == 0)
    return base.parse_json(raw)


def validate_receipt(value, commit):
    require(commit == IMAGE_SOURCE)
    require(type(value) is dict and set(value) == {'format','status','source_commit',
        'context_manifest_sha256','build_context_sha256','image_id','platform','wheel_count',
        'migration_count','source_file_count','default_exit_code','containers_removed',
        'database_connected','migrations_executed','limitations'})
    expected = {'format':BUILDER_FORMAT, 'status':BUILDER_SUCCESS, 'source_commit':commit,
        'platform':'linux/amd64','wheel_count':30,'migration_count':30,'default_exit_code':1,
        'containers_removed':2,'database_connected':False,'migrations_executed':False,
        'limitations':LIMITATIONS}
    require(all(base.exact(value[key], item) for key,item in expected.items()))
    require(all(base.hexadecimal(value[key],64) for key in ('context_manifest_sha256','build_context_sha256')))
    require(type(value['image_id']) is str and re.fullmatch('sha256:[0-9a-f]{64}',value['image_id']))
    require(type(value['source_file_count']) is int and 0 < value['source_file_count'] <= 512)


def evidence(commit):
    return {'format':'slc-migration-image-handoff-evidence-v1','source_commit':commit,
        'status':BUILDER_SUCCESS,'checks':{'same_run_builder':True,'containers_removed':2,
        'strict_archive':True,'migration_config':True},
        'database_connected':False,'migrations_executed':False,
        'limitations':['No PostgreSQL image or database acceptance','No offline installation acceptance',
                      'No signature or publisher authentication','No hostile same-UID protection']}


def check_item(item, commit):
    require(type(item) is dict and set(item) == {'archive','size','sha256','image_id','platform','source_commit'})
    require(base.exact(item['archive'],'migration.tar') and base.exact(item['platform'],'linux/amd64')
            and base.exact(item['source_commit'],commit) and type(item['size']) is int
            and 0 < item['size'] <= MAX_BYTES and base.hexadecimal(item['sha256'],64)
            and type(item['image_id']) is str and re.fullmatch('sha256:[0-9a-f]{64}',item['image_id']))


def archive_gate(file, item, commit):
    base.archive_gate(file, item, commit)
    path = base.PinnedArchive(file)
    with tarfile.open(path, mode='r:') as archive:
        record = base.parse_json(archive.extractfile('manifest.json').read())[0]
        config_member = archive.getmember(record['Config'])
        require(config_member.size <= 8 * 1024**2)
        with archive.extractfile(config_member) as stream:
            config = base.parse_json(stream.read())
        verify_image([{'Id':item['image_id'],'Os':config.get('os'),
            'Architecture':config.get('architecture'),'Variant':config.get('variant'),
            'Config':config.get('config')}],item['image_id'],commit)
    file.check()


def verify_files(directory, files, commit, digest, completed):
    names = FILES | ({'COMPLETE'} if completed else set())
    directory.names(names)
    raw = base.read_bytes(files['manifest.json'], base.MAX_JSON_BYTES)
    require(hashlib.sha256(raw).hexdigest() == digest)
    manifest = base.parse_json(raw)
    require(type(manifest) is dict and set(manifest) == {'format','source_commit','tool_commit','required_db_revision','image','evidence_sha256',
            'context_manifest_sha256','build_context_sha256'})
    require(base.hexadecimal(manifest['tool_commit'],40) and commit == IMAGE_SOURCE
            and manifest['required_db_revision'] == SOURCE_REVISIONS[commit])
    require(base.exact(manifest['format'],FORMAT) and base.exact(manifest['source_commit'],commit)
            and all(base.hexadecimal(manifest[key],64) for key in
                    ('evidence_sha256','context_manifest_sha256','build_context_sha256')))
    check_item(manifest['image'],commit)
    raw = base.read_bytes(files['evidence.json'],base.MAX_JSON_BYTES)
    require(hashlib.sha256(raw).hexdigest() == manifest['evidence_sha256']
            and base.exact(base.parse_json(raw),evidence(commit)))
    archive_gate(files['migration.tar'],manifest['image'],commit)
    for file in files.values():file.check()
    directory.names(names)


def verify_bundle(directory, *, expected_commit, expected_manifest_sha256):
    try:
        require(base.hexadecimal(expected_commit,40) and base.hexadecimal(expected_manifest_sha256,64))
        with bounded(600), ExitStack() as stack:
            root = base.Directory.open(directory,stack)
            root.names(FILES | {'COMPLETE'})
            marker = base.File(root,'COMPLETE',stack)
            require(marker.initial.st_size == 0)
            files = {name:base.File(root,name,stack) for name in sorted(FILES)}
            manifest=base.parse_json(base.read_bytes(files['manifest.json'],base.MAX_JSON_BYTES))
            require(manifest.get('tool_commit') == expected_commit)
            verify_files(root,files,IMAGE_SOURCE,expected_manifest_sha256,True)
            marker.check(); root.names(FILES | {'COMPLETE'})
        return {'status':VERIFIED,'tool_commit':expected_commit,'image_source_commit':IMAGE_SOURCE,
                'required_db_revision':REVISION,'manifest_sha256':expected_manifest_sha256}
    except (Exception,KeyboardInterrupt):
        raise base.BundleError('BUNDLE_IO_FAILED') from None


def save_image(file, image_id, budget, env):
    """Stream one immutable-ID save; bound bytes, time and shutdown, never retry."""
    docker = shutil.which('docker',path=os.defpath)
    require(docker is not None)
    deadline = time.monotonic() + budget.allowance(600, 630)
    process = subprocess.Popen([docker,'--host=unix:///var/run/docker.sock','image','save',image_id],
        env=env,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,start_new_session=True)
    total = 0
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout,selectors.EVENT_READ)
            while selector.get_map():
                require(time.monotonic() < deadline,'BUNDLE_IO_FAILED')
                for key,_ in selector.select(min(.1,max(.001,deadline-time.monotonic()))):
                    raw = os.read(key.fileobj.fileno(),base.CHUNK)
                    if not raw:selector.unregister(key.fileobj)
                    else:
                        total += len(raw); require(total <= MAX_BYTES,'BUNDLE_CAPACITY_REJECTED')
                        base.write_bytes(file,raw)
            require(time.monotonic() < deadline,'BUNDLE_IO_FAILED')
            require(process.wait(timeout=max(.001,deadline-time.monotonic())) == 0,'BUNDLE_IO_FAILED')
        require(total > 0)
        file.written()
    finally:
        try:
            if process.returncode is None:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait(timeout=2)
        finally:process.stdout.close()


def digest_file(file):
    file.check(); os.lseek(file.fd,0,os.SEEK_SET)
    digest = hashlib.sha256(); total = 0
    while raw := os.read(file.fd,base.CHUNK):
        total += len(raw); require(total <= MAX_BYTES)
        digest.update(raw)
    require(total == file.initial.st_size and total > 0)
    file.check(); return digest.hexdigest()


def _run(commit,destination,state,source_directory):
    require(base.hexadecimal(commit,40))
    base.check_destination(destination)
    budget = Budget.from_environment()
    state['budget'] = budget
    stamp = os.environ.get('MIGRATION_REHEARSAL_STARTED_NS')
    with bounded(budget.allowance(600)):
        source_binding(commit,source_directory)
    receipt = build_once(source_directory,budget)  # Only fresh return value is runtime authority.
    validate_receipt(receipt,IMAGE_SOURCE)
    require(os.environ.get('MIGRATION_REHEARSAL_STARTED_NS') == stamp)
    budget.reserve(1260)
    with bounded(budget.allowance(600,1260)):
        source_binding(commit,source_directory)
    parts = base.path_parts(destination)
    with bounded(budget.allowance(1260)), ExitStack() as stack:
        parent = base.Directory.open('/'+'/'.join(parts[:-1]),stack)
        space = os.fstatvfs(parent.fd)
        require(space.f_bavail * space.f_frsize >= MAX_BYTES + base.RESERVE_BYTES,'BUNDLE_CAPACITY_REJECTED')
        parent.check(); os.mkdir(parts[-1],mode=0o700,dir_fd=parent.fd)
        directory = parent.child(parts[-1],stack); directory.names(set())
        # A private empty Docker config, outside transferred data, without credentials.
        with tempfile.TemporaryDirectory(prefix='slc-migration-save-') as config:
            env = {'PATH':os.defpath,'HOME':'/nonexistent','LANG':'C.UTF-8','DOCKER_CONFIG':config}
            files = {'migration.tar':base.File(directory,'migration.tar',stack,create=True)}
            save_image(files['migration.tar'],receipt['image_id'],budget,env)
        # Shorten the active tail timer after save; never extend/reset its deadline.
        remaining, interval = signal.getitimer(signal.ITIMER_REAL)
        require(remaining > 0 and interval == 0)
        limit = min(remaining, budget.allowance(600))
        state['verification_deadline'] = time.monotonic() + limit
        signal.setitimer(signal.ITIMER_REAL, limit)
        safe = base.canonical(evidence(IMAGE_SOURCE))
        item = {'archive':'migration.tar','size':files['migration.tar'].initial.st_size,
            'sha256':digest_file(files['migration.tar']),'image_id':receipt['image_id'],
            'platform':'linux/amd64','source_commit':IMAGE_SOURCE}
        check_item(item,IMAGE_SOURCE)
        raw = base.canonical({'format':FORMAT,'source_commit':IMAGE_SOURCE,'tool_commit':commit,
            'required_db_revision':REVISION,'image':item,
            'context_manifest_sha256':receipt['context_manifest_sha256'],
            'build_context_sha256':receipt['build_context_sha256'],
                              'evidence_sha256':hashlib.sha256(safe).hexdigest()})
        digest = hashlib.sha256(raw).hexdigest()
        state['receipt'] = {'source_commit':commit,'manifest_sha256':digest}
        for name,data in [('evidence.json',safe),('manifest.json',raw)]:
            files[name]=base.File(directory,name,stack,create=True)
            base.write_bytes(files[name],data);files[name].written()
        verify_files(directory,files,IMAGE_SOURCE,digest,False)
        budget.reserve(0)
        for file in files.values():file.handle.close()
        directory.names(FILES);os.fsync(directory.fd)
        state['completion_attempted']=True
        marker=base.File(directory,'COMPLETE',stack,create=True)
        marker.handle.close()
    return {'status':EXPORTED,'tool_commit':commit,'image_source_commit':IMAGE_SOURCE,
            'required_db_revision':REVISION,'manifest_sha256':digest}


def run(commit,destination,source_directory):
    state = {'completion_attempted':False}
    original = os.environ.get('MIGRATION_REHEARSAL_STARTED_NS')
    previous = None
    attempted = False
    try:
        try:
            if original is None:os.environ['MIGRATION_REHEARSAL_STARTED_NS']=str(time.monotonic_ns())
            previous = signal.getsignal(signal.SIGTERM)
            def interrupted(_signum,_frame):raise KeyboardInterrupt()
            attempted=True;signal.signal(signal.SIGTERM,interrupted)
            result=_run(commit,destination,state,source_directory)
        finally:
            try:
                if attempted:signal.signal(signal.SIGTERM,previous)
            finally:
                if original is None:os.environ.pop('MIGRATION_REHEARSAL_STARTED_NS',None)
                else:os.environ['MIGRATION_REHEARSAL_STARTED_NS']=original
        state['budget'].reserve(0)
        require(time.monotonic() < state['verification_deadline'], 'BUNDLE_COMPLETION_UNCERTAIN')
        return result
    except (Exception,KeyboardInterrupt,SystemExit):
        code='BUNDLE_COMPLETION_UNCERTAIN' if state['completion_attempted'] else 'BUNDLE_IO_FAILED'
        raise base.BundleError(code,receipt=state.get('receipt')) from None


class Parser(argparse.ArgumentParser):
    def error(self, _message): raise base.BundleError("ARGUMENTS_REJECTED")


def emit(stream, value):
    text=value+'\n'
    require(stream.write(text) == len(text),'BUNDLE_IO_FAILED')
    stream.flush()


def main(argv=None):
    completed = None
    try:
        parser=Parser(description=__doc__,allow_abbrev=False)
        parser.add_argument('mode',choices=['export','verify'])
        parser.add_argument('--run',action='store_true')
        parser.add_argument('--expected-commit',required=True)
        parser.add_argument('--destination')
        parser.add_argument('--source-directory')
        parser.add_argument('--directory')
        parser.add_argument('--expected-manifest-sha256')
        args=parser.parse_args(argv)
        if args.mode == 'export':
            require(args.run and args.destination and args.source_directory and args.directory is None and args.expected_manifest_sha256 is None)
            result=run(args.expected_commit,args.destination,args.source_directory)
            completed=base.safe_receipt({'source_commit':result['tool_commit'],'manifest_sha256':result['manifest_sha256']})
        else:
            require(not args.run and args.source_directory is None and args.directory and args.destination is None and args.expected_manifest_sha256)
            result=verify_bundle(args.directory,expected_commit=args.expected_commit,
                expected_manifest_sha256=args.expected_manifest_sha256)
        emit(sys.stdout,json.dumps(result,sort_keys=True));return 0
    except (Exception,KeyboardInterrupt,SystemExit) as error:
        if isinstance(error,SystemExit) and completed is None:
            raise
        receipt=completed or base.safe_receipt(getattr(error,'receipt',None))
        try:
            emit(sys.stderr,'MIGRATION_BUNDLE_BLOCKED_OR_UNCERTAIN; preserve partial output; no retry, load or offline acceptance.')
            if receipt is not None and (completed is not None or getattr(error,'code',None) == 'BUNDLE_COMPLETION_UNCERTAIN'):
                emit(sys.stderr,json.dumps({'status':'BUNDLE_COMPLETION_UNCERTAIN','tool_commit':receipt['source_commit'],
                                           'manifest_sha256':receipt['manifest_sha256']},sort_keys=True))
        except (Exception,KeyboardInterrupt,SystemExit):
            pass
        return 2

if __name__ == '__main__':sys.exit(main())
