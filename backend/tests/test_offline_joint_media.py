"""Synthetic joint media verification: never run a container or download media."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'backend/tests'))
import test_offline_media_retention as app_fixture
import test_offline_postgres_image_bundle as pg_fixture
import test_offline_migration_image_bundle as migration_fixture
try:
    import offline_joint_media as joint
except ModuleNotFoundError:
    joint = None


class JointMediaTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(joint, 'missing joint verified-media capability')
        self.app=app_fixture.MediaRetentionTests(methodName='runTest');self.app.setUp()
        self.addCleanup(self.app.doCleanups)
        self.pg=pg_fixture.PostgresBundleTests(methodName='runTest');self.pg.setUp()
        self.addCleanup(self.pg.doCleanups)
        self.pg_receipt=self.pg.export()  # All daemon methods mocked by fixture.
        self.migration=migration_fixture.MigrationBundleTests(methodName='runTest');self.migration.setUp()
        self.addCleanup(self.migration.doCleanups)
        self.migration_receipt=self.migration.export()  # Non-runnable synthetic tar.
        self.inputs={
            'api_web':{'directory':self.app.root,'expected_commit':app_fixture.SOURCE,'manifest_sha256':self.app.digest},
            'postgres':{'directory':self.pg.dest,'expected_commit':pg_fixture.COMMIT,'manifest_sha256':self.pg_receipt['manifest_sha256']},
            'migration':{'directory':self.migration.dest,'expected_commit':migration_fixture.COMMIT,'manifest_sha256':self.migration_receipt['manifest_sha256']}}

    def verify(self):
        return joint.verify(self.inputs)

    def snapshot(self):
        return {role:{p.name:(p.read_bytes(),p.stat().st_mtime_ns,p.stat().st_ino)
                      for p in values['directory'].iterdir()} for role,values in self.inputs.items()}

    def rewrite(self,role,mutate):
        path=self.inputs[role]['directory']/'manifest.json'
        data=json.loads(path.read_bytes());mutate(data)
        raw=joint.bundle.canonical(data);path.write_bytes(raw)
        self.inputs[role]['manifest_sha256']=hashlib.sha256(raw).hexdigest()

    def test_complete_set_is_verified_without_runtime_or_mutation(self):
        before=self.snapshot()
        with patch('subprocess.Popen',side_effect=AssertionError('no process')), \
             patch('socket.create_connection',side_effect=AssertionError('no network')):
            result=self.verify()
        self.assertEqual(result['status'],'MEDIA_SET_VERIFIED_NOT_INSTALLATION_READY')
        self.assertEqual(set(result['images']),{'api','web','postgres','migration'})
        self.assertEqual(result['image_source_commit'],app_fixture.SOURCE)
        self.assertEqual(result['required_db_revision'],'0030_private_upload_sessions')
        self.assertEqual(result['file_count'],13)
        self.assertEqual(result['payload_bytes'],sum(len(raw[0]) for files in before.values() for raw in files.values()))
        for flag in ('installation_ready','database_migrated','database_readonly_role','content_clearance_verified','upload_authorized'):
            self.assertIs(result[flag],False)
        self.assertEqual(before,self.snapshot())
        self.assertNotIn(str(self.app.root),json.dumps(result))

    def test_unknown_app_source_refused_before_files_open(self):
        self.inputs['api_web']['expected_commit']='a'*40
        with patch.object(joint.bundle.Directory,'open') as opened,self.assertRaises(joint.MediaError):self.verify()
        opened.assert_not_called()

    def test_schema_mismatch_rejected_even_with_recomputed_digest(self):
        self.rewrite('migration',lambda d:d.update(required_db_revision='0029_changeover_batch_history'))
        with self.assertRaises(joint.MediaError):self.verify()

    def test_wrong_independent_digest_for_each_handoff(self):
        for role in self.inputs:
            original=self.inputs[role]['manifest_sha256'];self.inputs[role]['manifest_sha256']='0'*64
            with self.subTest(role=role),self.assertRaises(joint.MediaError):self.verify()
            self.inputs[role]['manifest_sha256']=original

    def test_role_directory_swap_is_rejected(self):
        self.inputs['postgres']['directory'],self.inputs['migration']['directory']=self.inputs['migration']['directory'],self.inputs['postgres']['directory']
        with self.assertRaises(joint.MediaError):self.verify()

    def test_same_directory_alias_rejected_before_validators(self):
        self.inputs['postgres']['directory']=self.app.root
        with patch.object(joint.bundle,'verify_files') as validate,self.assertRaises(joint.MediaError):self.verify()
        validate.assert_not_called()

    def test_late_mutation_of_already_verified_handoff_is_rejected(self):
        original=joint.migration.verify_files
        def changed(*args,**kwargs):
            result=original(*args,**kwargs)
            (self.app.root/'evidence.json').write_bytes(b'changed')
            return result
        with patch.object(joint.migration,'verify_files',side_effect=changed),self.assertRaises(joint.MediaError):self.verify()

    def test_total_payload_limit_includes_metadata(self):
        total=sum(p.stat().st_size for item in self.inputs.values() for p in item['directory'].iterdir())
        with patch.object(joint,'MAX_PAYLOAD_BYTES',total):self.verify()
        with patch.object(joint,'MAX_PAYLOAD_BYTES',total-1),self.assertRaises(joint.MediaError):self.verify()

    def cli_args(self):
        args=['verify']
        for role,item in self.inputs.items():
            name=role.replace('_','-')
            for field,suffix in [('directory','directory'),('expected_commit','expected-commit'),('manifest_sha256','manifest-sha256')]:
                args.extend(['--'+name+'-'+suffix,str(item[field])])
        return args

    def test_distinct_tool_commits_preserve_their_own_trust_roles(self):
        tool='b'*40
        self.rewrite('migration',lambda d:d.update(tool_commit=tool))
        self.inputs['migration']['expected_commit']=tool
        result=self.verify()
        self.assertEqual(result['handoffs']['migration']['tool_commit'],tool)
        self.assertEqual(result['handoffs']['postgres']['tool_commit'],pg_fixture.COMMIT)
        self.assertEqual(result['handoffs']['api_web']['image_source_commit'],app_fixture.SOURCE)
        self.assertNotIn('image_source_commit',result['handoffs']['postgres'])
        self.assertEqual(result['images']['postgres']['image_id'],self.pg.image_id)

    def test_wrong_migration_tool_commit_rejected(self):
        self.inputs['migration']['expected_commit']='b'*40
        with self.assertRaises(joint.MediaError):self.verify()

    def test_legacy_and_unknown_source_packages_rejected(self):
        for source in ('576a6452194d36377ea92dc28f3e0ffec1241cf1','a'*40):
            with self.subTest(source=source):
                self.rewrite('migration',lambda d:d.update(source_commit=source))
                with self.assertRaises(joint.MediaError):self.verify()

    def test_missing_extra_nonempty_marker_and_archive_tampering(self):
        for role,item in self.inputs.items():
            with self.subTest(role=role):
                marker=item['directory']/'COMPLETE';marker.unlink()
                with self.assertRaises(joint.MediaError):self.verify()
                marker.write_bytes(b'x')
                with self.assertRaises(joint.MediaError):self.verify()
                marker.write_bytes(b'')
                extra=item['directory']/'database.env';extra.write_bytes(b'PRIVATE_SENTINEL')
                with self.assertRaises(joint.MediaError):self.verify()
                extra.unlink()
                archive=next(item['directory'].glob('*.tar'));raw=archive.read_bytes()
                archive.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
                with self.assertRaises(joint.MediaError):self.verify()
                archive.write_bytes(raw)

    def test_symlink_and_hardlink_are_rejected(self):
        target=self.pg.dest/'postgres.tar';saved=self.pg.root/'saved.tar'
        target.rename(saved);target.symlink_to(saved)
        with self.assertRaises(joint.MediaError):self.verify()
        target.unlink();os.link(saved,target)
        with self.assertRaises(joint.MediaError):self.verify()

    def test_lexical_nesting_rejected_before_input_access(self):
        self.inputs['postgres']['directory']=self.app.root/'nested'
        with patch.object(joint.bundle.Directory,'open') as opened,self.assertRaises(joint.MediaError):self.verify()
        opened.assert_not_called()

    def test_inode_alias_rejected_before_file_validation(self):
        original=joint.bundle.Directory.open;first=[]
        def aliased(path,stack):
            value=original(path,stack)
            if not first:first.append(value)
            return first[0] if path == self.pg.dest else value
        with patch.object(joint.bundle.Directory,'open',side_effect=aliased), \
             patch.object(joint.bundle,'verify_files') as validate,self.assertRaises(joint.MediaError):self.verify()
        validate.assert_not_called()

    def test_directory_replacement_after_validation_is_rejected(self):
        original=joint.migration.verify_files
        def replaced(*args,**kwargs):
            result=original(*args,**kwargs)
            self.app.root.rename(self.app.root.with_name('original'));self.app.root.mkdir()
            return result
        with patch.object(joint.migration,'verify_files',side_effect=replaced),self.assertRaises(joint.MediaError):self.verify()

    def test_duplicate_ids_rejected_after_individual_validators_pass(self):
        path=self.app.root/'manifest.json';data=json.loads(path.read_bytes())
        (self.app.root/'web.tar').write_bytes((self.app.root/'api.tar').read_bytes())
        data['images']['web']={**data['images']['api'],'archive':'web.tar'}
        raw=joint.bundle.canonical(data);path.write_bytes(raw)
        self.inputs['api_web']['manifest_sha256']=hashlib.sha256(raw).hexdigest()
        with joint.assembly._ClosingStack() as stack:
            checked=joint.inputs_checked(self.inputs);opened,total=joint.open_set(checked,stack)
            manifests=joint.verify_pinned(opened,checked)
            with self.assertRaises(joint.MediaError):joint.make_index(manifests,checked,total)

    def test_one_total_timer_no_wrapper_resets(self):
        original=joint.migration.bounded
        with patch.object(joint.migration,'bounded',wraps=original) as timer, \
             patch.object(joint.postgres,'verify_bundle',side_effect=AssertionError), \
             patch.object(joint.migration,'verify_bundle',side_effect=AssertionError):
            self.verify()
        timer.assert_called_once_with(600)

    def test_existing_alarm_not_overwritten_and_expired_result_not_returned(self):
        with patch.object(joint.migration.signal,'getitimer',return_value=(1,0)), \
             patch.object(joint.bundle.Directory,'open') as opened,self.assertRaises(joint.MediaError):self.verify()
        opened.assert_not_called()
        with patch.object(joint.migration.time,'monotonic',side_effect=[0,601]),self.assertRaises(joint.MediaError):self.verify()

    def test_close_failure_never_returns_success_or_retries_close(self):
        original=joint.bundle.Descriptor.close;counts={};failed=[]
        def close(handle):
            fd=handle.fd
            if fd is not None:counts[id(handle)]=counts.get(id(handle),0)+1
            original(handle)
            if fd is not None and not failed:
                failed.append(True);raise OSError('PRIVATE_CLOSE_SENTINEL')
        with patch.object(joint.bundle.Descriptor,'close',close),self.assertRaises(joint.MediaError):self.verify()
        self.assertTrue(failed);self.assertTrue(all(n == 1 for n in counts.values()))

    def test_default_help_and_runtime_flags_do_not_verify(self):
        with patch.object(joint,'verify') as verify,contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(joint.main([]),0)
            with self.assertRaises(SystemExit) as error:joint.main(['--help'])
            self.assertEqual(error.exception.code,0)
            for flag in ('--run','--upload','--load','--destination'):
                self.assertEqual(joint.main(self.cli_args()+[flag]),2)
        verify.assert_not_called()

    def test_cli_success_redaction_short_write_and_late_exit(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):self.assertEqual(joint.main(self.cli_args()),0)
        self.assertEqual(json.loads(out.getvalue())['status'],joint.STATUS)
        result=json.loads(out.getvalue())
        for mode in ('short','exit'):
            class Broken:
                def write(self,raw):
                    if mode == 'exit':raise SystemExit(0)
                    return len(raw)-1
                def flush(self):pass
            err=io.StringIO()
            with patch.object(joint,'verify',return_value=result),contextlib.redirect_stdout(Broken()),contextlib.redirect_stderr(err):
                self.assertEqual(joint.main(self.cli_args()),2)
            self.assertIn('UNCONFIRMED',err.getvalue())
            self.assertNotIn(str(self.app.root),err.getvalue())
        with patch.object(joint,'verify',side_effect=ValueError('PRIVATE_SENTINEL')), \
             contextlib.redirect_stderr(out):self.assertEqual(joint.main(self.cli_args()),2)
        self.assertNotIn('PRIVATE_SENTINEL',out.getvalue())


if __name__=='__main__':unittest.main()
