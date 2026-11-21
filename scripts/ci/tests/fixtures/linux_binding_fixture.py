"""Test-only sequential byte integration, never a live backend or binding proof.

Injected operations are invented fixture behavior. Root tokens and model leases
only establish local call identity; they cannot attest OS ownership or PID view.
"""
import importlib.util
from pathlib import Path


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

_ROOT = Path(__file__).parents[2]
_DESCRIPTOR = _load('binding_descriptor', _ROOT / 'linux_owned_descriptor.py')
_FDINFO = _load('binding_fdinfo', _ROOT / 'linux_pidfd_fdinfo.py')
_PROC = _load('binding_proc', _ROOT / 'linux_proc_observations.py')
_MODEL = _load('binding_owner', Path(__file__).with_name('linux_ownership_model.py'))


class IntegrationRejected(ValueError):
    pass


class _FixtureRecord(_DESCRIPTOR.OwnedDirectory):
    # A virtual fixture entry, NOT /proc/<pid>/fdinfo/<fd> or a new live path.
    # Reuse complete bounded reads and exact owned record cleanup unchanged.
    _LIMITS = {'record': 4096}


class FixtureSession:
    """One attempt with synthetic operations; owns only internally issued tokens.

    `ops` implements DescriptorOps plus exited(original_token). No OS operations
    exist here. All reads are sequential, not atomic. A cooperative interface
    cannot impose a hard kernel I/O deadline. The fixed PID/start/view are the
    existing OwnerModel fixture, not caller assertions of real provenance.
    """
    def __init__(self, ops):
        self.owner = _MODEL.OwnerModel()
        self._lease = self.owner.acquire()
        self._ops = ops
        binding = object()
        self._pidfd, self._view = object(), object()
        self._fdinfo = _FixtureRecord(ops, object(), (7, 11), binding)
        self._directory = _DESCRIPTOR.OwnedDirectory(ops, object(), (7, 11), binding)
        self._used = False

    @property
    def pidfd(self):
        return self._pidfd

    def _record(self, kind):
        receipt = self.owner.observe(self._lease, kind)
        if kind == 'fdinfo':
            raw = self._fdinfo.read('record', 4096)
            _FDINFO.match_expected_proc_pid(raw, 4123)
        else:
            parsed = _PROC.parse_stat(self._directory.read('stat', 4096))
            if (parsed['pid'], parsed['start_ticks']) != (4123, 124):
                raise ValueError()
        self.owner.consume(self._lease, receipt)

    def _cleanup(self):
        failed = False
        for close in (self._fdinfo.close, self._directory.close,
                      lambda handle=self._pidfd: self._ops.close(handle),
                      lambda handle=self._view: self._ops.close(handle),
                      lambda: self.owner.close(self._lease)):
            try:
                close()
            except BaseException:
                # Each owned resource gets one attempt, including interruption.
                # Never retry an uncertain close or use broad cleanup.
                failed = True
        return failed

    def run(self):
        if self._used:
            raise IntegrationRejected('Synthetic integration rejected')
        self._used = True
        failed = False
        result = None
        try:
            for kind in ('fdinfo', 'stat', 'fdinfo'):
                self._record(kind)
            receipt = self.owner.observe(self._lease, 'exit')
            if self._ops.exited(self._pidfd) is not False:
                raise ValueError()
            self.owner.consume(self._lease, receipt)
            result = self.owner.finish(self._lease)
            result.update(common_view_verified=False, fresh_bytes_verified=False)
        except Exception:
            failed = True
        finally:
            if self._cleanup():
                raise IntegrationRejected('Synthetic cleanup rejected') from None
        if failed:
            raise IntegrationRejected('Synthetic integration rejected') from None
        return result
