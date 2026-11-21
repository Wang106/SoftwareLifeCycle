"""Synthetic descriptor operations only; never opens live proc or real FDs."""
import importlib.util
from pathlib import Path
import unittest
import traceback
from test_linux_proc_observations import stat, status, namespaces
from test_linux_process_sampling import MODULE as sampling, ExitProbe

SPEC = importlib.util.spec_from_file_location('owned_descriptor', Path(__file__).parents[1] / 'linux_owned_descriptor.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class Ops:
    def __init__(self):
        self.directory = object()
        self.identity_value = (7, 11)
        self.calls = []
        self.closed = []
        self.streams = {}
        self.records = {'stat':stat(), 'status':status()}
        self.chunks = None
        self.namespace_error = None
        self.chunk_error_at = None
        self.read_count = 0
        self.close_error = False
        self.link = None
    def identity(self, handle):
        assert handle is self.directory
        return self.identity_value
    def open_relative(self, handle, name):
        assert handle is self.directory
        self.calls.append(('open', name))
        token=object(); self.streams[token]=[self.records[name],0]
        return token
    def read_chunk(self, handle, size):
        assert size > 0
        self.read_count += 1
        self.calls.append(('read',size))
        if self.read_count == self.chunk_error_at: raise OSError('private read error')
        data,position=self.streams[handle]
        amount=min(size,self.chunks or size)
        result=data[position:position+amount]
        self.streams[handle][1]+=len(result)
        return result
    def readlink_relative(self, handle, name, capacity):
        assert handle is self.directory
        self.calls.append(('link', name, capacity))
        if self.namespace_error: raise self.namespace_error
        return (self.link if self.link is not None else namespaces()[name[3:]])[:capacity]
    def close(self, handle):
        self.closed.append(handle)
        if self.close_error: raise OSError('private close error')


def fixture():
    ops=Ops(); binding=object()
    adapter=m.OwnedDirectory(ops,ops.directory,(7,11),binding)
    probe=ExitProbe(binding)
    return ops,adapter,probe


class DescriptorTests(unittest.TestCase):
    def test_sampler_success_and_exact_owned_cleanup(self):
        ops,adapter,probe=fixture();ops.chunks=3
        with adapter:
            result=sampling.SampleOnce(adapter,probe,101,124).sample()
        self.assertFalse(result['runner_qualified'])
        self.assertFalse(result['live_binding_verified'])
        self.assertEqual(result['process']['uid'],1001)
        self.assertEqual(len(ops.closed),4)  # stat/status/stat and directory
        self.assertEqual(len(set(ops.closed)),4)
        self.assertIs(ops.closed[-1],ops.directory)
        adapter.close();self.assertEqual(len(ops.closed),4)
    def test_alive_same_uid_namespace_permission_is_not_exit(self):
        ops,adapter,probe=fixture();ops.namespace_error=PermissionError('private ns')
        with self.assertRaises(sampling.SamplingRejected):
            with adapter: sampling.SampleOnce(adapter,probe,101,124).sample()
        self.assertEqual(adapter.failure_reason,'permission_denied')
        self.assertIs(probe.value,False)
        self.assertEqual([c for c in ops.calls if c[0]=='open'],[('open','stat'),('open','status')])
        self.assertEqual([c[1] for c in ops.calls if c[0]=='link'],['ns/pid'])
        self.assertEqual(len(ops.closed),3)
    def test_exit_before_read_has_no_permission_error(self):
        ops,adapter,probe=fixture();probe.value=True
        with self.assertRaises(sampling.SamplingRejected):
            with adapter: sampling.SampleOnce(adapter,probe,101,124).sample()
        self.assertIsNone(adapter.failure_reason)
        self.assertEqual(ops.calls,[])
        self.assertEqual(ops.closed,[ops.directory])
    def test_chunked_short_reads_continue_to_eof(self):
        ops,adapter,_=fixture();ops.chunks=1
        with adapter: self.assertEqual(adapter.read('stat',4096),stat())
        reads=[c[1] for c in ops.calls if c[0]=='read']
        self.assertEqual(len(reads),len(stat())+1)
        self.assertTrue(all(size>0 for size in reads))
    def test_exact_limit_requires_positive_eof_probe(self):
        ops,adapter,_=fixture();ops.records['stat']=b'a'*4096
        with adapter: self.assertEqual(adapter.read('stat',4096),b'a'*4096)
        self.assertEqual([c[1] for c in ops.calls if c[0]=='read'],[4096,1])
    def test_valid_limit_prefix_plus_byte_never_reaches_parser(self):
        ops,adapter,probe=fixture()
        prefix=status()+b'Padding:\t'+b'x'*(16384-len(status())-10)+b'\n'
        self.assertEqual(len(prefix),16384)
        ops.records['status']=prefix+b'X'
        with self.assertRaises(sampling.SamplingRejected):
            with adapter: sampling.SampleOnce(adapter,probe,101,124).sample()
        self.assertEqual(adapter.failure_reason,'invalid_record')
        self.assertFalse(any(c[0]=='link' for c in ops.calls))
    def test_midstream_error_returns_no_prefix_and_no_retry(self):
        ops,adapter,_=fixture();ops.chunks=3;ops.chunk_error_at=2
        with adapter:
            with self.assertRaises(m.DescriptorRejected): adapter.read('stat',4096)
            count=len(ops.calls)
            with self.assertRaises(m.DescriptorRejected): adapter.read('stat',4096)
            self.assertEqual(len(ops.calls),count)
        self.assertEqual(adapter.failure_reason,'io_error')
        self.assertEqual(len(ops.closed),2)
    def test_namespace_bounds_use_capacity_not_eof(self):
        for length in (128,129,200):
            ops,adapter,_=fixture();ops.link=b'x'*length
            with adapter:
                if length==128: self.assertEqual(adapter.read('ns/pid',128),ops.link)
                else:
                    with self.assertRaises(m.DescriptorRejected): adapter.read('ns/pid',128)
            self.assertEqual(ops.calls,[('link','ns/pid',129)])
    def test_value_handles_refused_before_ownership_or_io(self):
        ops=Ops()
        for handle in (1000,'1000',True,(),None):
            with self.assertRaises(m.DescriptorRejected):
                m.OwnedDirectory(ops,handle,(7,11),object())
        self.assertEqual(ops.closed,[])
        ops,adapter,_=fixture()
        ops.open_relative=lambda *_: int('1000')
        with adapter:
            with self.assertRaises(m.DescriptorRejected): adapter.read('stat',4096)
        self.assertEqual(ops.closed,[ops.directory])

    def test_directory_alias_never_closed_as_record(self):
        ops,adapter,_=fixture();ops.open_relative=lambda *_:ops.directory
        with adapter:
            with self.assertRaises(m.DescriptorRejected): adapter.read('stat',4096)
        self.assertEqual(ops.closed,[ops.directory])

    def test_interrupt_plus_cleanup_failure_reports_cleanup(self):
        ops,adapter,_=fixture();ops.close_error=True
        def interrupted(*_): raise KeyboardInterrupt()
        ops.read_chunk=interrupted
        with self.assertRaises(m.DescriptorRejected):
            with adapter: adapter.read('stat',4096)
        self.assertEqual(adapter.failure_reason,'cleanup_failed')
        self.assertEqual(len(ops.closed),2)

    def test_fixed_names_and_limits_only(self):
        for name,limit in [('stat',1),('../stat',4096),('/proc/101/stat',4096),('cmdline',4096),('ns/pid',True)]:
            ops,adapter,_=fixture()
            with adapter:
                with self.assertRaises(m.DescriptorRejected): adapter.read(name,limit)
            self.assertEqual(ops.calls,[])
    def test_directory_identity_change_rejects_before_open(self):
        ops,adapter,_=fixture();ops.identity_value=(7,12)
        with adapter:
            with self.assertRaises(m.DescriptorRejected): adapter.read('stat',4096)
        self.assertEqual(ops.calls,[])
        self.assertEqual(adapter.failure_reason,'identity_changed')
    def test_close_failure_is_explicit_never_retried(self):
        ops,adapter,_=fixture();ops.close_error=True
        with self.assertRaises(m.DescriptorRejected):
            with adapter: adapter.read('stat',4096)
        self.assertEqual(adapter.failure_reason,'cleanup_failed')
        self.assertEqual(len(ops.closed),2)
        adapter.close();self.assertEqual(len(ops.closed),2)
    def test_same_pid_new_generation_rejected_by_sampler(self):
        ops,adapter,probe=fixture();ops.records['stat']=stat(start=125)
        with self.assertRaises(sampling.SamplingRejected):
            with adapter: sampling.SampleOnce(adapter,probe,101,124).sample()
        self.assertEqual([c for c in ops.calls if c[0]=='open'],[('open','stat')])
    def test_io_and_cleanup_tracebacks_hide_original_errors(self):
        for cleanup in (False,True):
            ops,adapter,_=fixture()
            ops.close_error=cleanup
            if not cleanup: ops.chunk_error_at=1
            with self.assertRaises(m.DescriptorRejected) as caught:
                with adapter: adapter.read('stat',4096)
            self.assertNotIn('private',''.join(traceback.format_exception(caught.exception)))

    def test_error_diagnostics_do_not_echo_adapter_text(self):
        ops,adapter,_=fixture();ops.namespace_error=PermissionError('secret-path')
        with adapter:
            with self.assertRaises(m.DescriptorRejected) as caught: adapter.read('ns/pid',128)
        self.assertNotIn('secret',str(caught.exception))
        self.assertNotIn('secret-path',''.join(traceback.format_exception(caught.exception)))

if __name__ == '__main__': unittest.main()
