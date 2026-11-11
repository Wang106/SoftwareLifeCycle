#!/usr/bin/env python3
"""Bounded, synthetic-only software file backup/restore; Linux directory-fd I/O."""
import hashlib
import json
import os
import secrets
import stat
import sys

FIXTURES = {
    'firmware.bin': b'SYNTHETIC_ONLY\x00' + bytes(range(256)) * 4,
    'settings.json': b'{"mode":"sample-only","real_writes":false}\n',
    'README.txt': b'Synthetic software restore rehearsal. No company data.\n',
}
MAX_BYTES = 8192
MAX_ENTRIES = 4


class Rejected(Exception):
    """Intentionally contains only a fixed, non-sensitive code."""


def identity(st):
    return st.st_dev, st.st_ino


def signature(st):
    return identity(st), st.st_mode, st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def supported():
    return (sys.platform == 'linux' and hasattr(os, 'O_NOFOLLOW')
            and hasattr(os, 'O_DIRECTORY') and os.open in os.supports_dir_fd
            and os.stat in os.supports_dir_fd and os.mkdir in os.supports_dir_fd
            and os.scandir in os.supports_fd)


def expected_manifest(run_id):
    return json.dumps({'scope': 'SYNTHETIC_ONLY', 'version': 1, 'run_id': run_id,
                       'files': [{'path': name, 'size': len(data),
                                  'sha256': hashlib.sha256(data).hexdigest()}
                                 for name, data in sorted(FIXTURES.items())]},
                      sort_keys=True, separators=(',', ':')).encode('ascii')


class Rehearsal:
    """One fresh run, with no caller-selected source, bundle, or target path.

    Private helpers and fds are not an import API for untrusted callers. The CLI
    is the supported boundary. Retained evidence cannot be resumed/imported.
    """
    def __init__(self):
        self.fds = []
        self.links = []
        self.run_id = None
        self.prepared = False
        self.finished = False
        try:
            if not supported():
                raise Rejected('UNSUPPORTED_PLATFORM')
            self.parent = self._open_dir('/tmp')
            parent_stat = os.fstat(self.parent)
            if (parent_stat.st_uid not in (0, os.geteuid())
                    or (parent_stat.st_mode & 0o022 and not parent_stat.st_mode & stat.S_ISVTX)):
                raise Rejected('UNSAFE_TEMP_ROOT')
            self.run_id = 'software-rehearsal-' + secrets.token_hex(16)
            self.root = self._new_dir(self.parent, self.run_id)
            # This immutable in-process reference, not disk JSON, anchors trust.
            self.manifest = expected_manifest(self.run_id)
        except BaseException:
            self.close()
            raise

    def _open_dir(self, name, parent=None):
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                     dir_fd=parent)
        self.fds.append(fd)
        return fd

    def _new_dir(self, parent, name):
        self._guard()
        os.mkdir(name, 0o700, dir_fd=parent)  # Existing, even empty, is forbidden.
        fd = self._open_dir(name, parent)
        st = os.fstat(fd)
        if st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != 0o700:
            raise Rejected('UNSAFE_DIRECTORY')
        self.links.append((parent, name, fd, identity(st)))
        self._guard()
        return fd

    def _guard(self):
        for parent, name, fd, saved in self.links:
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            opened = os.fstat(fd)
            if (identity(current) != saved or identity(opened) != saved
                    or not stat.S_ISDIR(current.st_mode)
                    or stat.S_IMODE(current.st_mode) != 0o700
                    or current.st_uid != os.geteuid()):
                raise Rejected('DIRECTORY_CHANGED')

    def _names(self, directory):
        self._guard()
        names = set()
        with os.scandir(directory) as entries:
            for entry in entries:
                if len(names) >= MAX_ENTRIES:
                    raise Rejected('UNEXPECTED_FILES')
                names.add(entry.name)
        self._guard()
        return names

    def _write(self, directory, name, data):
        self._guard()
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                     | os.O_CLOEXEC | os.O_NONBLOCK, 0o600, dir_fd=directory)
        try:
            initial = os.fstat(fd)
            if not stat.S_ISREG(initial.st_mode) or initial.st_nlink != 1:
                raise Rejected('UNSAFE_FILE')
            offset = 0
            while offset < len(data):
                self._guard()
                count = os.write(fd, data[offset:])
                if count <= 0:
                    raise Rejected('WRITE_FAILED')
                offset += count
            os.fsync(fd)
            final = os.fstat(fd)
            linked = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (signature(final) != signature(linked) or final.st_nlink != 1
                    or final.st_size != len(data)):
                raise Rejected('FILE_CHANGED')
            self._guard()
        finally:
            os.close(fd)

    def _read(self, directory, name, expected):
        self._guard()
        before = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size != len(expected) or before.st_size > MAX_BYTES):
            raise Rejected('UNSAFE_FILE')
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     dir_fd=directory)
        try:
            initial = os.fstat(fd)
            if signature(initial) != signature(before):
                raise Rejected('FILE_CHANGED')
            chunks = bytearray()
            while len(chunks) <= len(expected):
                block = os.read(fd, len(expected) + 1 - len(chunks))
                if not block:
                    break
                chunks.extend(block)
            final = os.fstat(fd)
            linked = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if signature(initial) != signature(final) or signature(final) != signature(linked):
                raise Rejected('FILE_CHANGED')
            self._guard()
            data = bytes(chunks)
            if data != expected or hashlib.sha256(data).digest() != hashlib.sha256(expected).digest():
                raise Rejected('CONTENT_MISMATCH')
            return data
        finally:
            os.close(fd)

    def _verify(self, directory, with_manifest=False):
        wanted = set(FIXTURES) | ({'manifest.json'} if with_manifest else set())
        if self._names(directory) != wanted:
            raise Rejected('UNEXPECTED_FILES')
        if with_manifest:
            # Exact bounded bytes, never parse or follow a path from disk JSON.
            self._read(directory, 'manifest.json', self.manifest)
        contents = {name: self._read(directory, name, data) for name, data in FIXTURES.items()}
        if self._names(directory) != wanted:
            raise Rejected('UNEXPECTED_FILES')
        return contents

    def prepare(self):
        if self.prepared or self.finished:
            raise Rejected('INVALID_STATE')
        self.source = self._new_dir(self.root, 'source')
        self.bundle = self._new_dir(self.root, 'bundle')
        for name, data in FIXTURES.items():
            self._write(self.source, name, data)
        for name, data in self._verify(self.source).items():
            self._write(self.bundle, name, data)
        self._write(self.bundle, 'manifest.json', self.manifest)
        self._verify(self.bundle, with_manifest=True)
        self.prepared = True

    def restore(self):
        if not self.prepared or self.finished:
            raise Rejected('INVALID_STATE')
        self.finished = True  # A failed attempt cannot be resumed into partial output.
        contents = self._verify(self.bundle, with_manifest=True)
        target = self._new_dir(self.root, 'restored')
        for name, data in contents.items():
            self._write(target, name, data)
        self._verify(target)
        self._verify(self.source)
        self._verify(self.bundle, with_manifest=True)
        self._guard()
        report = {'scope': 'SYNTHETIC_ONLY', 'status': 'VERIFIED', 'run_id': self.run_id,
                  'file_count': len(contents), 'total_bytes': sum(map(len, contents.values())),
                  'manifest_sha256': hashlib.sha256(self.manifest).hexdigest()}
        self._write(self.root, 'result.json', json.dumps(report, sort_keys=True).encode('ascii'))
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

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()  # Never delete retained evidence, known or unknown.


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args == ['--help']:
        print('Synthetic-only software backup/restore. No arguments accepted. Evidence retained in /tmp.')
        return 0
    if args:
        print(json.dumps({'scope': 'SYNTHETIC_ONLY', 'status': 'BLOCKED', 'reason': 'ARGUMENTS_REJECTED'}))
        return 2
    run = None
    try:
        with Rehearsal() as run:
            run.prepare()
            report = run.restore()
        print(json.dumps(report, sort_keys=True))
        return 0
    except (OSError, Rejected):
        # No raw exception, caller argument, path, configuration, or file data.
        report = {'scope': 'SYNTHETIC_ONLY', 'status': 'BLOCKED', 'reason': 'REHEARSAL_FAILED'}
        if run is not None:
            report['run_id'] = run.run_id
        print(json.dumps(report, sort_keys=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
