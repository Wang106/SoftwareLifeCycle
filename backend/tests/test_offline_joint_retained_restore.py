"""Standard-library fail-closed joint orchestration tests; no native DB calls."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/offline_joint_retained_restore.py'


def module():
    spec = importlib.util.spec_from_file_location('joint_restore', SCRIPT)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class JointRestoreTests(unittest.TestCase):
    def setUp(self):
        self.m = module()

    def test_default_and_help_never_execute(self):
        for args in ([], ['--help']):
            with patch.object(self.m, 'child') as child:
                self.assertEqual(self.m.main(args), 0)
                child.assert_not_called()

    def test_trust_and_argument_gate_precedes_allocation(self):
        for args in (['produce'], ['recover', '../bad', 'a' * 64, '--trusted-own-synthetic'],
                     ['recover', 'joint-rehearsal-' + 'a' * 32, 'bad', '--trusted-own-synthetic']):
            with patch.object(self.m, 'new_root') as create, patch.object(self.m, 'child') as child:
                self.assertNotEqual(self.m.main(args), 0)
                create.assert_not_called()
                child.assert_not_called()

    def test_nonzero_child_never_accepts_success_stdout(self):
        with self.assertRaises(self.m.Rejected):
            self.m.child('database-produce', ['-c', 'print(\'{"status":"passed"}\'); raise SystemExit(1)'])

    def test_child_requires_single_strict_json_object(self):
        for output in (b'{}\n{}', b'[]', b'{"x":1,"x":2}', b'{"x":NaN}', b'x' * 65537):
            with self.subTest(output=output[:40]), patch.object(self.m, 'capture', return_value=output):
                with self.assertRaises(self.m.Rejected):
                    self.m.child('database-produce', [])

    def test_live_child_pipe_limit_and_deadline(self):
        for code in ('import os; os.write(1, b"x" * 70000)', 'import os; os.write(2, b"x" * 70000)'):
            with self.subTest(code=code), self.assertRaises(self.m.Rejected):
                self.m.child('synthetic-test', ['-c', code])
        with patch.object(self.m.subprocess, 'Popen') as start:
            with self.assertRaises(self.m.Rejected):
                self.m.child('synthetic-test', ['-c', 'print("{}")'], deadline=0)
            start.assert_not_called()
        self.assertEqual(self.m.child('synthetic-test', ['-c', 'print("{}")']), {})

    def test_pair_digest_rejection_precedes_recovery(self):
        with patch.object(self.m, 'read_pair', return_value=(b'{}', {})), patch.object(self.m, 'new_root') as create, patch.object(self.m, 'child') as child:
            with self.assertRaises(self.m.Rejected):
                self.m.recover('joint-rehearsal-' + 'a' * 32, '0' * 64)
            create.assert_not_called()
            child.assert_not_called()

    def test_failure_summary_never_exposes_exception(self):
        with patch.object(self.m, 'produce', side_effect=RuntimeError('postgresql://user:password@host secret')), patch('builtins.print') as output:
            self.assertEqual(self.m.main(['produce', '--trusted-own-synthetic']), 1)
            self.assertNotIn('password', str(output.call_args_list))
            self.assertNotIn('secret', str(output.call_args_list))

    def test_secure_read_rejects_symlink_hardlink_and_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            file = root / 'file'
            file.write_bytes(b'content')
            file.chmod(0o600)
            self.assertEqual(self.m.read_file(root, 'file'), b'content')
            (root / 'link').symlink_to(file)
            with self.assertRaises((self.m.Rejected, OSError)):
                self.m.read_file(root, 'link')
            import os
            os.link(file, root / 'hard')
            with self.assertRaises(self.m.Rejected):
                self.m.read_file(root, 'file')
            (root / 'hard').unlink()
            file.chmod(0o644)
            with self.assertRaises(self.m.Rejected):
                self.m.read_file(root, 'file')


    def fixture_pair(self):
        import shutil
        root = self.m.new_root('joint-rehearsal-')
        self.addCleanup(shutil.rmtree, root)
        run = '0123456789ab'
        swrun = 'software-rehearsal-' + __import__('secrets').token_hex(16)
        swroot = Path('/tmp') / swrun
        swroot.mkdir(mode=0o700)
        self.addCleanup(shutil.rmtree, swroot)
        (swroot / 'bundle').mkdir(mode=0o700)
        files = {name: b'fixture' for name in self.m.SOFTWARE_FILES}
        files['manifest.json'] = b'{}'
        for name, data in files.items():
            self.m.write_file(swroot / 'bundle', name, data)
        sw = dict(scope='SYNTHETIC_ONLY', status='VERIFIED', run_id=swrun, file_count=3,
                  total_bytes=21, manifest_sha256=self.m.digest(b'{}'))
        self.m.write_file(swroot, 'result.json', self.m.encode(sw))
        database = root / 'database'
        database.mkdir(mode=0o700)
        archive, manifest, baseline, proof = self.m.db_names(run)
        metadata = dict(run_id=run, source_commit='1' * 40, checkout_commit='2' * 40,
                        archive_file=archive, ownership_proof=proof)
        base = dict(metadata, status='passed', cleanup='owned_databases_dropped', manifest=manifest)
        for name, data in ((archive, b'dump'), (manifest, self.m.encode(metadata)),
                           (baseline, self.m.encode(base)),
                           (proof, self.m.encode(dict(run_id=run, dropped_databases=[dict(role='source'), dict(role='target')])))):
            self.m.write_file(database, name, data)
        db = dict(status='passed', run_id=run, source_commit='1' * 40, cleanup='owned_databases_dropped')
        pair = dict(version=1, scope='SYNTHETIC_ONLY', status='SEALED', pair_id=root.name,
                    database_run_id=run, database_receipt=db, software_receipt=sw,
                    commits=dict(source_commit='1' * 40, checkout_commit='2' * 40),
                    hashes=self.m.snapshot(root, run, sw))
        self.m.write_file(root, 'pair.json', self.m.encode(pair))
        return root, pair

    def test_mixed_pair_and_changed_inputs_rejected_before_children(self):
        import copy
        root, pair = self.fixture_pair()
        other_root, other = self.fixture_pair()
        bad_pairs = []
        mixed = copy.deepcopy(pair)
        mixed['software_receipt'] = other['software_receipt']
        bad_pairs.append(mixed)
        changed = copy.deepcopy(pair)
        changed['database_run_id'] = 'f' * 12
        bad_pairs.append(changed)
        changed = copy.deepcopy(pair)
        changed['commits']['checkout_commit'] = 'f' * 40
        bad_pairs.append(changed)
        changed = copy.deepcopy(pair)
        changed['version'] = True
        bad_pairs.append(changed)
        for bad in bad_pairs:
            raw = self.m.encode(bad)
            with self.subTest(bad=bad), patch.object(self.m, 'read_pair', return_value=(raw, bad)), patch.object(self.m, 'child') as child, patch.object(self.m, 'new_root') as create:
                with self.assertRaises((self.m.Rejected, OSError)):
                    self.m.recover(root.name, self.m.digest(raw))
                create.assert_not_called()
                child.assert_not_called()
        archive = root / 'database' / self.m.db_names(pair['database_run_id'])[0]
        archive.write_bytes(b'changed')
        with patch.object(self.m, 'child') as child, patch.object(self.m, 'new_root') as create:
            with self.assertRaises(self.m.Rejected):
                self.m.recover(root.name, self.m.digest(self.m.encode(pair)))
            create.assert_not_called()
            child.assert_not_called()

    def test_software_success_database_failure_is_retained_not_success(self):
        import shutil
        root, pair = self.fixture_pair()
        output = self.m.new_root('joint-recovery-')
        self.addCleanup(shutil.rmtree, output)
        sw = dict(pair['software_receipt'], run_id='software-recovery-' + 'b' * 32,
                  source_run_id=pair['software_receipt']['run_id'])
        with patch.object(self.m, 'new_root', return_value=output), patch.object(self.m, 'child', side_effect=[sw, RuntimeError('secret')]) as child:
            with self.assertRaises(RuntimeError):
                self.m.recover(root.name, self.m.digest(self.m.encode(pair)))
        self.assertEqual(child.call_count, 2)
        failure = json.loads((output / 'failure.json').read_bytes())
        self.assertEqual(failure['status'], 'FAILED')
        self.assertEqual(failure['software_run_id'], sw['run_id'])
        self.assertTrue(failure['partial_output_possible'])
        self.assertNotIn('secret', json.dumps(failure))
        self.assertFalse((output / 'result.json').exists())
        self.assertTrue((root / 'pair.json').exists())

    def test_candidate_software_receipt_never_starts_database_recovery(self):
        import shutil
        root, pair = self.fixture_pair()
        output = self.m.new_root('joint-recovery-')
        self.addCleanup(shutil.rmtree, output)
        sw = dict(pair['software_receipt'], status='CANDIDATE', run_id='software-recovery-' + 'b' * 32,
                  source_run_id=pair['software_receipt']['run_id'])
        with patch.object(self.m, 'new_root', return_value=output), patch.object(self.m, 'child', return_value=sw) as child:
            with self.assertRaises(self.m.Rejected):
                self.m.recover(root.name, self.m.digest(self.m.encode(pair)))
        self.assertEqual(child.call_count, 1)
        self.assertFalse((output / 'result.json').exists())

    def test_partial_producer_cannot_seal_pair(self):
        import shutil
        output = self.m.new_root('joint-rehearsal-')
        self.addCleanup(shutil.rmtree, output)
        with patch.object(self.m, 'new_root', return_value=output), patch.object(self.m, 'child', side_effect=RuntimeError('private')) as child:
            with self.assertRaises(RuntimeError):
                self.m.produce()
        self.assertEqual(child.call_count, 1)
        self.assertFalse((output / 'pair.json').exists())
        self.assertEqual(json.loads((output / 'failure.json').read_bytes())['status'], 'FAILED')

    def test_producer_seals_only_after_both_current_child_receipts(self):
        root, pair = self.fixture_pair()
        (root / 'pair.json').unlink()
        with patch.object(self.m, 'new_root', return_value=root), patch.object(self.m.secrets, 'token_hex', return_value=pair['database_run_id']), patch.object(self.m, 'child', side_effect=[pair['database_receipt'], pair['software_receipt']]) as child:
            result = self.m.produce()
        self.assertEqual([call.args[0] for call in child.call_args_list], ['database-produce', 'software-produce'])
        self.assertEqual(result['status'], 'SEALED')
        self.assertEqual(result['manifest_sha256'], self.m.digest((root / 'pair.json').read_bytes()))
        self.assertEqual(json.loads((root / 'pair.json').read_bytes()), pair)

    def successful_recovery(self, mutate=False):
        import shutil
        root, pair = self.fixture_pair()
        output = self.m.new_root('joint-recovery-')
        self.addCleanup(shutil.rmtree, output)
        swroot = Path('/tmp') / ('software-recovery-' + __import__('secrets').token_hex(16))
        swroot.mkdir(mode=0o700)
        self.addCleanup(shutil.rmtree, swroot)
        (swroot / 'restored').mkdir(mode=0o700)
        for name in self.m.SOFTWARE_FILES:
            self.m.write_file(swroot / 'restored', name, b'fixture')
        sw = dict(pair['software_receipt'], run_id=swroot.name, source_run_id=pair['software_receipt']['run_id'])
        newrun = 'abcdef012345'
        def fake_child(stage, arguments, **kwargs):
            if stage == 'software-recover':
                return sw
            self.assertEqual(stage, 'database-recover')
            (output / 'database').mkdir(mode=0o700)
            report = dict(status='passed', run_id=newrun, backup_run_id=pair['database_run_id'],
                          source_accessed=False, originals_unchanged=True,
                          backup_source_commit=pair['commits']['source_commit'],
                          backup_checkout_commit=pair['commits']['checkout_commit'])
            self.m.write_file(output / 'database', 'retained-synthetic-restore.json', self.m.encode(report))
            if mutate:
                (root / 'database' / self.m.db_names(pair['database_run_id'])[0]).write_bytes(b'mutated')
            return dict(status='passed', run_id=newrun, backup_run_id=pair['database_run_id'], cleanup='retained_for_explicit_cleanup')
        with patch.object(self.m, 'new_root', return_value=output), patch.object(self.m.secrets, 'token_hex', return_value=newrun), patch.object(self.m, 'child', side_effect=fake_child) as child:
            if mutate:
                with self.assertRaises(self.m.Rejected):
                    self.m.recover(root.name, self.m.digest(self.m.encode(pair)))
                self.assertFalse((output / 'result.json').exists())
                self.assertTrue((output / 'failure.json').exists())
            else:
                result = self.m.recover(root.name, self.m.digest(self.m.encode(pair)))
                self.assertEqual(result['status'], 'VERIFIED')
                self.assertEqual(result['database_run_id'], newrun)
                self.assertEqual(result['software_run_id'], swroot.name)
                self.assertEqual(json.loads((output / 'result.json').read_bytes())['status'], 'CANDIDATE')
            self.assertEqual(child.call_count, 2)

    def test_success_requires_both_children_and_restored_bytes(self):
        self.successful_recovery()

    def test_post_restore_input_mutation_cannot_report_success(self):
        self.successful_recovery(mutate=True)

    def test_failure_report_write_preserves_first_error(self):
        import shutil
        output = self.m.new_root('joint-rehearsal-')
        self.addCleanup(shutil.rmtree, output)
        original = RuntimeError('first')
        with patch.object(self.m, 'new_root', return_value=output), patch.object(self.m, 'child', side_effect=original), patch.object(self.m, 'write_file', side_effect=OSError('secondary')):
            with self.assertRaises(RuntimeError) as caught:
                self.m.produce()
        self.assertIs(caught.exception, original)

    def test_recovery_diagnostic_failure_preserves_interruptions(self):
        import shutil
        for original in (RuntimeError('first'), KeyboardInterrupt(), SystemExit(2)):
            with self.subTest(error=type(original).__name__):
                root, pair = self.fixture_pair()
                output = self.m.new_root('joint-recovery-')
                self.addCleanup(shutil.rmtree, output)
                with patch.object(self.m, 'new_root', return_value=output), patch.object(self.m, 'child', side_effect=original), patch.object(self.m, 'write_file', side_effect=OSError('secondary')) as write:
                    with self.assertRaises(type(original)) as caught:
                        self.m.recover(root.name, self.m.digest(self.m.encode(pair)))
                self.assertIs(caught.exception, original)
                self.assertEqual(write.call_count, 1)

    def test_capture_shutdown_preserves_primary_and_closes_both_pipes(self):
        from unittest.mock import Mock
        process = Mock()
        process.poll.return_value = None
        process.terminate.side_effect = OSError('secondary')
        original = RuntimeError('original')
        with patch.object(self.m.subprocess, 'Popen', return_value=process), patch.object(self.m.os, 'set_blocking', side_effect=original):
            try:
                self.m.capture([], self.m.time.monotonic() + 300)
            except BaseException as observed:
                self.assertIs(observed, original)
            else:
                self.fail('Primary failure was swallowed')
        process.stdout.close.assert_called_once_with()
        process.stderr.close.assert_called_once_with()
        process.terminate.assert_called_once_with()
        process.kill.assert_not_called()

    def test_capture_first_pipe_close_failure_still_closes_second(self):
        from unittest.mock import Mock, MagicMock
        process = Mock()
        process.poll.return_value = 0
        process.wait.return_value = 0
        original = OSError('stdout close failed')
        process.stdout.close.side_effect = original
        selector = MagicMock()
        selector.__enter__.return_value.get_map.return_value = {}
        with patch.object(self.m.subprocess, 'Popen', return_value=process), patch.object(self.m.os, 'set_blocking'), patch.object(self.m.selectors, 'DefaultSelector', return_value=selector):
            with self.assertRaises(OSError) as caught:
                self.m.capture([], self.m.time.monotonic() + 300)
        self.assertIs(caught.exception, original)
        process.stdout.close.assert_called_once_with()
        process.stderr.close.assert_called_once_with()

    def test_producer_final_persistence_cannot_outlive_budget(self):
        root, pair = self.fixture_pair()
        (root / 'pair.json').unlink()
        now = [0]
        original_write = self.m.write_file
        def slow_final_write(root, name, data):
            original_write(root, name, data)
            if name == 'pair.json':
                now[0] = 601
        with patch.object(self.m, 'new_root', return_value=root), patch.object(self.m.secrets, 'token_hex', return_value=pair['database_run_id']), patch.object(self.m, 'child', side_effect=[pair['database_receipt'], pair['software_receipt']]), patch.object(self.m.time, 'monotonic', side_effect=lambda: now[0]), patch.object(self.m, 'write_file', side_effect=slow_final_write):
            with self.assertRaises(self.m.Rejected):
                self.m.produce()
        self.assertTrue((root / 'failure.json').exists())

    def test_recovery_final_persistence_cannot_outlive_budget(self):
        now = [0]
        original_write = self.m.write_file
        def slow_final_write(root, name, data):
            original_write(root, name, data)
            if name == 'result.json' and root.name.startswith('joint-recovery-'):
                now[0] = 601
        with patch.object(self.m.time, 'monotonic', side_effect=lambda: now[0]), patch.object(self.m, 'write_file', side_effect=slow_final_write):
            with self.assertRaises(self.m.Rejected):
                self.successful_recovery()

    def test_started_lightweight_child_is_stopped_at_deadline(self):
        original_popen = self.m.subprocess.Popen
        children = []
        def started(*args, **kwargs):
            result = original_popen(*args, **kwargs)
            children.append(result)
            return result
        with patch.object(self.m.subprocess, 'Popen', side_effect=started):
            with self.assertRaises(self.m.Rejected):
                self.m.child('synthetic-test', ['-c', 'import time; time.sleep(20)'], deadline=self.m.time.monotonic() + 5.1)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.assertTrue(children[0].stdout.closed)
        self.assertTrue(children[0].stderr.closed)



if __name__ == '__main__':
    unittest.main()
