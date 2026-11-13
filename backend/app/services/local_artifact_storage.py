"""Default-off, import-inert local byte storage primitive. No application wiring.

Only trusted Linux local filesystems with atomic hard links and directory fsync
are supported. The operator supplies an existing, service-owned 0700 absolute
root, with trusted ancestor directories. No chmod, mkdir, client filenames,
network access, database state, deletion, garbage collection or automatic retry.
The same UID/root administrator is trusted: this is not a sandbox against them.
The trusted caller serializes non-reentrant calls (including reader callbacks),
keeps instance configuration fixed and prevents concurrent object-path mutation.
No thread-safe lifecycle or cross-process reservation is provided.

reserve() does no filesystem I/O. Its immutable receipt must be durably retained
by the caller BEFORE stage(); a process crash cannot deliver an error receipt.
UUIDs are service-generated identifiers, not authentication or authorization.
stage() creates a fresh 0600 .part with O_EXCL and verifies bounded bytes. commit()
revalidates it, hard-links to a fresh .blob, then fsyncs the directory. It retains
the stage alias deliberately. All failures retain any created bytes. Repeating
stage/commit is rejected, never an idempotent retry. After any ambiguous outcome,
inspect() is read-only (apart from filesystem access-time behavior); it reports
current bytes, NOT proven durability, prior operation success or DB/business
READY. A matching partial stage after a failed fsync is not proof of success.
Only the same storage instance can commit a receipt after stage() returned
successfully, and it consumes this one-shot capability before attempting commit.
Failed/ambiguous calls and process restarts permit inspection only. An async
interrupt between internal success and delivery of the Python return cannot
prove acknowledgement: callers must inspect only after any such uncertainty.
A future durable adapter must handle acknowledgement and persistence explicitly.

No quotas across objects, malware checks, download API, HTTP authorization,
retention policy, Windows/network filesystem support or company acceptance is
provided. Expected digest/size are trusted caller inputs, not origin evidence.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
import re
import stat
import sys
import uuid


@dataclass(frozen=True)
class Receipt:
    object_id: str
    expected_bytes: int
    sha256: str


class StorageError(Exception):
    """Operation failed or is uncertain; receipt permits read-only inspection."""

    def __init__(self, message, receipt=None):
        super().__init__(message)
        self.receipt = receipt


def _close_once(fd, *, suppress_error=False):
    """Never retry Linux close, even if acknowledgement is uncertain."""
    try:
        os.close(fd)
    except OSError:
        if not suppress_error:
            raise


@contextmanager
def _owned_fd(fd):
    """Preserve only this scope's primary failure, not a caller's exception."""
    try:
        yield fd
    except BaseException:
        _close_once(fd, suppress_error=True)
        raise
    else:
        _close_once(fd)


def _stable_info(info):
    # Reading either hard-link alias can update atime on their shared inode.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class LocalArtifactStorage:
    def __init__(self, root, *, enabled=False, max_bytes=64 * 1024 * 1024,
                 chunk_bytes=64 * 1024):
        # Configuration is inert, including when disabled or invalid.
        self.root = root
        self.enabled = enabled
        self.max_bytes = max_bytes
        self.chunk_bytes = chunk_bytes
        self._staged = set()

    def _gate(self):
        if self.enabled is not True:
            raise StorageError('local artifact storage is disabled')
        if sys.platform != 'linux':
            raise StorageError('only trusted Linux local filesystems are supported')
        if (type(self.max_bytes) is not int or self.max_bytes < 0
                or type(self.chunk_bytes) is not int
                or not 1 <= self.chunk_bytes <= 1024 * 1024):
            raise StorageError('invalid storage bounds')

    def _metadata(self, size, digest):
        if (type(size) is not int or not 0 <= size <= self.max_bytes
                or type(digest) is not str
                or re.fullmatch('[0-9a-f]{64}', digest) is None):
            raise StorageError('invalid expected size or SHA-256')

    def _receipt(self, receipt):
        self._gate()
        if type(receipt) is not Receipt:
            raise StorageError('invalid receipt')
        self._metadata(receipt.expected_bytes, receipt.sha256)
        try:
            identifier = uuid.UUID(receipt.object_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise StorageError('invalid object identifier') from exc
        if str(identifier) != receipt.object_id or identifier.version != 4:
            raise StorageError('invalid object identifier')

    def reserve(self, *, expected_bytes, sha256):
        """Return a new service ID; caller persists receipt before any write."""
        self._gate()
        self._metadata(expected_bytes, sha256)
        return Receipt(str(uuid.uuid4()), expected_bytes, sha256)

    @contextmanager
    def _root(self):
        root = self.root
        if (type(root) is not str or not root.startswith('/') or root == '/'
                or any(part in ('', '.', '..') for part in root.split('/')[1:])):
            raise StorageError('root must be a canonical absolute directory path')
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            for part in root.split('/')[1:]:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY
                                  | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                previous_fd, fd = fd, next_fd
                _close_once(previous_fd)
                info = os.fstat(fd)
                # Shared sticky ancestors such as /tmp cannot replace our
                # owned child; arbitrary non-sticky writable ancestors can.
                if (info.st_uid not in (0, os.geteuid())
                        or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX)):
                    raise StorageError('untrusted root ancestor')
            info = os.fstat(fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise StorageError('root must already be service-owned mode 0700')
            yield fd
        except BaseException:
            _close_once(fd, suppress_error=True)
            raise
        else:
            _close_once(fd)

    def _file_info(self, root_fd, name):
        try:
            info = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink not in (1, 2)):
            raise StorageError('unsafe object file')
        return info

    def _pair(self, root_fd, receipt):
        names = [receipt.object_id + suffix for suffix in ('.part', '.blob')]
        infos = [self._file_info(root_fd, name) for name in names]
        for info in infos:
            if info is not None and info.st_nlink == 2:
                if any(other is None or (other.st_dev, other.st_ino) !=
                       (info.st_dev, info.st_ino) for other in infos):
                    raise StorageError('unexpected hard link')
        return names, infos

    def _verify(self, root_fd, name, expected_info, receipt):
        if expected_info is None:
            return 'missing'
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                     | os.O_CLOEXEC, dir_fd=root_fd)
        with _owned_fd(fd):
            before = os.fstat(fd)
            if _stable_info(before) != _stable_info(expected_info):
                raise StorageError('object changed during inspection')
            if before.st_size != receipt.expected_bytes:
                return 'mismatch'
            digest = hashlib.sha256()
            size = 0
            while True:
                block = os.read(fd, min(self.chunk_bytes, receipt.expected_bytes - size + 1))
                if not block:
                    break
                size += len(block)
                if size > receipt.expected_bytes:
                    return 'mismatch'
                digest.update(block)
            after = os.fstat(fd)
            if _stable_info(before) != _stable_info(after):
                raise StorageError('object changed during inspection')
            return ('verified' if size == receipt.expected_bytes
                    and digest.hexdigest() == receipt.sha256 else 'mismatch')

    def stage(self, receipt, source):
        """Consume bounded binary read(n); source is borrowed and never closed."""
        self._receipt(receipt)
        self._staged.discard(receipt)
        try:
            with self._root() as root_fd:
                name = receipt.object_id + '.part'
                if self._file_info(root_fd, receipt.object_id + '.blob') is not None:
                    raise StorageError('object identifier already used', receipt)
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=root_fd)
                with _owned_fd(fd):
                    info = os.fstat(fd)
                    if stat.S_IMODE(info.st_mode) != 0o600:
                        raise StorageError('umask prevented required file mode', receipt)
                    size = 0
                    digest = hashlib.sha256()
                    while True:
                        count = min(self.chunk_bytes, receipt.expected_bytes - size + 1)
                        block = source.read(count)
                        if type(block) is not bytes or len(block) > count:
                            raise StorageError('reader violated bounded bytes contract', receipt)
                        if not block:
                            break
                        if size + len(block) > receipt.expected_bytes:
                            raise StorageError('stream exceeds expected size', receipt)
                        view = memoryview(block)
                        while view:
                            written = os.write(fd, view)
                            if written <= 0 or written > len(view):
                                raise StorageError('invalid write progress', receipt)
                            view = view[written:]
                        size += len(block)
                        digest.update(block)
                    if size != receipt.expected_bytes or digest.hexdigest() != receipt.sha256:
                        raise StorageError('stream size or SHA-256 mismatch', receipt)
                    os.fsync(fd)
                os.fsync(root_fd)
            self._staged.add(receipt)
            return receipt
        except Exception as exc:
            raise StorageError('stage failed; inspect retained state without retry', receipt) from exc

    def commit(self, receipt):
        """Publish once without overwriting. Only after a successful stage call."""
        self._receipt(receipt)
        if receipt not in self._staged:
            raise StorageError('no successful unconsumed stage in this instance', receipt)
        self._staged.remove(receipt)
        try:
            with self._root() as root_fd:
                names, infos = self._pair(root_fd, receipt)
                if infos[1] is not None:
                    raise StorageError('publication already exists', receipt)
                if self._verify(root_fd, names[0], infos[0], receipt) != 'verified':
                    raise StorageError('stage is absent or invalid', receipt)
                os.link(names[0], names[1], src_dir_fd=root_fd, dst_dir_fd=root_fd,
                        follow_symlinks=False)
                os.fsync(root_fd)
        except Exception as exc:
            raise StorageError('commit failed or uncertain; inspect without retry', receipt) from exc

    def inspect(self, receipt):
        """Observe bounded current bytes; never repair, sync, publish or delete."""
        self._receipt(receipt)
        try:
            with self._root() as root_fd:
                names, infos = self._pair(root_fd, receipt)
                return dict(zip(('stage', 'object'),
                                (self._verify(root_fd, name, info, receipt)
                                 for name, info in zip(names, infos))))
        except Exception as exc:
            raise StorageError('inspection failed; no recovery mutation performed', receipt) from exc
