#!/usr/bin/env python3
"""Restore only a retained, fixed synthetic bundle. No arbitrary path interface."""
import hashlib
import json
import os
import re
import secrets
import stat
import sys

from offline_software_restore_rehearsal import (
    FIXTURES, Rehearsal, Rejected, expected_manifest, identity, signature, supported,
)


def valid_arguments(args):
    return (len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], str)
            and len(args[0]) == 51 and len(args[1]) == 64
            and re.fullmatch(r'software-rehearsal-[0-9a-f]{32}', args[0]) is not None
            and re.fullmatch(r'[0-9a-f]{64}', args[1]) is not None)


class RetainedRestore(Rehearsal):
    """CLI-only boundary; inherited helpers never receive disk-supplied paths.

    No directory is created in __init__. Validation precedes target allocation.
    A digest binds the operator's record; it is not a signature or proof of origin.
    """
    def __init__(self, source_run_id, manifest_sha256):
        self.fds = []
        self.links = []
        self.snapshots = {}
        self.run_id = None
        self.finished = False
        self.parent_state = None
        try:
            if not valid_arguments([source_run_id, manifest_sha256]):
                raise Rejected('ARGUMENTS_REJECTED')
            if not supported():
                raise Rejected('UNSUPPORTED_PLATFORM')
            self.source_run_id = source_run_id
            self.manifest = expected_manifest(source_run_id)
            if hashlib.sha256(self.manifest).hexdigest() != manifest_sha256:
                raise Rejected('DIGEST_MISMATCH')
            self.parent = self._open_dir('/tmp')
            st = os.fstat(self.parent)
            if (st.st_uid not in (0, os.geteuid())
                    or (st.st_mode & 0o022 and not st.st_mode & stat.S_ISVTX)):
                raise Rejected('UNSAFE_TEMP_ROOT')
            self.parent_state = (identity(st), st.st_mode, st.st_uid)
            self.original = self._existing_dir(self.parent, source_run_id)
            self.bundle = self._existing_dir(self.original, 'bundle')
            baseline = {'scope': 'SYNTHETIC_ONLY', 'status': 'VERIFIED', 'run_id': source_run_id,
                        'file_count': len(FIXTURES), 'total_bytes': sum(map(len, FIXTURES.values())),
                        'manifest_sha256': manifest_sha256}
            self.baseline = json.dumps(baseline, sort_keys=True).encode('ascii')
        except BaseException:
            self.close()
            raise

    def _existing_dir(self, parent, name):
        self._guard()
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        fd = self._open_dir(name, parent)
        opened = os.fstat(fd)
        if (identity(before) != identity(opened) or not stat.S_ISDIR(opened.st_mode)
                or stat.S_IMODE(opened.st_mode) != 0o700 or opened.st_uid != os.geteuid()):
            raise Rejected('UNSAFE_DIRECTORY')
        self.links.append((parent, name, fd, identity(opened)))
        self._guard()
        return fd

    def _guard(self):
        if self.parent_state is not None:
            for st in (os.fstat(self.parent), os.stat('/tmp', follow_symlinks=False)):
                if (identity(st), st.st_mode, st.st_uid) != self.parent_state:
                    raise Rejected('TEMP_ROOT_CHANGED')
        super()._guard()
        for (directory, name), saved in self.snapshots.items():
            st = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (signature(st), st.st_uid) != saved:
                raise Rejected('FILE_CHANGED')

    def _read(self, directory, name, expected):
        st = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != 0o600:
            raise Rejected('UNSAFE_FILE')
        key = (directory, name)
        saved = (signature(st), st.st_uid)
        if key in self.snapshots and self.snapshots[key] != saved:
            raise Rejected('FILE_CHANGED')
        self.snapshots[key] = saved
        data = super()._read(directory, name, expected)
        self._guard()
        return data

    def _write(self, directory, name, data):
        super()._write(directory, name, data)
        # Include new files (including the report) in mode/owner/identity guards.
        self._read(directory, name, data)

    def restore(self):
        if self.finished:
            raise Rejected('INVALID_STATE')
        self.finished = True
        self._read(self.original, 'result.json', self.baseline)
        contents = self._verify(self.bundle, with_manifest=True)
        self._guard()
        self.run_id = 'software-recovery-' + secrets.token_hex(16)
        self.root = self._new_dir(self.parent, self.run_id)
        target = self._new_dir(self.root, 'restored')
        for name, data in contents.items():
            self._write(target, name, data)
        self._verify(target)
        self._verify(self.bundle, with_manifest=True)
        self._read(self.original, 'result.json', self.baseline)
        report = {'scope': 'SYNTHETIC_ONLY', 'status': 'VERIFIED', 'run_id': self.run_id,
                  'source_run_id': self.source_run_id, 'file_count': len(contents),
                  'total_bytes': sum(map(len, contents.values())),
                  'manifest_sha256': hashlib.sha256(self.manifest).hexdigest()}
        # Persisted bytes can survive a later fsync, close, or guard failure.
        # They must never assert success: only stdout plus exit 0 is final.
        candidate = {**report, 'status': 'CANDIDATE',
                     'completion_evidence': 'STDOUT_AND_EXIT_ZERO_REQUIRED'}
        self._write(self.root, 'recovery-result.json', json.dumps(candidate, sort_keys=True).encode('ascii'))
        self._guard()
        return report


    def close(self):
        error = None
        while self.fds:
            fd = self.fds.pop()
            try:
                os.close(fd)
            except OSError as exc:
                # A failed close has an uncertain outcome. Never retry that
                # descriptor number, but still attempt every other owned fd.
                if error is None:
                    error = exc
        if error is not None:
            raise error


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args == ['--help']:
        print('SYNTHETIC_ONLY: RUN_ID EXPECTED_MANIFEST_SHA256; retained bundle in fixed /tmp only.')
        return 0
    if not valid_arguments(args):
        print(json.dumps({'scope': 'SYNTHETIC_ONLY', 'status': 'BLOCKED', 'reason': 'ARGUMENTS_REJECTED'}))
        return 2
    try:
        with RetainedRestore(*args) as run:
            report = run.restore()
        print(json.dumps(report, sort_keys=True))
        return 0
    except (OSError, Rejected):
        print(json.dumps({'scope': 'SYNTHETIC_ONLY', 'status': 'BLOCKED', 'reason': 'RECOVERY_FAILED'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
