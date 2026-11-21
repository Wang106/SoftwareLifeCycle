"""Synthetic byte records only; no OS collection or process operations."""
import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('fdinfo_parser',Path(__file__).parents[1]/'linux_pidfd_fdinfo.py')
M=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def record(**updates):
    fields={'pos':'0','flags':'02000002','mnt_id':'5','ino':'42','Pid':'4123','NSpid':'4123\t560'}
    fields.update(updates)
    return ''.join(k+':\t'+v+'\n' for k,v in fields.items()).encode('ascii')


class FdinfoTests(unittest.TestCase):
    def test_visible_metadata_and_namespace_chain(self):
        parsed=M.parse_fdinfo(record())
        self.assertEqual(parsed,{'pos':0,'flags':int('2000002',8),'mnt_id':5,'ino':42,
                                 'pid':4123,'nspid':(4123,560),'visibility':'visible'})

    def test_matching_is_conditional_and_never_live_proof(self):
        result=M.match_expected_proc_pid(record(),4123)
        self.assertEqual(result['observed_pid'],4123)
        self.assertIs(result['numeric_match'],True)
        for key in ('common_view_verified','input_authenticity_verified','live_binding_verified','atomic_snapshot','runner_qualified'):
            self.assertIs(result[key],False)

    def test_inner_namespace_alias_never_matches(self):
        raw=record(Pid='560',NSpid='560\t4123')
        self.assertEqual(M.parse_fdinfo(raw)['pid'],560)
        with self.assertRaises(M.FdinfoRejected): M.match_expected_proc_pid(raw,4123)

    def test_zero_and_detached_are_not_binding_evidence(self):
        for token,state in (('0','not_visible'),('-1','detached')):
            raw=record(Pid=token,NSpid=token)
            self.assertEqual(M.parse_fdinfo(raw)['visibility'],state)
            with self.assertRaises(M.FdinfoRejected): M.match_expected_proc_pid(raw,4123)

    def test_sentinel_or_first_namespace_contradictions_reject(self):
        for pid,chain in [('4123','560\t4123'),('0','0\t1'),('-1','-1\t1'),
                          ('4123','4123\t0'),('4123','4123\t-1'),('0','-1'),('-1','0')]:
            with self.subTest(pid=pid,chain=chain),self.assertRaises(M.FdinfoRejected):
                M.parse_fdinfo(record(Pid=pid,NSpid=chain))

    def test_missing_duplicate_unknown_or_case_changed_fields_reject(self):
        lines=record().splitlines(keepends=True)
        for i in range(6):
            for raw in (b''.join(lines[:i]+lines[i+1:]),record()+lines[i],
                        b''.join(lines[:i]+[lines[(i+1)%6]]+lines[i+1:])):
                with self.assertRaises(M.FdinfoRejected): M.parse_fdinfo(raw)
        for raw in (record()+b'Extra:\t1\n',record().replace(b'Pid:',b'pid:')):
            with self.assertRaises(M.FdinfoRejected): M.parse_fdinfo(raw)

    def test_exact_ascii_tab_lf_profile_and_complete_record(self):
        raw=record()
        for bad in (raw[:-1],raw+b'\n',raw.replace(b'\n',b'\r\n'),raw.replace(b':\t',b': '),
                    raw.replace(b'4123\t560',b'4123 560'),raw+b'\x00',b'\xff'+raw):
            with self.assertRaises(M.FdinfoRejected): M.parse_fdinfo(bad)
        self.assertEqual(M.parse_fdinfo(b''.join(reversed(raw.splitlines(keepends=True))))['pid'],4123)

    def test_bytes_type_and_total_bound(self):
        for bad in (None,'text',bytearray(record()),memoryview(record()),b'',b'x'*4097):
            with self.assertRaises(M.FdinfoRejected): M.parse_fdinfo(bad)

    def test_decimal_numeric_bounds_and_canonical_form(self):
        for field,bad in [('pos',str(2**63)),('mnt_id',str(2**31)),('ino',str(2**64)),
                          ('Pid',str(2**31)),('Pid','-2'),('Pid','+1'),('Pid','01'),
                          ('pos','-1'),('ino','1e2'),('mnt_id',' 5'),('Pid','9'*1000)]:
            with self.subTest(field=field,bad=bad[:20]),self.assertRaises(M.FdinfoRejected):
                M.parse_fdinfo(record(**{field:bad}))
        parsed=M.parse_fdinfo(record(pos=str(2**63-1),mnt_id=str(2**31-1),ino=str(2**64-1),
                                    Pid=str(2**31-1),NSpid=str(2**31-1)))
        self.assertEqual(parsed['ino'],2**64-1)

    def test_flags_octal_not_decimal_or_permissions_assertion(self):
        self.assertEqual(M.parse_fdinfo(record(flags='00'))['flags'],0)
        self.assertEqual(M.parse_fdinfo(record(flags='0'+format(2**32-1,'o')))['flags'],2**32-1)
        for bad in ('2','08','0x2','002','0'+format(2**32,'o'),'-02'):
            with self.assertRaises(M.FdinfoRejected): M.parse_fdinfo(record(flags=bad))

    def test_namespace_level_bound_includes_initial_level_zero(self):
        self.assertEqual(len(M.parse_fdinfo(record(NSpid='\t'.join(['4123']*33)))['nspid']),33)
        for chain in ('', '\t'.join(['4123']*34), '4123\t', '4123\t\t560', '4123\t2147483648'):
            with self.assertRaises(M.FdinfoRejected): M.parse_fdinfo(record(NSpid=chain))

    def test_expected_pid_is_strict_and_cannot_supply_view_override(self):
        for expected in (True,0,-1,2**31,'4123',None):
            with self.assertRaises(M.FdinfoRejected): M.match_expected_proc_pid(record(),expected)
        with self.assertRaises(TypeError): M.match_expected_proc_pid(record(),4123,common_view_verified=True)
        with self.assertRaises(M.FdinfoRejected): M.match_expected_proc_pid(M.parse_fdinfo(record()),4123)

    def test_errors_never_echo_untrusted_content(self):
        import traceback
        try: M.parse_fdinfo(b'private-record-path:\tsecret\n')
        except M.FdinfoRejected as error:
            formatted=''.join(traceback.format_exception_only(error))
            self.assertNotIn('private-record-path',formatted)
            self.assertNotIn('secret',formatted)
        else: self.fail('malformed bytes accepted')

if __name__=='__main__': unittest.main()
