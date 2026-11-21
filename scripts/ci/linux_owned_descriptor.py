"""Owned descriptor adapter over injected operations; no OS implementation."""
from typing import Protocol


class DescriptorOps(Protocol):
    def identity(self, directory: object) -> tuple[int, int]: ...
    def open_relative(self, directory: object, name: str) -> object: ...
    def read_chunk(self, record: object, size: int) -> bytes: ...
    def readlink_relative(self, directory: object, name: str, capacity: int) -> bytes: ...
    def close(self, handle: object) -> None: ...


class DescriptorRejected(ValueError):
    pass


class OwnedDirectory:
    """Own the supplied opaque object() handle after successful construction.

    Raw numeric FDs/value handles are rejected. Ops maps unique object() tokens
    to resources and must preserve handle identity and implement genuinely relative, read-only
    access; no such kernel implementation is provided or verified here. Identity
    is supplied device/inode metadata, not process-generation or pidfd proof.
    This object is single-owner, synchronous, and not thread-safe.
    """
    _LIMITS = {'stat':4096, 'status':16384, 'ns/pid':128, 'ns/net':128, 'ns/user':128}

    def __init__(self, ops: DescriptorOps, directory: object,
                 directory_identity: tuple[int, int], binding: object):
        if (type(directory) is not object or binding is None or type(directory_identity) is not tuple or
                len(directory_identity) != 2 or
                any(type(n) is not int or not 0 <= n < 2**64 for n in directory_identity)):
            raise DescriptorRejected('Descriptor input rejected')
        self._ops, self._directory = ops, directory
        self._identity, self._binding = directory_identity, binding
        self._closed = False
        self.failure_reason = None

    @property
    def binding(self):
        return self._binding

    def _reject(self, reason):
        self.failure_reason = reason
        raise DescriptorRejected('Descriptor observation rejected') from None

    def _check(self):
        if self._closed or self.failure_reason is not None:
            raise DescriptorRejected('Descriptor unavailable')
        observed = self._ops.identity(self._directory)
        if (type(observed) is not tuple or len(observed) != 2 or
                any(type(n) is not int for n in observed) or observed != self._identity):
            self._reject('identity_changed')

    def _close_record(self, handle):
        try:
            self._ops.close(handle)
        except Exception:
            self._reject('cleanup_failed')

    def _record(self, name, limit):
        handle = self._ops.open_relative(self._directory, name)
        if type(handle) is not object or handle is self._directory:
            self._reject('invalid_handle')
        try:
            data = bytearray()
            # Positive short reads are progress, not EOF. At the exact limit,
            # request one positive byte to distinguish EOF from truncation.
            for _ in range(limit + 1):
                self._check()
                size = min(4096, limit + 1 - len(data))
                chunk = self._ops.read_chunk(handle, size)
                self._check()
                if type(chunk) is not bytes or len(chunk) > size:
                    self._reject('invalid_record')
                if not chunk:
                    if not data:
                        self._reject('invalid_record')
                    return bytes(data)
                data.extend(chunk)
                if len(data) > limit:
                    self._reject('invalid_record')
            self._reject('invalid_record')
        finally:
            # One close attempt only: an error may already have released an FD.
            self._close_record(handle)

    def read(self, relative_name: str, limit: int) -> bytes:
        try:
            self._check()
            if (type(relative_name) is not str or type(limit) is not int or
                    self._LIMITS.get(relative_name) != limit):
                self._reject('invalid_request')
            if relative_name.startswith('ns/'):
                # readlink has no stream EOF: an extra byte detects an overlong
                # or capacity-truncated link instead of accepting its prefix.
                value = self._ops.readlink_relative(self._directory, relative_name, limit + 1)
                self._check()
                if type(value) is not bytes or not 0 < len(value) <= limit:
                    self._reject('invalid_link')
                return value
            return self._record(relative_name, limit)
        except DescriptorRejected:
            raise
        except PermissionError:
            self._reject('permission_denied')
        except Exception:
            self._reject('io_error')

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._ops.close(self._directory)
        except Exception:
            self._reject('cleanup_failed')

    def __enter__(self):
        if self._closed or self.failure_reason is not None:
            raise DescriptorRejected('Descriptor unavailable')
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False
