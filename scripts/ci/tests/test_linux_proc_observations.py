"""Entirely synthetic proc bytes; no host process observation."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('proc_observations', Path(__file__).parents[1] / 'linux_proc_observations.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def stat(pid=101, parent=100, start=124, name='chrome ) worker'):
    tail=['S']+['0']*49
    tail[1]=str(parent); tail[19]=str(start)
    return (str(pid)+' ('+name+') '+' '.join(tail)+'\n').encode()


def status():
    return b'Name:\tchrome\nTgid:\t101\nPid:\t101\nPPid:\t100\nUid:\t1001\t1001\t1001\t1001\nSeccomp:\t2\nNoNewPrivs:\t1\nThreads:\t4\n'


def namespaces():
    return {'pid':b'pid:[11]', 'net':b'net:[21]', 'user':b'user:[31]'}


class ProcTests(unittest.TestCase):
    def test_maps_only_observed_fields_without_qualification(self):
        result=m.adapt(stat(),status(),namespaces(),stat())
        self.assertEqual(result['process'], {'pid':101,'start_ticks':124,'uid':1001,'pid_ns':11,'net_ns':21,'user_ns':31,'seccomp':2,'no_new_privs':1})
        self.assertEqual(result['observed_ppid'],100)
        self.assertFalse(result['runner_qualified'])
        self.assertFalse(result['publisher_signature_verified'])
        self.assertNotIn('chrome',str(result))

    def test_non_sandbox_values_are_preserved_not_upgraded(self):
        raw=status().replace(b'Seccomp:\t2',b'Seccomp:\t0').replace(b'NoNewPrivs:\t1',b'NoNewPrivs:\t0')
        result=m.adapt(stat(),raw,namespaces(),stat())
        self.assertEqual(result['process']['seccomp'],0)
        self.assertEqual(result['process']['no_new_privs'],0)
        self.assertFalse(result['runner_qualified'])

    def test_stat_rejects_bounds_and_ambiguous_records(self):
        for raw in [b'',b'x'*4097,stat()+stat(),stat().replace(b'101 (',b'0101 ('),stat().replace(b' S ',b' ? '),stat().replace(b' S ',b' S 0 '),stat(start=-1),stat(pid=0),stat(parent=2**63),stat(start=2**63),stat(name='line\nbreak'),b'\xff']:
            with self.subTest(raw=raw[:30]):
                with self.assertRaises(ValueError): m.parse_stat(raw)

    def test_status_rejects_missing_duplicate_invalid_values(self):
        base=status()
        cases=[b'',b'x'*16385,base+b'Pid:\t101\n',base.replace(b'Pid:\t101\n',b''),base.replace(b'Seccomp:\t2',b'Seccomp:\t3'),base.replace(b'NoNewPrivs:\t1',b'NoNewPrivs:\t2'),base.replace(b'Uid:\t1001\t1001\t1001\t1001',b'Uid:\t1001'),base.replace(b'101',b'+101'),base+b'Bad\x00:\t1\n',base+b'Bad line\n',base.replace(b'101',b'\xff')]
        for raw in cases:
            with self.subTest(raw=raw[:30]):
                with self.assertRaises(ValueError): m.parse_status(raw)

    def test_identity_mismatch_and_privileged_uid_refused(self):
        cases=[(stat(pid=102),status(),stat(pid=102)),(stat(),status().replace(b'PPid:\t100',b'PPid:\t99'),stat()),(stat(),status().replace(b'Tgid:\t101',b'Tgid:\t100'),stat()),(stat(),status(),stat(start=125)),(stat(),status(),stat(parent=99)),(stat(),status().replace(b'1001',b'0'),stat()),(stat(),status().replace(b'Uid:\t1001',b'Uid:\t1002'),stat())]
        for before, raw, after in cases:
            with self.subTest(before=before[:20],raw=raw[:20]):
                with self.assertRaises(ValueError): m.adapt(before,raw,namespaces(),after)

    def test_namespace_types_and_bounds(self):
        for value in [b'net:[11]',b'pid:[0]',b'pid:[01]',b'pid:[-1]',b'pid:[18446744073709551616]',b'pid:[9223372036854775808]',b'pid:[11]\n',b'x'*129,'pid:[11]']:
            with self.subTest(value=value):
                ns=namespaces();ns['pid']=value
                with self.assertRaises(ValueError): m.adapt(stat(),status(),ns,stat())
        ns=namespaces();ns['extra']=b'pid:[11]'
        with self.assertRaises(ValueError): m.adapt(stat(),status(),ns,stat())

    def test_errors_do_not_echo_input(self):
        secret=b'not-a-real-secret'
        for function in [m.parse_stat,m.parse_status]:
            with self.assertRaises(ValueError) as caught: function(secret)
            self.assertNotIn(secret.decode(),str(caught.exception))

if __name__ == '__main__': unittest.main()
