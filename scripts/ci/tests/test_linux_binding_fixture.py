"""Synthetic byte-to-ownership integration; no actual descriptors or proc reads."""
import importlib.util
from pathlib import Path
import traceback
import unittest
from test_linux_proc_observations import stat

SPEC = importlib.util.spec_from_file_location('binding_fixture', Path(__file__).parent / 'fixtures/linux_binding_fixture.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def fdinfo(pid=4123, chain=None):
    chain = str(pid) if chain is None else chain
    return f'pos:\t0\nflags:\t02000002\nmnt_id:\t5\nino:\t7\nPid:\t{pid}\nNSpid:\t{chain}\n'.encode()


class Ops:
    def __init__(self):
        self.records = [fdinfo(), stat(pid=4123), fdinfo()]
        self.streams = {}
        self.events = []
        self.closed = []
        self.chunk = 3
        self.exit_value = False
        self.error_at = None
        self.no_eof = False
        self.cleanup_error = False
        self.hook = lambda: None
    def identity(self, handle):
        return (7, 11)
    def open_relative(self, handle, name):
        self.events.append(('open', name))
        self.hook()
        token = object()
        self.streams[token] = [self.records.pop(0), 0]
        return token
    def read_chunk(self, handle, size):
        self.events.append(('read', size))
        if len(self.events) == self.error_at: raise OSError('private diagnostic')
        raw, pos = self.streams[handle]
        chunk = raw[pos:pos+min(size,self.chunk)]
        self.streams[handle][1] += len(chunk)
        return chunk if chunk or not self.no_eof else b'X'
    def exited(self, handle):
        self.events.append(('exit', handle))
        if isinstance(self.exit_value, Exception): raise self.exit_value
        return self.exit_value
    def close(self, handle):
        self.closed.append(handle)
        if self.cleanup_error: raise OSError('private cleanup')


class BindingFixtureTests(unittest.TestCase):
    def test_order_short_reads_and_original_exit_handle(self):
        ops=Ops(); session=m.FixtureSession(ops)
        result=session.run()
        self.assertEqual([e[1] for e in ops.events if e[0]=='open'], ['record','stat','record'])
        self.assertEqual(session.owner.reads,['fdinfo','stat','fdinfo','exit'])
        self.assertIs(ops.events[-1][1], session.pidfd)
        self.assertEqual(result['state'],'MODEL_PROTOCOL_COMPLETE')
        for key,value in result.items():
            if key != 'state': self.assertIs(value,False)
        self.assertEqual(len(ops.closed),7) # three record handles plus four roots
        self.assertEqual(len(set(ops.closed)),7)
        before=list(ops.events)
        with self.assertRaises(m.IntegrationRejected): session.run()
        self.assertEqual(ops.events,before)
        self.assertEqual(len(ops.closed),7)
    def test_first_fdinfo_invalid_or_inner_alias_stops_before_stat(self):
        for raw in (fdinfo(560,'560\t4123'),fdinfo(0),fdinfo(-1),fdinfo()+b'extra\n'):
            ops=Ops();ops.records[0]=raw;session=m.FixtureSession(ops)
            with self.assertRaises(m.IntegrationRejected): session.run()
            self.assertEqual(session.owner.reads,['fdinfo'])
            self.assertEqual(len(ops.closed),5)
    def test_generation_or_stat_pid_mismatch_stops_before_second_fdinfo(self):
        for raw in (stat(pid=4123,start=125),stat(pid=560)):
            ops=Ops();ops.records[1]=raw;session=m.FixtureSession(ops)
            with self.assertRaises(m.IntegrationRejected): session.run()
            self.assertEqual(session.owner.reads,['fdinfo','stat'])
            self.assertFalse(any(e[0]=='exit' for e in ops.events))
    def test_second_fdinfo_failure_has_no_exit_or_success(self):
        ops=Ops();ops.records[2]=fdinfo(-1);session=m.FixtureSession(ops)
        with self.assertRaises(m.IntegrationRejected): session.run()
        self.assertEqual(session.owner.reads,['fdinfo','stat','fdinfo'])
        self.assertFalse(any(e[0]=='exit' for e in ops.events))
    def test_exit_unknown_and_error_reject_after_records(self):
        for value in (True,None,0,'false',PermissionError('private')):
            ops=Ops();ops.exit_value=value;session=m.FixtureSession(ops)
            with self.assertRaises(m.IntegrationRejected): session.run()
            self.assertEqual(len(ops.closed),7)
            self.assertEqual(session.owner.reads,['fdinfo','stat','fdinfo','exit'])
    def test_read_error_and_absent_eof_do_not_reach_next_stage(self):
        for mode in ('error','no_eof','over_limit'):
            ops=Ops()
            if mode=='error': ops.error_at=3
            elif mode=='no_eof': ops.no_eof=True
            else: ops.records[0]=b'x'*4097
            session=m.FixtureSession(ops)
            with self.assertRaises(m.IntegrationRejected): session.run()
            self.assertEqual(session.owner.reads,['fdinfo'])
            self.assertEqual(len(ops.closed),5)
    def test_view_replacement_and_generation_fault_at_each_read(self):
        for fault in ('view_changed','fd_replaced','generation_changed','unknown','exited'):
            for stage in (1,2,3):
                ops=Ops();session=m.FixtureSession(ops)
                def hook():
                    if len([e for e in ops.events if e[0]=='open'])==stage:
                        session.owner.inject(fault)
                ops.hook=hook
                with self.assertRaises(m.IntegrationRejected): session.run()
                self.assertEqual(len(session.owner.reads),stage)
                self.assertEqual(len(ops.closed),stage+4)
    def test_cleanup_error_no_success_all_owned_attempted_once(self):
        ops=Ops();ops.cleanup_error=True;session=m.FixtureSession(ops)
        with self.assertRaises(m.IntegrationRejected) as caught: session.run()
        self.assertEqual(len(ops.closed),5)
        self.assertEqual(len(set(ops.closed)),5)
        self.assertEqual(len(session.owner.close_attempts),4)
        self.assertNotIn('private',''.join(traceback.format_exception(caught.exception)))
    def test_interrupt_cleans_without_continuing(self):
        ops=Ops();session=m.FixtureSession(ops)
        def stop(): raise KeyboardInterrupt()
        ops.hook=stop
        with self.assertRaises(KeyboardInterrupt): session.run()
        self.assertEqual(len(ops.closed),4)
        self.assertEqual(session.owner.reads,['fdinfo'])
    def test_public_exit_token_cannot_be_replaced_during_read_or_cleanup(self):
        for phase in ('read','cleanup'):
            ops=Ops();session=m.FixtureSession(ops);original=session.pidfd
            attempts=[]
            def replace():
                try: session.pidfd=object()
                except AttributeError: attempts.append('refused')
                else: attempts.append('replaced')
            if phase=='read': ops.hook=replace
            else:
                close=ops.close
                def replacing_close(handle):
                    replace();close(handle)
                ops.close=replacing_close
            result=session.run()
            self.assertTrue(attempts)
            self.assertEqual(set(attempts),{'refused'})
            self.assertIs(session.pidfd,original)
            self.assertIs(ops.events[-1][1],original)
            self.assertEqual(ops.closed.count(original),1)
            self.assertEqual(result['state'],'MODEL_PROTOCOL_COMPLETE')

    def test_malformed_input_never_yields_partial_result_or_diagnostic(self):
        ops=Ops();ops.error_at=2;session=m.FixtureSession(ops)
        with self.assertRaises(m.IntegrationRejected) as caught: session.run()
        self.assertNotIn('private',''.join(traceback.format_exception(caught.exception)))
        self.assertFalse(hasattr(session,'result'))

if __name__=='__main__': unittest.main()
