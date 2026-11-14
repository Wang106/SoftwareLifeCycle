#!/usr/bin/env python3
"""Explicit local handoff-to-operator assembly, disabled without --run.

Trusted local Linux filesystem only, not a hostile-user security boundary.
Copies two strictly verified archives into a new private directory and writes
the exact preflight manifest and unapproved operator template. No extraction,
Docker, network, database, credentials, installation or deployment acceptance.
Failed or interrupted directories are retained, never overwritten or resumed.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
import stat
import sys

import offline_image_bundle as bundle

MAX_TOTAL_BYTES = 16 * 1024**3
RESERVE_BYTES = 1024**3
REVISION = '0030_private_upload_sessions'
FILES = frozenset({'api.tar', 'web.tar', 'manifest.json', 'operator.json'})
LIMITATIONS = ('Trusted local Linux filesystem only', 'Hashes are not signatures or provenance',
              'Database prerequisites and operator approval are not supplied',
              'No runtime, deployment or offline acceptance')


class AssemblyError(ValueError):
    """Only a fixed diagnostic code may leave the filesystem boundary."""
    def __init__(self):
        super().__init__('OPERATOR_ASSEMBLY_FAILED')


def _interruption(error, boundary):
    # An unchanged validator's stream context manager can replace its body
    # interrupt with a close error, then redact it to BundleError. Python still
    # retains that exception context; inspect types only, never exception text.
    # Prefer the original body control over later close controls, but never
    # revive a caller's already handled exception from before this operation.
    seen, original = set(), None
    while isinstance(error, BaseException) and error is not boundary and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            original = error
        error = error.__context__
    return original


class _ClosingStack(ExitStack):
    """Close every owned descriptor once, retaining interruptions over close errors.

The reused Descriptor marks an attempted close consumed before calling close:
an uncertain close must not be retried against a possibly recycled descriptor.
Ordinary ExitStack cleanup can otherwise replace an interrupt with an IO error.
"""
    def __init__(self):
        super().__init__()
        self.interruption = None
        self.boundary = sys.exc_info()[1]

    def callback(self, callback, *args, **kwargs):
        def checked_close():
            try:
                callback(*args, **kwargs)
            except (KeyboardInterrupt, SystemExit) as error:
                if self.interruption is None:
                    self.interruption = error
                raise
        return super().callback(checked_close)

    def __exit__(self, kind, value, traceback):
        self.interruption = _interruption(value, self.boundary)
        try:
            return super().__exit__(kind, value, traceback)
        finally:
            if self.interruption is not None:
                raise self.interruption


def operator_template():
    """Fresh fixed template, matching deploy/offline-readonly/operator.example.json."""
    return {'profile': 'linux-localhost-readonly', 'database_env_file': 'database.env',
            'database_preprovisioned': False, 'database_readonly_role': False,
            'data_classification': 'synthetic-only'}


def _inode(value):
    return value.st_dev, value.st_ino


def _assemble(source, destination, expected_commit, expected_manifest_sha256):
    bundle.require(bundle.hexadecimal(expected_commit, 40)
                   and bundle.hexadecimal(expected_manifest_sha256, 64))
    source_parts, destination_parts = bundle.path_parts(source), bundle.path_parts(destination)
    common = min(len(source_parts), len(destination_parts))
    bundle.require(len(destination_parts) > 1 and source_parts[:common] != destination_parts[:common])
    bundle.require(bundle.preflight.REVISION == REVISION)

    with _ClosingStack() as stack:
        source_dir = bundle.Directory.open(source, stack)
        source_dir.names(bundle.FILES | {'COMPLETE'})
        marker = bundle.File(source_dir, 'COMPLETE', stack)
        bundle.require(marker.initial.st_size == 0)
        sources = {name: bundle.File(source_dir, name, stack) for name in sorted(bundle.FILES)}
        bundle.require(sum(sources[role + '.tar'].initial.st_size for role in ('api', 'web')) <= MAX_TOTAL_BYTES)
        # This strict source gate completes before any destination creation.
        handoff = bundle.verify_files(source_dir, sources, expected_commit,
                                      expected_manifest_sha256, completed=True)
        marker.check()
        manifest = {'format': 'slc-offline-readonly-v1', 'source_commit': handoff['source_commit'],
                    'required_db_revision': REVISION,
                    'images': {role: dict(handoff['images'][role]) for role in ('api', 'web')}}
        metadata = {'manifest.json': bundle.canonical(manifest),
                    'operator.json': bundle.canonical(operator_template())}
        archive_bytes = sum(item['size'] for item in manifest['images'].values())
        copy_bytes = archive_bytes + sum(len(raw) for raw in metadata.values())
        bundle.require(archive_bytes <= MAX_TOTAL_BYTES)

        parent = bundle.Directory.open('/' + '/'.join(destination_parts[:-1]), stack)
        source_inode = _inode(os.fstat(source_dir.fd))
        # Also reject directory aliases (for example trusted bind mounts) that
        # evade lexical nesting detection. No bind mounts are created here.
        bundle.require(all(_inode(os.fstat(fd.fd)) != source_inode for fd in parent.descriptors))
        try:
            os.stat(destination_parts[-1], dir_fd=parent.fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise AssemblyError()
        capacity = os.fstatvfs(parent.fd)
        bundle.require(capacity.f_bavail * capacity.f_frsize >= copy_bytes + RESERVE_BYTES)
        parent.check()
        source_dir.names(bundle.FILES | {'COMPLETE'})
        marker.check()
        for file in sources.values():
            file.check()

        # Exclusive reservation; any later failure leaves this directory intact.
        os.mkdir(destination_parts[-1], mode=0o700, dir_fd=parent.fd)
        directory = parent.child(destination_parts[-1], stack)
        directory.names(set())
        bundle.require(not stat.S_IMODE(os.fstat(directory.fd).st_mode) & ~0o700)
        files = {}
        source_inodes = {_inode(file.initial) for file in sources.values()} | {_inode(marker.initial)}
        for role in ('api', 'web'):
            name = role + '.tar'
            files[name] = bundle.File(directory, name, stack, create=True)
            bundle.require(_inode(files[name].initial) not in source_inodes)
            bundle.copy_archive(sources[name], files[name], manifest['images'][role])
        for name, raw in metadata.items():
            files[name] = bundle.File(directory, name, stack, create=True)
            bundle.write_bytes(files[name], raw)
            files[name].written()

        directory.names(FILES)
        for name, raw in metadata.items():
            bundle.require(bundle.read_bytes(files[name], bundle.MAX_JSON_BYTES) == raw)
        # Reparse and hash the actual independent output inodes, not a receipt
        # or the copy loop's digest. Existing strict archive gates stay unchanged.
        for role in ('api', 'web'):
            bundle.archive_gate(files[role + '.tar'], manifest['images'][role], expected_commit)
        os.fsync(directory.fd)
        os.fsync(parent.fd)

        # Source handles never close/reopen between the two full verifications.
        bundle.verify_files(source_dir, sources, expected_commit, expected_manifest_sha256, completed=True)
        marker.check()
        source_dir.names(bundle.FILES | {'COMPLETE'})
        directory.names(FILES)
        bundle.require(not stat.S_IMODE(os.fstat(directory.fd).st_mode) & ~0o700)
        for file in files.values():
            file.check()
            bundle.require(file.initial.st_nlink == 1 and not stat.S_IMODE(file.initial.st_mode) & ~0o600)
        # No marker: all four files can exist after a failed close. Success is
        # returned only after the context has closed every retained descriptor.

    return {'status': 'OPERATOR_DIRECTORY_ASSEMBLED_NOT_READY', 'source_commit': expected_commit,
            'handoff_manifest_sha256': expected_manifest_sha256,
            'manifest_sha256': hashlib.sha256(metadata['manifest.json']).hexdigest(),
            'operator_sha256': hashlib.sha256(metadata['operator.json']).hexdigest(),
            'archive_count': 2, 'file_count': 4, 'archive_bytes': archive_bytes,
            'operator_ready': False, 'application_started': False, 'database_started': False,
            'provenance_verified': False, 'offline_accepted': False, 'deployment_approved': False,
            'limitations': list(LIMITATIONS)}


def assemble(source, destination, *, expected_commit, expected_manifest_sha256):
    """Create once from independent trusted expectations; never clean up or retry.

All ordinary failures are redacted. Control exceptions retain their type for
callers, even if cleanup fails too, without retaining private exception text.
"""
    try:
        return _assemble(source, destination, expected_commit, expected_manifest_sha256)
    except KeyboardInterrupt:
        raise KeyboardInterrupt('OPERATOR_ASSEMBLY_INTERRUPTED') from None
    except SystemExit:
        raise SystemExit(2) from None
    except Exception:
        raise AssemblyError() from None


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, 'offline operator assembly: invalid arguments\n')


def _emit(stream, message):
    line = message + '\n'
    count = stream.write(line)
    bundle.require(type(count) is int and count == len(line))
    stream.flush()


def _blocked(code):
    # Reporting failure must not expose another raw stream exception. A failed
    # receipt is uncertain delivery, not permission to repeat the assembly.
    try:
        _emit(sys.stderr, 'BLOCKED: assembly unconfirmed; any created directory must not be resumed.')
    except KeyboardInterrupt:
        return 130
    except (Exception, SystemExit):
        pass
    return code


def main(argv=None):
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('mode', nargs='?', choices=['assemble'])
    parser.add_argument('source', nargs='?')
    parser.add_argument('destination', nargs='?')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--expected-commit')
    parser.add_argument('--expected-manifest-sha256')
    args = parser.parse_args(argv)
    if args.run and not all((args.mode, args.source, args.destination, args.expected_commit,
                             args.expected_manifest_sha256)):
        parser.error('missing inputs')
    try:
        if not args.run:
            _emit(sys.stdout, 'DISABLED: operator assembly requires explicit --run; no inputs inspected or files created.')
            return 0
        result = assemble(args.source, args.destination, expected_commit=args.expected_commit,
                          expected_manifest_sha256=args.expected_manifest_sha256)
        _emit(sys.stdout, json.dumps(result, sort_keys=True))
    except KeyboardInterrupt:
        return _blocked(130)
    except (Exception, SystemExit):
        return _blocked(2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
