"""Real joint recovery in fresh processes, discovered by the existing PG CI suite."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/offline_joint_retained_restore.py'


class NativeJointPostgresqlTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('TEST_POSTGRES_URL'), 'TEST_POSTGRES_URL required for native joint recovery')
    def test_native_postgresql_joint_pair_new_process_recovery(self):
        from app.ops import postgresql_backup_restore as backup

        def cli(*args):
            return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT / 'backend',
                                  capture_output=True, text=True, timeout=650, check=False)

        def sha(path):
            return hashlib.sha256(path.read_bytes()).hexdigest()

        producer = cli('produce', '--trusted-own-synthetic')
        self.assertEqual(producer.returncode, 0, 'Joint producer failed; inspect private owned evidence')
        produced = json.loads(producer.stdout)
        self.assertEqual(produced['status'], 'SEALED')
        pair_root = Path('/tmp') / produced['pair_id']
        pair_path = pair_root / 'pair.json'
        pair = json.loads(pair_path.read_bytes())
        self.assertEqual(sha(pair_path), produced['manifest_sha256'])
        database = pair_root / 'database'
        original_files = [pair_path, *(database / name for name in pair['hashes']['database'])]
        originals = {str(path): sha(path) for path in original_files}
        baseline = json.loads((database / 'postgresql-backup-restore-rehearsal.json').read_bytes())
        admin = backup.PostgresAdmin.from_url(os.environ['TEST_POSTGRES_URL'])
        for name in baseline['owned_databases'].values():
            self.assertFalse(backup.database_metadata(admin, name)[0])
        original_sw = Path('/tmp') / pair['software_receipt']['run_id']
        # Existing recoverer must use retained bundle, never original source files.
        (original_sw / 'source').rename(original_sw / 'source-not-used')
        software_hashes = {name: sha(original_sw / 'bundle' / name) for name in ('README.txt', 'firmware.bin', 'settings.json', 'manifest.json')}

        # A second successful independent software producer is not interchangeable.
        other = subprocess.run([sys.executable, str(ROOT / 'scripts/offline_software_restore_rehearsal.py')],
                               capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(other.returncode, 0)
        other_sw = Path('/tmp') / json.loads(other.stdout)['run_id']
        manifest_path = original_sw / 'bundle' / 'manifest.json'
        saved_manifest = manifest_path.read_bytes()
        manifest_path.write_bytes((other_sw / 'bundle' / 'manifest.json').read_bytes())
        try:
            refused = cli('recover', produced['pair_id'], produced['manifest_sha256'], '--trusted-own-synthetic')
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(json.loads(refused.stdout)['status'], 'BLOCKED')
        finally:
            manifest_path.write_bytes(saved_manifest)
        self.assertEqual(software_hashes, {name: sha(original_sw / 'bundle' / name) for name in software_hashes})

        recovery = cli('recover', produced['pair_id'], produced['manifest_sha256'], '--trusted-own-synthetic')
        self.assertEqual(recovery.returncode, 0, 'Joint recovery failed; inspect private owned evidence')
        recovered = json.loads(recovery.stdout)
        self.assertEqual(recovered['status'], 'VERIFIED')
        self.assertEqual(recovered['pair_id'], produced['pair_id'])
        self.assertEqual(recovered['manifest_sha256'], produced['manifest_sha256'])
        recovery_root = Path('/tmp') / recovered['run_id']
        evidence = recovery_root / 'database'
        db_report = json.loads((evidence / 'retained-synthetic-restore.json').read_bytes())
        new_run = recovered['database_run_id']
        self.assertNotEqual(new_run, pair['database_run_id'])
        target = backup.owned_database_name(new_run, 'target')
        self.assertEqual(backup.inventory(admin, target, pair['database_run_id'], backup.fixture_ids(pair['database_run_id'])), baseline['source_inventory'])
        self.assertEqual(db_report['target_inventory'], baseline['source_inventory'])
        self.assertTrue(db_report['append_only']['blocked'])
        self.assertTrue(db_report['append_only']['target_unchanged'])
        self.assertFalse(db_report['source_accessed'])
        self.assertTrue(db_report['originals_unchanged'])
        restored_sw = Path('/tmp') / recovered['software_run_id']
        self.assertNotEqual(restored_sw, original_sw)
        self.assertEqual(json.loads((restored_sw / 'recovery-result.json').read_bytes())['status'], 'CANDIDATE')
        for name in ('README.txt', 'firmware.bin', 'settings.json'):
            self.assertEqual(sha(restored_sw / 'restored' / name), software_hashes[name])
        self.assertEqual(originals, {str(path): sha(path) for path in original_files})
        for name in baseline['owned_databases'].values():
            self.assertFalse(backup.database_metadata(admin, name)[0])
        old_proof_path = backup.ownership_proof_path(database, pair['database_run_id'])
        old_proof = backup.load_ownership_proof(old_proof_path, pair['database_run_id'], admin)
        with self.assertRaises(backup.RehearsalError):
            backup.drop_owned_database(admin, new_run, target, 'target', old_proof, old_proof_path)
        self.assertTrue(backup.database_metadata(admin, target)[0])
        proof_path = backup.ownership_proof_path(evidence, new_run)
        proof = backup.load_ownership_proof(proof_path, new_run, admin)
        self.assertEqual(set(proof['created_databases']), {'target'})
        backup.drop_owned_database(admin, new_run, target, 'target', proof, proof_path)
        self.assertFalse(backup.database_metadata(admin, target)[0])
        self.assertEqual(originals, {str(path): sha(path) for path in original_files})
        acceptance = ROOT / 'ci-results' / 'joint-retained-restore.json'
        acceptance.parent.mkdir(exist_ok=True)
        acceptance.write_text(json.dumps(dict(status='passed', producer=produced, recovery=recovered,
                                             native_database_inventory_verified=True, append_only_verified=True,
                                             original_databases_absent=True, software_bytes_verified=True,
                                             mixed_pair_rejected=True, originals_unchanged=True,
                                             old_proof_rejected=True, new_target_only_cleaned=True,
                                             source_commit=baseline['source_commit'], checkout_commit=baseline['checkout_commit']),
                                         sort_keys=True, indent=2) + '\n')
        # No automatic deletion of software roots or failed database resources.
        # This disposable CI runner owns them until teardown.


if __name__ == '__main__':
    unittest.main()
