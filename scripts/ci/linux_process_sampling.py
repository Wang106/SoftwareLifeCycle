"""Injected one-shot sampling protocol. No live adapters or process operations."""
from typing import Protocol
from scripts.ci.linux_proc_observations import adapt, parse_stat


class BoundDirectory(Protocol):
    # Shared opaque association token, NOT a kernel identity proof.
    binding: object

    def read(self, relative_name: str, limit: int) -> bytes:
        """Supply a complete bounded record from the already-bound directory.

        Future live implementations must reject truncation and keep the original
        directory descriptor; this interface provides no open-by-PID fallback.
        """
        ...


class BoundExitProbe(Protocol):
    binding: object

    def exited(self) -> bool:
        """Report exit for the same bound identity; unknown/error must reject."""
        ...


class SamplingRejected(ValueError):
    pass


class SampleOnce:
    """Caller owns adapters and their cleanup. This instance consumes one attempt.

    Neither tokens nor supplied bytes attest actual kernel binding. Calls are
    sequential, not atomic; a future live adapter needs its own bounded I/O and
    identity/exit mechanism. No wall-clock deadline is enforced here.
    """
    def __init__(self, directory: BoundDirectory, probe: BoundExitProbe,
                 expected_pid: int, expected_start_ticks: int):
        if (type(expected_pid) is not int or not 0 < expected_pid < 2**31 or
                type(expected_start_ticks) is not int or not 0 < expected_start_ticks < 2**63):
            raise SamplingRejected('Process sampling rejected')
        self._directory = directory
        self._probe = probe
        self._expected = (expected_pid, expected_start_ticks)
        self._used = False
        try:
            self._binding = directory.binding
            if self._binding is None or probe.binding is not self._binding:
                raise ValueError()
        except Exception:
            raise SamplingRejected('Process sampling rejected') from None

    def _check(self):
        if (self._directory.binding is not self._binding or
                self._probe.binding is not self._binding or
                self._probe.exited() is not False or
                self._directory.binding is not self._binding or
                self._probe.binding is not self._binding):
            raise ValueError()

    def _read(self, name, limit):
        self._check()
        raw = self._directory.read(name, limit)
        self._check()
        if type(raw) is not bytes or not 0 < len(raw) <= limit:
            raise ValueError()
        return raw

    def sample(self):
        if self._used:
            raise SamplingRejected('Process sampling rejected')
        self._used = True
        try:
            before = self._read('stat', 4096)
            identity = parse_stat(before)
            if (identity['pid'], identity['start_ticks']) != self._expected:
                raise ValueError()
            status = self._read('status', 16384)
            namespaces = {kind: self._read('ns/' + kind, 128)
                          for kind in ('pid', 'net', 'user')}
            after = self._read('stat', 4096)
            result = adapt(before, status, namespaces, after)
            result.update(atomic_snapshot=False, live_binding_verified=False)
            return result
        except Exception:
            # Suppress adapter diagnostics which may contain paths or raw data.
            raise SamplingRejected('Process sampling rejected') from None
