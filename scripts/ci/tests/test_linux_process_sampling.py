"""Synthetic handles only: no proc access, processes, or network."""
import unittest
from scripts.ci.linux_process_sampling import SampleOnce, SamplingRejected
from test_linux_proc_observations import stat, status, namespaces


class Directory:
    def __init__(self, binding):
        self.binding = binding
        self.calls = []
        self.stats = [stat(), stat()]
        self.failure = None
        self.replace = False
    def read(self, name, limit):
        self.calls.append((name, limit))
        if self.failure: raise self.failure
        if self.replace: self.binding = object()
        if name == 'stat': return self.stats.pop(0)
        if name == 'status': return status()
        return namespaces()[name[3:]]


class ExitProbe:
    def __init__(self, binding):
        self.binding = binding
        self.calls = 0
        self.fail_at = None
        self.value = False
    def exited(self):
        self.calls += 1
        if self.calls == self.fail_at: return True
        return self.value


def fixture():
    binding = object()
    directory, probe = Directory(binding), ExitProbe(binding)
    return directory, probe, SampleOnce(directory, probe, 101, 124)


class SamplingTests(unittest.TestCase):
    def test_complete_is_partial_untrusted_and_nonatomic(self):
        directory, probe, sample = fixture()
        result = sample.sample()
        self.assertEqual(result['process']['pid'], 101)
        for field in ('runner_qualified','publisher_signature_verified','input_authenticity_verified','atomic_snapshot','live_binding_verified'):
            self.assertIs(result[field], False)
        self.assertEqual(directory.calls, [('stat',4096),('status',16384),('ns/pid',128),('ns/net',128),('ns/user',128),('stat',4096)])
        self.assertEqual(probe.calls, 12)
    def test_exit_at_each_boundary_stops_without_retry(self):
        for boundary in range(1,13):
            with self.subTest(boundary=boundary):
                directory, probe, sample = fixture(); probe.fail_at=boundary
                with self.assertRaises(SamplingRejected): sample.sample()
                calls=list(directory.calls)
                with self.assertRaises(SamplingRejected): sample.sample()
                self.assertEqual(directory.calls,calls)
                self.assertEqual(probe.calls,boundary)
    def test_original_identity_mismatch_stops_before_other_reads(self):
        for raw in (stat(start=125),stat(pid=102)):
            directory, probe, sample=fixture();directory.stats[0]=raw
            with self.assertRaises(SamplingRejected): sample.sample()
            self.assertEqual(directory.calls,[('stat',4096)])
    def test_same_pid_new_generation_after_reads_is_rejected(self):
        directory, probe, sample=fixture();directory.stats[1]=stat(start=125)
        with self.assertRaises(SamplingRejected): sample.sample()
        self.assertEqual(len(directory.calls),6)
    def test_permission_or_missing_input_has_fixed_error(self):
        for error in (PermissionError('private path'),FileNotFoundError('private path'),OSError('private path')):
            directory, probe, sample=fixture();directory.failure=error
            with self.assertRaises(SamplingRejected) as caught: sample.sample()
            self.assertNotIn('private',str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)
            self.assertEqual(len(directory.calls),1)
    def test_probe_error_and_unknown_exit_are_rejected(self):
        for value in (None,0,'false',True):
            directory, probe, sample=fixture();probe.value=value
            with self.assertRaises(SamplingRejected): sample.sample()
            self.assertEqual(directory.calls,[])
        directory, probe, sample=fixture()
        def failed(): raise PermissionError('private probe')
        probe.exited=failed
        with self.assertRaises(SamplingRejected): sample.sample()
        self.assertEqual(directory.calls,[])
    def test_binding_mismatch_or_replacement_is_rejected(self):
        directory, probe, sample=fixture();probe.binding=object()
        with self.assertRaises(SamplingRejected): sample.sample()
        self.assertEqual(directory.calls,[])
        directory, probe, sample=fixture();directory.replace=True
        with self.assertRaises(SamplingRejected): sample.sample()
        self.assertEqual(len(directory.calls),1)
    def test_incomplete_or_oversized_bytes_never_accepted(self):
        for raw in (b'',b'x'*4097,None,'text'):
            directory, probe, sample=fixture();directory.stats[0]=raw
            with self.assertRaises(SamplingRejected): sample.sample()
            self.assertEqual(len(directory.calls),1)
    def test_probe_cannot_replace_binding_during_check(self):
        directory, probe, sample=fixture()
        def replaced():
            probe.binding=object()
            return False
        probe.exited=replaced
        with self.assertRaises(SamplingRejected): sample.sample()
        self.assertEqual(directory.calls,[])

    def test_interrupted_attempt_remains_consumed(self):
        directory, probe, sample=fixture()
        def interrupted(): raise KeyboardInterrupt()
        probe.exited=interrupted
        with self.assertRaises(KeyboardInterrupt): sample.sample()
        with self.assertRaises(SamplingRejected): sample.sample()
        self.assertEqual(directory.calls,[])

    def test_success_cannot_be_sampled_again(self):
        directory, probe, sample=fixture();sample.sample()
        with self.assertRaises(SamplingRejected): sample.sample()
        self.assertEqual(len(directory.calls),6)
    def test_invalid_expected_identity_never_reads(self):
        for pid,ticks in ((True,124),(0,124),(101,0),(101,2**63)):
            directory,probe,_=fixture()
            with self.assertRaises(SamplingRejected): SampleOnce(directory,probe,pid,ticks)
            self.assertEqual(directory.calls,[])

if __name__ == '__main__': unittest.main()
