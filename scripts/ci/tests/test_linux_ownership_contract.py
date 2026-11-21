"""Reference model regressions; no kernel, process, filesystem or network adapter."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('ownership_model',
    Path(__file__).parent / 'fixtures' / 'linux_ownership_model.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def finish(owner, lease):
    for kind in ('fdinfo', 'stat', 'fdinfo', 'exit'):
        owner.consume(lease, owner.observe(lease, kind))
    return owner.finish(lease)


class OwnershipContractTests(unittest.TestCase):
    def test_stable_complete_never_claims_live_proof(self):
        owner=M.OwnerModel(); lease=owner.acquire()
        result=finish(owner,lease)
        self.assertEqual(result['state'],'MODEL_PROTOCOL_COMPLETE')
        for key in ('live_binding_verified','input_authenticity_verified','atomic_snapshot','runner_qualified'):
            self.assertIs(result[key],False)
        self.assertEqual(owner.reads,['fdinfo','stat','fdinfo','exit'])
        with self.assertRaises(M.Rejected): owner.acquire()
        owner.close(lease)
        self.assertEqual(owner.close_attempts, ['fdinfo','pidfd','directory','view'])

    def test_arbitrary_or_other_owner_lease_is_not_authority(self):
        for foreign in (object(), 5, None, M.OwnerModel().acquire()):
            owner=M.OwnerModel(); lease=owner.acquire()
            with self.assertRaises(M.Rejected): owner.observe(foreign,'fdinfo')
            self.assertEqual(owner.reads,[])
            owner.close(lease)

    def test_exclusive_lease_cannot_be_issued_twice(self):
        owner=M.OwnerModel(); lease=owner.acquire()
        with self.assertRaises(M.Rejected): owner.acquire()
        with self.assertRaises(M.Rejected): finish(owner,lease)
        owner.close(lease)

    def test_fd_replacement_and_generation_change_at_every_boundary(self):
        for fault in ('fd_replaced','generation_changed','view_changed'):
            for boundary in range(5):
                with self.subTest(fault=fault,boundary=boundary):
                    owner=M.OwnerModel();lease=owner.acquire()
                    for kind in ('fdinfo','stat','fdinfo','exit')[:boundary]:
                        owner.consume(lease,owner.observe(lease,kind))
                    owner.inject(fault)
                    with self.assertRaises(M.Rejected):
                        for kind in ('fdinfo','stat','fdinfo','exit')[boundary:]:
                            owner.consume(lease,owner.observe(lease,kind))
                        owner.finish(lease)
                    owner.close(lease)
                    self.assertEqual(len(owner.close_attempts),4)

    def test_exit_unknown_and_error_never_produce_evidence(self):
        for fault in ('exited','unknown','permission_error','io_error'):
            owner=M.OwnerModel();lease=owner.acquire();owner.inject(fault)
            with self.assertRaises(M.Rejected): finish(owner,lease)
            self.assertEqual(owner.reads,[])
            owner.close(lease)

    def test_exit_unknown_error_at_all_stages_and_pending_final_record(self):
        for fault in ('exited','unknown','io_error'):
            for boundary in range(5):
                owner=M.OwnerModel();lease=owner.acquire()
                for kind in ('fdinfo','stat','fdinfo','exit')[:boundary]:
                    owner.consume(lease,owner.observe(lease,kind))
                owner.inject(fault)
                with self.assertRaises(M.Rejected):
                    for kind in ('fdinfo','stat','fdinfo','exit')[boundary:]:
                        owner.consume(lease,owner.observe(lease,kind))
                    owner.finish(lease)
                owner.close(lease)
            owner=M.OwnerModel();lease=owner.acquire()
            for kind in ('fdinfo','stat','fdinfo'):
                owner.consume(lease,owner.observe(lease,kind))
            last=owner.observe(lease,'exit');owner.inject(fault)
            with self.assertRaises(M.Rejected): owner.consume(lease,last)
            owner.close(lease)

    def test_same_view_pid_only_not_inner_alias(self):
        for scenario in ({'fdinfo_pid':560,'nspid':(560,4123)},
                         {'fdinfo_pid':0,'nspid':(0,)},
                         {'fdinfo_pid':-1,'nspid':(-1,)},
                         {'nspid':(560,4123)},
                         {'fdinfo_view':'other'}, {'directory_view':'other'},
                         {'stat_pid':560}, {'stat_start':125}):
            with self.subTest(scenario=scenario):
                owner=M.OwnerModel(**scenario);lease=owner.acquire()
                with self.assertRaises(M.Rejected): finish(owner,lease)
                owner.close(lease)

    def test_cached_record_cannot_satisfy_second_read(self):
        owner=M.OwnerModel();lease=owner.acquire()
        first=owner.observe(lease,'fdinfo');owner.consume(lease,first)
        owner.consume(lease,owner.observe(lease,'stat'))
        with self.assertRaises(M.Rejected): owner.consume(lease,first)
        self.assertEqual(owner.reads,['fdinfo','stat'])
        owner.close(lease)

    def test_foreign_record_and_prefetch_are_rejected(self):
        owner=M.OwnerModel();lease=owner.acquire()
        with self.assertRaises(M.Rejected): owner.consume(lease,object())
        owner.close(lease)
        owner=M.OwnerModel();lease=owner.acquire()
        owner.observe(lease,'fdinfo')
        with self.assertRaises(M.Rejected): owner.observe(lease,'stat')
        owner.close(lease)

    def test_mutation_between_issue_and_consume_invalidates_record(self):
        owner=M.OwnerModel();lease=owner.acquire();record=owner.observe(lease,'fdinfo')
        owner.inject('fd_replaced')
        with self.assertRaises(M.Rejected): owner.consume(lease,record)
        owner.close(lease)

    def test_no_early_finish_or_wrong_order(self):
        for operation in ('finish','stat'):
            owner=M.OwnerModel();lease=owner.acquire()
            with self.assertRaises(M.Rejected):
                if operation=='finish': owner.finish(lease)
                else: owner.observe(lease,operation)
            owner.close(lease)

    def test_close_is_once_owned_only_and_uncertain_close_not_retried(self):
        owner=M.OwnerModel();lease=owner.acquire()
        with self.assertRaises(M.Rejected): owner.close(object())
        self.assertEqual(owner.close_attempts,[])
        with self.assertRaises(M.Rejected): owner.close(lease,fail_on='pidfd')
        self.assertEqual(owner.close_attempts,['fdinfo','pidfd','directory','view'])
        owner.close(lease)
        self.assertEqual(len(owner.close_attempts),4)
        with self.assertRaises(M.Rejected): finish(owner,lease)

    def test_result_and_fixture_fields_cannot_be_used_as_live_backend(self):
        owner=M.OwnerModel();lease=owner.acquire();result=finish(owner,lease)
        self.assertEqual(set(result),{'state','live_binding_verified','input_authenticity_verified','atomic_snapshot','runner_qualified'})
        self.assertFalse(hasattr(owner,'open_pid'))
        self.assertFalse(hasattr(owner,'reacquire'))
        owner.close(lease)

if __name__=='__main__': unittest.main()
