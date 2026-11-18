#!/usr/bin/env python3
"""Build a source-only receiver zipapp from exact committed Git blobs.

Default-inert. No image build, network, upload, extraction or runtime installation.
Trusted local Linux filesystem only; partial outputs are retained, never retried.
"""
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import zipfile

MODULES = ('offline_image_bundle', 'offline_media_retention', 'offline_media_transport',
           'offline_operator_assembly', 'offline_readonly_preflight', 'offline_postgres_image_bundle', 'offline_migration_image_bundle')
IMAGE_SOURCE = 'e2038a9462770a29254674dd86c0e7b26b26a221'
REVISION = '0030_private_upload_sessions'
MAX_SOURCE_BYTES = 2 * 1024**2
MAX_TOOLKIT_BYTES = 4 * 1024**2
ENTRY = b'''"""Source-only receiver toolkit; verify independent archive hash before execution."""
import importlib
import sys
COMMANDS = {'bundle':'offline_image_bundle', 'transport':'offline_media_transport',
            'assembly':'offline_operator_assembly', 'retention':'offline_media_retention',
            'preflight':'offline_readonly_preflight', 'postgres-verify':'offline_postgres_image_bundle',
            'migration-verify':'offline_migration_image_bundle'}
if len(sys.argv) == 1 or sys.argv[1:] == ['--help']:
    print('Receiver toolkit: bundle | transport | assembly | retention | preflight | postgres-verify | migration-verify; append --help. Requires Linux/Python3.12+, /proc/self/fd. No runtime included. Verify trusted toolkit SHA256 before execution; media hashes are separate.')
    raise SystemExit(0)
if sys.platform != 'linux' or sys.version_info < (3,12) or sys.argv[1] not in COMMANDS:
    print('RECEIVER_COMMAND_OR_PLATFORM_REJECTED', file=sys.stderr)
    raise SystemExit(2)
arguments = sys.argv[2:]
if sys.argv[1] in ('postgres-verify','migration-verify'):
    arguments = ['verify', *arguments]
raise SystemExit(importlib.import_module(COMMANDS[sys.argv[1]]).main(arguments))
'''
README = b'''SOURCE-ONLY RECEIVER TOOLKIT
Use an independently trusted SHA256 of this entire .pyz before running it.
A hash calculated only from a received package does not establish trust.
python3 -I -S receiver.pyz --help
python3 -I -S receiver.pyz transport --help
postgres-verify and migration-verify fix verify mode; export, --run and --destination are rejected.
Other existing CLI arguments and refusal behavior are unchanged. No extraction of
this tool archive is needed. Python3.12+, Linux and /proc/self/fd must already be
available; Python, OS, Docker, Compose, PostgreSQL and images are NOT included.
This is not a Windows runtime installer, company installation or content clearance.
TOOLKIT.json binds exact module bytes to a tool commit, not an image commit and
not a signature. The API/Web image source remains e2038a94/schema0030.
PostgreSQL uses its separate fixed official digest, not the API/Web source commit.
Its expected-commit binds the separately trusted handoff tool-source receipt.
Keep toolkit SHA256, media transport SHA256 and trusted handoff manifest SHA256
separate. The latter two must come from the independently trusted media receipt.
No credentials, databases, logs, site-packages or broad workspace contents included.
A failed/uncertain build leaves its output for inspection; never overwrite/retry.
'''

class ToolkitError(ValueError):
    def __init__(self):
        super().__init__('RECEIVER_TOOLKIT_REJECTED_OR_UNCONFIRMED')


def require(condition):
    if not condition:
        raise ToolkitError()


def git(root, *args):
    env = {'PATH': os.environ.get('PATH',''), 'LANG':'C.UTF-8',
           'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_GLOBAL':os.devnull}
    result = subprocess.run(['git', '--no-replace-objects', *args], cwd=root, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30, check=True)
    return result.stdout


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',',':'))+'\n').encode()


def sources(root, commit):
    require(re.fullmatch('[0-9a-f]{40}', commit) is not None)
    require(git(root,'rev-parse','HEAD').decode().strip() == commit)
    values, constants = {}, {}
    for module in MODULES:
        path = 'scripts/'+module+'.py'
        listing = git(root,'ls-tree',commit,'--',path).decode().strip()
        require(listing.startswith('100644 blob ') and listing.endswith('\t'+path))
        size = int(git(root,'cat-file','-s',commit+':'+path))
        require(0 < size <= MAX_SOURCE_BYTES)
        raw = git(root,'show',commit+':'+path)
        require(len(raw) == size)
        tree = ast.parse(raw, filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [n.name.split('.')[0] for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                require(node.level == 0 and node.module is not None)
                names = [node.module.split('.')[0]]
            else:
                continue
            require(all(n in MODULES or n in sys.stdlib_module_names for n in names))
        # Check literal declarations in reviewed source. This static inspection
        # does not prove absence of dynamic imports or runtime mutations.
        wanted = {'IMAGE_SOURCE','SOURCE_REVISIONS','REVISION'}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in wanted:
                        key = (module,target.id)
                        require(key not in constants)
                        constants[key] = ast.literal_eval(node.value)
        values[module+'.py'] = raw
    require(constants.get(('offline_media_retention','IMAGE_SOURCE')) == IMAGE_SOURCE)
    require(constants.get(('offline_operator_assembly','SOURCE_REVISIONS')) == {IMAGE_SOURCE:REVISION})
    require(constants.get(('offline_readonly_preflight','REVISION')) == REVISION)
    require(constants.get(('offline_migration_image_bundle','IMAGE_SOURCE')) == IMAGE_SOURCE)
    require(constants.get(('offline_migration_image_bundle','REVISION')) == REVISION)
    require(constants.get(('offline_migration_image_bundle','SOURCE_REVISIONS')) == {IMAGE_SOURCE:REVISION})
    require(git(root,'rev-parse','HEAD').decode().strip() == commit)
    return values


def archive_bytes(values, commit):
    values = {**values, '__main__.py':ENTRY, 'README.txt':README}
    metadata = {'format':'slc-receiver-source-v1', 'tool_commit':commit,
                'image_source_commit':IMAGE_SOURCE, 'required_db_revision':REVISION,
                'runtime_included':False,
                'files':{n:{'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()} for n,v in values.items()}}
    values['TOOLKIT.json'] = canonical(metadata)
    require(sum(map(len,values.values())) <= MAX_TOOLKIT_BYTES - 65536)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED,allowZip64=False) as archive:
        for name, raw in sorted(values.items()):
            info = zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG|0o600) << 16
            archive.writestr(info,raw)
    result = stream.getvalue()
    require(len(result) <= MAX_TOOLKIT_BYTES)
    return result


def write_output(file, raw):
    require(file.write(raw) == len(raw))
    file.flush()
    os.fsync(file.fileno())
    file.seek(0)
    require(file.read(len(raw)+1) == raw)


def build(root, destination, *, expected_tool_commit):
    try:
        raw = archive_bytes(sources(root,expected_tool_commit),expected_tool_commit)
        target = Path(destination)
        require(target.is_absolute() and target.parent.resolve(strict=True) == target.parent)
        require(target.name not in ('','.','..'))
        # Trusted local storage/no concurrent mutation assumption. O_EXCL also
        # rejects existing symlinks. No parent mkdir, overwrite or cleanup.
        fd = os.open(target,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            file = os.fdopen(fd,'w+b')
        except BaseException:
            os.close(fd)
            raise
        try:
            write_output(file,raw)
        finally:
            active = sys.exc_info()[1]
            try:
                file.close()
            except BaseException:
                if not isinstance(active,(KeyboardInterrupt,SystemExit)):
                    raise
        # Only return after verified bytes, fsync and successful close.
        return {'status':'RECEIVER_SOURCE_TOOLKIT_CREATED_NOT_RUNTIME',
                'tool_commit':expected_tool_commit,'image_source_commit':IMAGE_SOURCE,
                'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                'runtime_included':False,'deployment_approved':False}
    except KeyboardInterrupt:
        raise KeyboardInterrupt('RECEIVER_TOOLKIT_INTERRUPTED_UNCONFIRMED') from None
    except Exception:
        raise ToolkitError() from None


def emit(stream, text):
    value = text+'\n'
    require(stream.write(value) == len(value))
    stream.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--source-root')
    parser.add_argument('--destination')
    parser.add_argument('--expected-tool-commit')
    args = parser.parse_args(argv)
    try:
        if not args.run:
            require(not any((args.source_root,args.destination,args.expected_tool_commit)))
            emit(sys.stdout,'DISABLED: explicit --run required; no toolkit created.')
            return 0
        require(all((args.source_root,args.destination,args.expected_tool_commit)))
        result = build(args.source_root,args.destination,expected_tool_commit=args.expected_tool_commit)
        emit(sys.stdout,json.dumps(result,sort_keys=True))
        return 0
    except (Exception,KeyboardInterrupt):
        try: emit(sys.stderr,'RECEIVER_TOOLKIT_REJECTED_OR_UNCONFIRMED: inspect any output; no automatic retry.')
        except (Exception,KeyboardInterrupt): pass
        return 2

if __name__ == '__main__': raise SystemExit(main())
