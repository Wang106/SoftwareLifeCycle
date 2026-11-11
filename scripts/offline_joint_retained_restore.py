#!/usr/bin/env python3
"""Bind and recover one own-synthetic DB/software pair through existing CLIs.

No arguments or --help performs no operations. Fixed private /tmp roots only.
A caller-retained digest checks integrity, not authenticity or hostile SQL safety.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import time
import stat
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
SOFTWARE_FILES = ('README.txt', 'firmware.bin', 'settings.json')
JSON_LIMIT = 65536
ARCHIVE_LIMIT = 64 * 1024 * 1024


class Rejected(Exception):
    pass


def require(condition):
    if not condition:
        raise Rejected('JOINT_REJECTED')


def matches(value, pattern):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def object_json(data):
    require(len(data) <= JSON_LIMIT)
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result)
            result[key] = value
        return result
    def reject_constant(_):
        raise Rejected('JOINT_REJECTED')
    try:
        value = json.loads(data, object_pairs_hook=pairs, parse_constant=reject_constant)
    except (ValueError, UnicodeError) as exc:
        raise Rejected("JOINT_REJECTED") from None
    require(isinstance(value, dict))
    return value


def root_fd(path):
    """Walk only fixed /tmp descendants, with no symlink traversal."""
    path = Path(path)
    require(path.is_absolute() and path.parts[:2] == ('/', 'tmp') and len(path.parts) > 2)
    require(all(part not in ('', '.', '..') for part in path.parts[2:]))
    fd = os.open('/tmp', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        current = os.fstat(fd)
        require(current.st_uid in (0, os.geteuid()))
        require(not current.st_mode & 0o022 or current.st_mode & stat.S_ISVTX)
        for part in path.parts[2:]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            previous, fd = fd, following
            os.close(previous)
            current = os.fstat(fd)
            require(current.st_uid == os.geteuid() and stat.S_IMODE(current.st_mode) == 0o700)
        return fd
    except BaseException:
        os.close(fd)
        raise


def file_state(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def read_file(root, name, limit=JSON_LIMIT):
    require(isinstance(name, str) and '/' not in name and name not in ('', '.', '..'))
    directory = root_fd(root)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == os.geteuid())
            require(stat.S_IMODE(before.st_mode) == 0o600 and 0 <= before.st_size <= limit)
            chunks, remaining = [], limit + 1
            while remaining:
                piece = os.read(fd, min(65536, remaining))
                if not piece:
                    break
                chunks.append(piece)
                remaining -= len(piece)
            data = b''.join(chunks)
            require(len(data) == before.st_size and len(data) <= limit)
            require(file_state(before) == file_state(os.fstat(fd)))
            require(file_state(before) == file_state(os.stat(name, dir_fd=directory, follow_symlinks=False)))
            return data
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def write_file(root, name, data):
    directory = root_fd(root)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        try:
            view = memoryview(data)
            while view:
                count = os.write(fd, view)
                require(count > 0)
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory)
    finally:
        os.close(directory)


def record_failure(root, report):
    # Best effort once. Diagnostic failure must never mask the primary failure,
    # including interruption; resources remain untouched and no write is retried.
    try:
        write_file(root, 'failure.json', encode(report))
    except BaseException:
        pass


def new_root(prefix):
    require(prefix in ('joint-rehearsal-', 'joint-recovery-'))
    root = Path('/tmp') / (prefix + secrets.token_hex(16))
    root.mkdir(mode=0o700, exist_ok=False)
    fd = root_fd(root)
    os.close(fd)
    return root


def capture(arguments, deadline):
    """Bound live pipe reads; reserve five seconds for owned-process shutdown."""
    stop = min(time.monotonic() + 300, deadline) - 5
    require(time.monotonic() < stop)
    process = subprocess.Popen([sys.executable, *map(str, arguments)], cwd=REPO / 'backend',
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, umask=0o077)
    output, sizes = bytearray(), {'stdout': 0, 'stderr': 0}
    try:
        with selectors.DefaultSelector() as selector:
            for name, stream in (('stdout', process.stdout), ('stderr', process.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map():
                remaining = stop - time.monotonic()
                require(remaining > 0)
                for key, _ in selector.select(min(remaining, 0.1)):
                    data = os.read(key.fd, 8192)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    sizes[key.data] += len(data)
                    require(sizes[key.data] <= JSON_LIMIT)
                    if key.data == 'stdout':
                        output.extend(data)
            require(process.wait(timeout=max(0.001, stop - time.monotonic())) == 0)
        return bytes(output)
    finally:
        # Touch only the Popen child, never names, other processes or DB targets.
        # Its descendants/resources may outlive it: completion remains uncertain.
        primary = sys.exc_info()[1]
        cleanup_error = None
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        except BaseException as exc:
            cleanup_error = exc
        for stream in (process.stdout, process.stderr):
            try:
                stream.close()
            except BaseException as exc:
                if cleanup_error is None:
                    cleanup_error = exc
        if primary is None and cleanup_error is not None:
            raise cleanup_error


def child(stage, arguments, *, deadline=None):
    # Neither credentials nor raw stdout/stderr/errors enter coordinator reports.
    return object_json(capture(arguments, time.monotonic() + 300 if deadline is None else deadline))


def db_names(run):
    require(matches(run, r'[0-9a-f]{12}'))
    return (f'postgresql-rehearsal-{run}.dump', f'postgresql-rehearsal-{run}-manifest.json',
            'postgresql-backup-restore-rehearsal.json', f'postgresql-rehearsal-{run}-ownership.json')


def software_receipt(value, recovery=False):
    expected = {'scope', 'status', 'run_id', 'file_count', 'total_bytes', 'manifest_sha256'}
    if recovery:
        expected.add('source_run_id')
    require(set(value) == expected and value['scope'] == 'SYNTHETIC_ONLY' and value['status'] == 'VERIFIED')
    prefix = 'software-recovery-' if recovery else 'software-rehearsal-'
    require(matches(value['run_id'], prefix + r'[0-9a-f]{32}'))
    require(type(value['file_count']) is int and value['file_count'] == len(SOFTWARE_FILES))
    require(type(value['total_bytes']) is int and 0 < value['total_bytes'] <= 8192)
    require(matches(value['manifest_sha256'], r'[0-9a-f]{64}'))
    if recovery:
        require(matches(value['source_run_id'], r'software-rehearsal-[0-9a-f]{32}'))


def snapshot(pair_root, db_run, software):
    """Hash only known child outputs; never accept disk-supplied paths."""
    software_receipt(software)
    database = pair_root / 'database'
    db_files = {name: digest(read_file(database, name, ARCHIVE_LIMIT if name.endswith('.dump') else JSON_LIMIT))
                for name in db_names(db_run)}
    sw_root = Path('/tmp') / software['run_id']
    sw_files = {name: digest(read_file(sw_root / 'bundle', name, 8192))
                for name in (*SOFTWARE_FILES, 'manifest.json')}
    result_bytes = read_file(sw_root, 'result.json')
    require(object_json(result_bytes) == software)
    require(sw_files['manifest.json'] == software['manifest_sha256'])
    sw_files['result.json'] = digest(result_bytes)
    require(sum(len(read_file(sw_root / 'bundle', name, 8192)) for name in SOFTWARE_FILES) == software['total_bytes'])
    return {'database': db_files, 'software': sw_files}


def validate_db(root, run, receipt):
    archive, manifest_name, baseline_name, proof_name = db_names(run)
    manifest = object_json(read_file(root / 'database', manifest_name))
    baseline = object_json(read_file(root / 'database', baseline_name))
    proof = object_json(read_file(root / 'database', proof_name))
    require(set(receipt) == {'status', 'run_id', 'source_commit', 'cleanup'})
    require(receipt == {'status': 'passed', 'run_id': run, 'source_commit': manifest.get('source_commit'),
                        'cleanup': 'owned_databases_dropped'})
    require(manifest.get('run_id') == baseline.get('run_id') == run)
    require(baseline.get('status') == 'passed' and baseline.get('cleanup') == 'owned_databases_dropped')
    require(manifest.get('archive_file') == archive and baseline.get('manifest') == manifest_name)
    require(manifest.get('ownership_proof') == baseline.get('ownership_proof') == proof_name)
    for key in ('source_commit', 'checkout_commit'):
        require(matches(manifest.get(key), r'[0-9a-f]{40}') and manifest[key] == baseline.get(key))
    require(proof.get('run_id') == run)
    dropped = proof.get('dropped_databases')
    require(isinstance(dropped, list) and len(dropped) == 2)
    require({item.get('role') for item in dropped if isinstance(item, dict)} == {'source', 'target'})
    return {'source_commit': manifest['source_commit'], 'checkout_commit': manifest['checkout_commit']}


def read_pair(pair_id):
    root = Path('/tmp') / pair_id
    data = read_file(root, 'pair.json')
    return data, object_json(data)


def check_pair(root, pair):
    require(set(pair) == {'version', 'scope', 'status', 'pair_id', 'database_run_id', 'database_receipt',
                         'software_receipt', 'commits', 'hashes'})
    require(type(pair['version']) is int and pair['version'] == 1)
    require(pair['scope'] == 'SYNTHETIC_ONLY' and pair['status'] == 'SEALED' and pair['pair_id'] == root.name)
    require(pair['commits'] == validate_db(root, pair['database_run_id'], pair['database_receipt']))
    require(pair['hashes'] == snapshot(root, pair['database_run_id'], pair['software_receipt']))


def produce():
    deadline = time.monotonic() + 600
    root = new_root('joint-rehearsal-')
    stage = 'database-produce'
    try:
        run = secrets.token_hex(6)
        db = child(stage, ['-m', 'app.ops.postgresql_backup_restore', '--evidence-dir', root / 'database', '--run-id', run], deadline=deadline)
        commits = validate_db(root, run, db)
        stage = 'software-produce'
        sw = child(stage, [REPO / 'scripts/offline_software_restore_rehearsal.py'], deadline=deadline)
        hashes = snapshot(root, run, sw)
        pair = {'version': 1, 'scope': 'SYNTHETIC_ONLY', 'status': 'SEALED', 'pair_id': root.name,
                'database_run_id': run, 'database_receipt': db, 'software_receipt': sw,
                'commits': commits, 'hashes': hashes}
        check_pair(root, pair)
        require(time.monotonic() < deadline)
        data = encode(pair)
        write_file(root, 'pair.json', data)
        require(read_file(root, 'pair.json') == data)
        require(time.monotonic() < deadline)
        return {'scope': 'SYNTHETIC_ONLY', 'status': 'SEALED', 'pair_id': root.name, 'manifest_sha256': digest(data)}
    except BaseException:
        record_failure(root, {'status': 'FAILED', 'stage': stage, 'pair_id': root.name,
                              'cleanup': 'RETAINED_NO_RETRY'})
        raise


def recover(pair_id, expected_digest):
    deadline = time.monotonic() + 600
    require(matches(pair_id, r'joint-rehearsal-[0-9a-f]{32}') and matches(expected_digest, r'[0-9a-f]{64}'))
    original = Path('/tmp') / pair_id
    data, pair = read_pair(pair_id)
    require(digest(data) == expected_digest)
    check_pair(original, pair)
    root = new_root('joint-recovery-')
    stage, sw, db = 'software-recover', None, None
    try:
        source_sw = pair['software_receipt']
        sw = child(stage, [REPO / 'scripts/offline_retained_software_restore.py', source_sw['run_id'], source_sw['manifest_sha256']], deadline=deadline)
        software_receipt(sw, recovery=True)
        require(sw['source_run_id'] == source_sw['run_id'])
        require(all(sw[key] == source_sw[key] for key in ('file_count', 'total_bytes', 'manifest_sha256')))
        check_pair(original, pair)
        stage = 'database-recover'
        archive, manifest, baseline, _ = db_names(pair['database_run_id'])
        new_run = secrets.token_hex(6)
        require(new_run != pair['database_run_id'])
        db = child(stage, ['-m', 'app.ops.retained_synthetic_restore', '--archive', original / 'database' / archive,
                          '--manifest', original / 'database' / manifest, '--baseline', original / 'database' / baseline,
                          '--evidence-dir', root / 'database', '--run-id', new_run, '--trusted-own-synthetic'], deadline=deadline)
        require(db == {'status': 'passed', 'run_id': new_run, 'backup_run_id': pair['database_run_id'],
                       'cleanup': 'retained_for_explicit_cleanup'})
        restored = object_json(read_file(root / 'database', 'retained-synthetic-restore.json'))
        require(restored.get('status') == 'passed' and restored.get('run_id') == new_run)
        require(restored.get('backup_run_id') == pair['database_run_id'] and restored.get('source_accessed') is False)
        require(restored.get('originals_unchanged') is True)
        require(restored.get('backup_source_commit') == pair['commits']['source_commit'])
        require(restored.get('backup_checkout_commit') == pair['commits']['checkout_commit'])
        stage = 'final-verification'
        require(read_file(original, 'pair.json') == data)
        check_pair(original, pair)
        for name in SOFTWARE_FILES:
            require(digest(read_file(Path('/tmp') / sw['run_id'] / 'restored', name, 8192)) == pair['hashes']['software'][name])
        require(time.monotonic() < deadline)
        result = {'scope': 'SYNTHETIC_ONLY', 'status': 'VERIFIED', 'pair_id': pair_id, 'run_id': root.name,
                  'manifest_sha256': expected_digest, 'database_run_id': new_run, 'software_run_id': sw['run_id'],
                  'cleanup': 'RETAINED_FOR_EXPLICIT_INSPECTION'}
        # Disk receipt is deliberately not standalone proof of final completion.
        write_file(root, 'result.json', encode({**result, 'status': 'CANDIDATE', 'completion': 'STDOUT_AND_EXIT_ZERO_REQUIRED'}))
        require(time.monotonic() < deadline)
        return result
    except BaseException:
        # Child failure may have allocated resources without returning a receipt.
        # The database directory/proof and fixed software roots remain untouched.
        failure = {'status': 'FAILED', 'stage': stage, 'pair_id': pair_id, 'run_id': root.name,
                   'cleanup': 'RETAINED_NO_RETRY', 'partial_output_possible': True}
        if isinstance(sw, dict) and matches(sw.get('run_id'), r'software-recovery-[0-9a-f]{32}'):
            failure['software_run_id'] = sw['run_id']
        record_failure(root, failure)
        raise


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args in ([], ['--help']):
        print('SYNTHETIC_ONLY: produce --trusted-own-synthetic OR recover PAIR_ID EXPECTED_SHA256 --trusted-own-synthetic. Fixed /tmp only; TEST_POSTGRES_URL must refer to disposable loopback PostgreSQL. No default execution.')
        return 0
    try:
        if args == ['produce', '--trusted-own-synthetic']:
            result = produce()
        elif len(args) == 4 and args[0] == 'recover' and args[3] == '--trusted-own-synthetic':
            result = recover(args[1], args[2])
        else:
            raise Rejected('JOINT_REJECTED')
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({'scope': 'SYNTHETIC_ONLY', 'status': 'BLOCKED', 'reason': 'JOINT_OPERATION_FAILED'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
