"""Synthetic reference state machine, NOT a Linux backend or security boundary.

Only tests import this file. Facts/events are invented fixture inputs. Internal
receipts model ordering and exclusive ownership; they do not authenticate an OS,
prevent Python introspection, or establish any real descriptor association.
"""


class Rejected(ValueError):
    pass


class OwnerModel:
    _ORDER = ('fdinfo', 'stat', 'fdinfo', 'exit')
    _RESOURCES = ('fdinfo', 'pidfd', 'directory', 'view')
    _FAULTS = frozenset(('fd_replaced', 'generation_changed', 'view_changed',
                        'exited', 'unknown', 'permission_error', 'io_error'))

    def __init__(self, *, fdinfo_pid=4123, nspid=(4123,), stat_pid=4123,
                 stat_start=124, fdinfo_view='proc-view', directory_view='proc-view'):
        self._fixture = (fdinfo_pid, nspid, stat_pid, stat_start,
                         fdinfo_view, directory_view)
        self._lease = None
        self._state = 'NEW'
        self._stage = 0
        self._pending = None
        self._fault = None
        self._closed = False
        self.reads = []
        self.close_attempts = []

    def _reject(self):
        self._state = 'REJECTED'
        self._pending = None
        raise Rejected('Synthetic ownership contract rejected') from None

    def acquire(self):
        # Model-issued ownership; callers cannot supply an association token.
        if self._state != 'NEW': self._reject()
        self._lease = object()
        self._state = 'ACTIVE'
        return self._lease

    def _check(self, lease):
        if (lease is not self._lease or self._lease is None or self._closed or
                self._state != 'ACTIVE' or self._fault is not None):
            self._reject()
        # These are synthetic common-view facts, NOT live namespace evidence.
        if self._fixture[4:] != ('proc-view', 'proc-view'):
            self._reject()

    def inject(self, fault):
        """Simulate a broker-detected lifecycle failure; no real detection exists."""
        if fault not in self._FAULTS: self._reject()
        self._fault = fault

    def observe(self, lease, kind):
        self._check(lease)
        if (self._pending is not None or self._stage >= len(self._ORDER) or
                kind != self._ORDER[self._stage]):
            self._reject()
        receipt = object()
        # Creating a new model record only after the prior record is consumed
        # makes cached/replayed or prefetched receipts invalid in this model.
        self._pending = (receipt, kind)
        self.reads.append(kind)
        return receipt

    def consume(self, lease, receipt):
        self._check(lease)
        if self._pending is None or receipt is not self._pending[0]:
            self._reject()
        kind = self._pending[1]
        pid, nspid, stat_pid, start, _, _ = self._fixture
        if kind == 'fdinfo':
            if (type(pid) is not int or pid != 4123 or type(nspid) is not tuple or
                    not 1 <= len(nspid) <= 32 or nspid[0] != pid or
                    any(type(n) is not int or not 0 < n < 2**31 for n in nspid)):
                self._reject()
        elif kind == 'stat':
            if type(stat_pid) is not int or stat_pid != 4123 or type(start) is not int or start != 124:
                self._reject()
        # exit has no caller-supplied false/true override. _check rejects every
        # injected exited/unknown/error event, including after the final record.
        self._pending = None
        self._stage += 1

    def finish(self, lease):
        self._check(lease)
        if self._pending is not None or self._stage != len(self._ORDER):
            self._reject()
        self._state = 'COMPLETE'
        return {'state':'MODEL_PROTOCOL_COMPLETE', 'live_binding_verified':False,
                'input_authenticity_verified':False, 'atomic_snapshot':False,
                'runner_qualified':False}

    def close(self, lease, *, fail_on=None):
        if self._lease is None or lease is not self._lease:
            self._reject()
        if self._closed: return
        if fail_on is not None and fail_on not in self._RESOURCES: self._reject()
        self._closed = True
        self._pending = None
        # Synthetic close attempts only. All four model-owned resources receive
        # one attempt even when a close outcome is uncertain; no retry/reopen.
        self.close_attempts.extend(self._RESOURCES)
        self._state = 'CLOSED'
        if fail_on is not None: self._reject()
