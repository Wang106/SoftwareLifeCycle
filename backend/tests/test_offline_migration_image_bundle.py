"""Synthetic migration transfer tests; never build, save, load or start Docker."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
try:
    import offline_migration_image_bundle as m
except ModuleNotFoundError:
    m = None

COMMIT = 'e2038a9462770a29254674dd86c0e7b26b26a221'

class MigrationBundleTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(m, 'missing independent migration image transfer capability')
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.dest = self.root / 'transfer'
        self.config = {'Labels': {'org.opencontainers.image.revision': COMMIT},
                       'Env': ['PYTHON_VERSION=3.12.14'], 'User': '65532:65532',
                       'WorkingDir': '/app', 'Entrypoint': ['/bin/false'], 'Cmd': None}
        self.make_archive()
        self.receipt = {'format': m.BUILDER_FORMAT, 'status': m.BUILDER_SUCCESS,
            'source_commit': COMMIT, 'context_manifest_sha256': 'b'*64,
            'build_context_sha256': 'c'*64, 'image_id': self.image_id,
            'platform': 'linux/amd64', 'wheel_count': 30, 'migration_count': 30,
            'source_file_count': 100, 'default_exit_code': 1, 'containers_removed': 2,
            'database_connected': False, 'migrations_executed': False,
            'limitations': m.LIMITATIONS}

    def test_legacy_0029_receipt_is_rejected(self):
        with self.assertRaises(m.base.BundleError):
            m.validate_receipt(dict(self.receipt,migration_count=29), COMMIT)

    def test_unknown_source_is_rejected_even_if_self_consistent(self):
        unknown = 'a' * 40
        with self.assertRaises(m.base.BundleError):
            m.validate_receipt(dict(self.receipt, source_commit=unknown), unknown)

    def test_manifest_compatibility_is_not_self_asserted(self):
        result=self.export()
        path=self.dest/'manifest.json'; original=path.read_bytes()
        for field, value in [('required_db_revision','0029_changeover_batch_history'),
                             ('source_commit','a'*40),('tool_commit','b'*40),
                             ('format','slc-migration-image-handoff-v1')]:
            with self.subTest(field=field):
                data=json.loads(original); data[field]=value
                raw=m.base.canonical(data); path.write_bytes(raw)
                with self.assertRaises(m.base.BundleError):
                    m.verify_bundle(self.dest,expected_commit=COMMIT,
                        expected_manifest_sha256=hashlib.sha256(raw).hexdigest())
        path.write_bytes(original)

    def test_tool_and_image_commits_are_distinct(self):
        tool='a'*40
        def save(file,*args):
            m.base.write_bytes(file,self.archive);file.written()
        with patch.object(m,'source_binding'),patch.object(m,'build_once',return_value=self.receipt), \
             patch.object(m,'save_image',side_effect=save), \
             patch.object(m.os,'fstatvfs',return_value=type('Space',(),{'f_bavail':32*1024**3,'f_frsize':1})()):
            receipt=m.run(tool,self.dest,self.root)
        self.assertEqual(receipt['tool_commit'],tool)
        self.assertEqual(receipt['image_source_commit'],COMMIT)
        self.assertEqual(m.verify_bundle(self.dest,expected_commit=tool,
            expected_manifest_sha256=receipt['manifest_sha256'])['required_db_revision'],m.REVISION)

    def test_builder_invocation_is_isolated_fixed_and_has_cleanup_grace(self):
        with patch.object(m,'command',return_value=(0,m.base.canonical(self.receipt))) as command, \
             patch.dict(os.environ,{'MIGRATION_REHEARSAL_STARTED_NS':str(m.time.monotonic_ns())}):
            self.assertEqual(m.build_once(self.root,m.Budget.from_environment()),self.receipt)
        args=command.call_args.args[0]; kwargs=command.call_args.kwargs
        self.assertEqual(args[1:4],['-I','-S','-B'])
        self.assertEqual(args[-1],COMMIT)
        self.assertEqual(kwargs['cleanup_grace'],90)
        self.assertNotIn('GITHUB_STEP_SUMMARY',kwargs['env'])
        self.assertLess(kwargs['timeout'],1950)

    def test_pure_config_policy_matches_original_builder(self):
        import offline_migration_image_rehearsal as original
        for key, value in [(None,None),('User','root'),('Cmd',['alembic']),
                           ('Env',['PYTHON_VERSION=3.12.14','DATABASE_URL=secret']),
                           ('Env',['PYTHON_VERSION=3.12.14']),('Entrypoint',['/bin/false'])]:
            config=copy.deepcopy(self.config)
            if key:config[key]=value
            image=[{'Id':self.image_id,'Os':'linux','Architecture':'amd64','Config':config}]
            outcomes=[]
            for checker in (m.verify_image,original.verify_image):
                try:outcomes.append(checker(image,self.image_id,COMMIT))
                except ValueError:outcomes.append('rejected')
            self.assertEqual(*outcomes)

    def test_source_checkout_rejects_ignored_cache_before_import(self):
        import subprocess
        root=self.root/'source';(root/'scripts').mkdir(parents=True)
        (root/'scripts/helper.py').write_text('VALUE = 1\n')
        (root/'.gitignore').write_text('__pycache__/\n')
        env={**m.clean_env(),'GIT_AUTHOR_NAME':'Synthetic','GIT_AUTHOR_EMAIL':'test@example.invalid',
             'GIT_COMMITTER_NAME':'Synthetic','GIT_COMMITTER_EMAIL':'test@example.invalid'}
        def git(*args):
            return subprocess.check_output(['/usr/bin/git',*args],cwd=root,env=env,stderr=subprocess.DEVNULL).decode().strip()
        git('init','-q');git('add','.');git('-c','commit.gpgsign=false','commit','-qm','fixture')
        commit=git('rev-parse','HEAD')
        self.assertEqual(m.checkout(root,commit,('helper',)),root)
        before={str(p.relative_to(root)) for p in root.rglob('*')}
        code,_=m.command([sys.executable,'-I','-S','-B','-c',
            'import sys;sys.path.insert(0,sys.argv[1]);import helper',str(root/'scripts')],
            env=m.clean_env(),timeout=10,cwd=root)
        self.assertEqual(code,0)
        self.assertEqual(before,{str(p.relative_to(root)) for p in root.rglob('*')})
        (root/'scripts/__pycache__').mkdir()
        (root/'scripts/__pycache__/helper.pyc').write_bytes(b'poison')
        self.assertEqual(git('status','--porcelain'),'')
        with self.assertRaises(m.base.BundleError):m.checkout(root,commit,('helper',))

    def test_git_filter_refused_before_status(self):
        with patch.object(m,'git',return_value=b'filter.unsafe.clean\ncommand\0') as git:
            with self.assertRaises(m.base.BundleError):m.checkout(self.root,COMMIT,('helper',))
        self.assertEqual(git.call_count,1)

    def test_short_or_terminated_success_output_is_uncertain(self):
        result={'status':m.EXPORTED,'tool_commit':COMMIT,'manifest_sha256':'b'*64}
        for failure in ('short','exit','interrupt'):
            class Broken:
                def write(self,raw):
                    if failure == 'exit':raise SystemExit(0)
                    if failure == 'interrupt':raise KeyboardInterrupt()
                    return len(raw)-1
                def flush(self):pass
            stderr=io.StringIO()
            with patch.object(m,'run',return_value=result),contextlib.redirect_stdout(Broken()),contextlib.redirect_stderr(stderr):
                self.assertEqual(m.main(['export','--run','--expected-commit',COMMIT,
                    '--destination',str(self.dest),'--source-directory',str(self.root)]),2)
            self.assertIn('BUNDLE_COMPLETION_UNCERTAIN',stderr.getvalue())
            self.assertIn('tool_commit',stderr.getvalue())

    def test_timeout_allows_owned_child_cleanup_then_fails(self):
        class Selector:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def register(self,*args):pass
            def get_map(self):return True
        class Process:
            returncode=None;pid=12345
            def __init__(self):self.stdout=io.BytesIO();self.waits=[]
            def wait(self,timeout):
                self.waits.append(timeout);self.returncode=2;return 2
        process=Process()
        with patch.object(m.subprocess,'Popen',return_value=process), \
             patch.object(m.selectors,'DefaultSelector',Selector), \
             patch.object(m.time,'monotonic',side_effect=[0,2]),patch.object(m.os,'killpg') as kill:
            with self.assertRaises(m.base.BundleError):
                m.command(['synthetic'],env={},timeout=1,cleanup_grace=90)
        kill.assert_called_once_with(12345,signal.SIGTERM)
        self.assertEqual(process.waits,[90]);self.assertTrue(process.stdout.closed)

    def make_archive(self):
        layer = b'synthetic non-runnable fixture'
        config = json.dumps({'os':'linux', 'architecture':'amd64', 'config':self.config,
            'rootfs':{'type':'layers','diff_ids':['sha256:'+hashlib.sha256(layer).hexdigest()]}}).encode()
        self.image_id = 'sha256:'+hashlib.sha256(config).hexdigest()
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w') as tf:
            for name, raw in {'config.json':config, 'layer.tar':layer, 'manifest.json':json.dumps([
                {'Config':'config.json','RepoTags':[], 'Layers':['layer.tar']}]).encode()}.items():
                info = tarfile.TarInfo(name); info.size=len(raw); tf.addfile(info, io.BytesIO(raw))
        self.archive = output.getvalue()

    def export(self):
        def save(file, image_id, budget, env):
            self.assertEqual(image_id, self.receipt['image_id'])
            m.base.write_bytes(file, self.archive); file.written()
        with patch.object(m, 'source_binding') as source, patch.object(m, 'build_once', return_value=self.receipt) as build, \
             patch.object(m, 'save_image', side_effect=save) as saved, \
             patch.object(m.os, 'fstatvfs', return_value=type('Space',(),{'f_bavail':32*1024**3,'f_frsize':1})()):
            result = m.run(COMMIT, self.dest, self.root)
            self.assertEqual(build.call_count,1)
            saved.assert_called_once(); self.assertGreaterEqual(source.call_count, 2)
            return result

    def verify(self, result):
        return m.verify_bundle(self.dest, expected_commit=COMMIT,
            expected_manifest_sha256=result['manifest_sha256'])

    def test_roundtrip_is_separate_readonly_and_redacted(self):
        result = self.export()
        self.assertEqual(set(p.name for p in self.dest.iterdir()), m.FILES | {'COMPLETE'})
        before = {p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.dest.iterdir()}
        with patch.object(m, 'build_once', side_effect=AssertionError), patch('subprocess.Popen', side_effect=AssertionError):
            self.assertEqual(self.verify(result)['status'], m.VERIFIED)
        self.assertEqual(before, {p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.dest.iterdir()})
        self.assertEqual(m.base.FILES, frozenset({'api.tar','web.tar','manifest.json','evidence.json'}))
        self.assertEqual((self.dest/'migration.tar').stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.dest.stat().st_mode & 0o777, 0o700)

    def test_default_and_help_never_run(self):
        with patch.object(m, 'build_once', side_effect=AssertionError), contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.main([]), 2)
            with self.assertRaises(SystemExit) as error: m.main(['--help'])
            self.assertEqual(error.exception.code, 0)

    def test_receipt_strict_types_and_fields(self):
        for key, value in [('wheel_count',True),('containers_removed',True),('database_connected',0),
                           ('migrations_executed',True),('image_id','latest'),('source_commit','d'*40),
                           ('status','old'),('platform','linux/arm64'),('source_file_count',False)]:
            with self.subTest(key=key):
                bad=copy.deepcopy(self.receipt); bad[key]=value
                with self.assertRaises(m.base.BundleError): m.validate_receipt(bad, COMMIT)
        bad=dict(self.receipt, private='SECRET')
        with self.assertRaises(m.base.BundleError): m.validate_receipt(bad, COMMIT)

    def test_wrong_expectations_and_mutation_rejected(self):
        result=self.export()
        for commit, digest in [('d'*40,result['manifest_sha256']),(COMMIT,'e'*64),(COMMIT,None)]:
            with self.subTest(commit=commit,digest=digest), self.assertRaises(m.base.BundleError):
                m.verify_bundle(self.dest,expected_commit=commit,expected_manifest_sha256=digest)
        with (self.dest/'migration.tar').open('ab') as f:f.write(b'x')
        with self.assertRaises(m.base.BundleError):self.verify(result)

    def test_migration_config_required(self):
        for key,value in [('User','root'),('WorkingDir','/'),('Entrypoint',['/bin/sh']),('Cmd',['alembic']),
                          ('Env',['PYTHON_VERSION=3.12.14','DATABASE_URL=secret']),('Volumes',{'/data':{}})]:
            with self.subTest(key=key):
                original=copy.deepcopy(self.config); self.config[key]=value; self.make_archive()
                self.receipt['image_id']=self.image_id
                self.dest=self.root/key
                with self.assertRaises(m.base.BundleError):self.export()
                self.assertFalse((self.dest/'COMPLETE').exists()); self.config=original

    def test_existing_destination_stops_before_builder(self):
        self.dest.mkdir()
        with patch.object(m,'build_once') as build, self.assertRaises(m.base.BundleError): m.run(COMMIT,self.dest,self.root)
        build.assert_not_called()

    def test_failed_builder_never_saves(self):
        with patch.object(m,'source_binding'), patch.object(m,'build_once',side_effect=ValueError('SECRET')), \
             patch.object(m,'save_image') as save, self.assertRaises(m.base.BundleError) as error:
            m.run(COMMIT,self.dest,self.root)
        save.assert_not_called(); self.assertNotIn('SECRET',str(error.exception))

    def test_signal_and_environment_restored(self):
        old=signal.getsignal(signal.SIGALRM); env=os.environ.get('MIGRATION_REHEARSAL_STARTED_NS')
        self.export()
        self.assertEqual(signal.getsignal(signal.SIGALRM),old)
        self.assertEqual(os.environ.get('MIGRATION_REHEARSAL_STARTED_NS'),env)

    def test_capacity_refusal_preserves_no_output(self):
        with patch.object(m,'source_binding'), patch.object(m,'build_once',return_value=self.receipt), \
             patch.object(m.os,'fstatvfs',return_value=type('Space',(),{'f_bavail':0,'f_frsize':1})()), \
             patch.object(m,'save_image') as save, self.assertRaises(m.base.BundleError):
            m.run(COMMIT,self.dest,self.root)
        save.assert_not_called();self.assertFalse(self.dest.exists())

    def test_source_failure_stops_builder(self):
        with patch.object(m,'source_binding',side_effect=ValueError('PRIVATE')), \
             patch.object(m,'build_once') as build, self.assertRaises(m.base.BundleError):
            m.run(COMMIT,self.dest,self.root)
        build.assert_not_called()

    def test_existing_budget_marker_is_not_refreshed(self):
        stamp=str(m.time.monotonic_ns()-2400*10**9)
        def build(*args):
            self.assertEqual(os.environ['MIGRATION_REHEARSAL_STARTED_NS'],stamp)
            return self.receipt
        with patch.dict(os.environ,{'MIGRATION_REHEARSAL_STARTED_NS':stamp}), \
             patch.object(m,'source_binding'), patch.object(m,'build_once',side_effect=build), \
             patch.object(m,'save_image') as save, self.assertRaises(m.base.BundleError):
            m.run(COMMIT,self.dest,self.root)
        save.assert_not_called(); self.assertFalse(self.dest.exists())

    def test_invalid_budget_marker_never_builds(self):
        for stamp in ['0','secret','9'*20]:
            with self.subTest(stamp=stamp), patch.dict(os.environ,{'MIGRATION_REHEARSAL_STARTED_NS':stamp}), \
                 patch.object(m,'build_once') as build, self.assertRaises(m.base.BundleError):
                m.run(COMMIT,self.dest,self.root)
            build.assert_not_called()

    def test_signal_install_failure_restores_environment(self):
        with patch.dict(os.environ,{},clear=True), patch.object(m.signal,'signal',side_effect=ValueError), \
             self.assertRaises(m.base.BundleError):
            try:m.run(COMMIT,self.dest,self.root)
            finally:self.assertNotIn('MIGRATION_REHEARSAL_STARTED_NS',os.environ)

    def test_binding_requires_new_helper_exact_tracked_source(self):
        with patch.object(m,'checkout',side_effect=ValueError) as checked, self.assertRaises(Exception):
            m.source_binding(COMMIT,self.root)
        checked.assert_called_once()

    def test_timer_cancel_failure_still_restores_handler(self):
        previous=signal.getsignal(signal.SIGALRM)
        calls=[]
        def timer(_kind, seconds):
            if seconds == 0:raise OSError('PRIVATE')
        with patch.object(m.signal,'getitimer',return_value=(0.0,0.0)), \
             patch.object(m.signal,'setitimer',side_effect=timer), \
             patch.object(m.signal,'signal',side_effect=lambda *args:calls.append(args)), \
             self.assertRaises(OSError):
            with m.bounded(1):pass
        self.assertEqual(calls[-1],(signal.SIGALRM,previous))

    def test_builder_cannot_replace_budget_marker(self):
        def build(*args):
            os.environ['MIGRATION_REHEARSAL_STARTED_NS']=str(m.time.monotonic_ns())
            return self.receipt
        with patch.object(m,'source_binding') as binding,patch.object(m,'build_once',side_effect=build), \
             patch.object(m,'save_image') as save, self.assertRaises(m.base.BundleError):
            m.run(COMMIT,self.dest,self.root)
        save.assert_not_called();self.assertEqual(binding.call_count,1)

    def test_readonly_verifier_refuses_extra_file_and_links(self):
        result=self.export()
        (self.dest/'secret').write_text('PRIVATE')
        with self.assertRaises(m.base.BundleError):self.verify(result)
        (self.dest/'secret').unlink()
        archive=self.dest/'migration.tar'; archive.rename(self.root/'original')
        archive.symlink_to(self.root/'original')
        with self.assertRaises(m.base.BundleError):self.verify(result)

    def test_completion_close_is_uncertain_and_never_retried(self):
        close=m.base.Descriptor.close; counts={}
        def uncertain(handle):
            fd=handle.fd
            if fd is not None:
                try:is_marker=os.readlink('/proc/self/fd/'+str(fd)).endswith('/COMPLETE')
                except OSError:is_marker=False
                if is_marker:
                    counts[fd]=counts.get(fd,0)+1
                    close(handle)
                    raise OSError('PRIVATE_CLOSE')
            close(handle)
        with patch.object(m.base.Descriptor,'close',uncertain),self.assertRaises(m.base.BundleError) as error:
            self.export()
        self.assertEqual(error.exception.code,'BUNDLE_COMPLETION_UNCERTAIN')
        self.assertEqual(list(counts.values()),[1])
        self.assertEqual(set(error.exception.receipt),{'source_commit','manifest_sha256'})
        self.assertTrue((self.dest/'COMPLETE').exists())

    def test_source_binding_rechecked_after_builder(self):
        with patch.object(m,'source_binding',side_effect=[None,ValueError('PRIVATE')]), \
             patch.object(m,'build_once',return_value=self.receipt), \
             patch.object(m,'save_image') as save,self.assertRaises(m.base.BundleError):
            m.run(COMMIT,self.dest,self.root)
        save.assert_not_called();self.assertFalse(self.dest.exists())

    def test_save_streams_one_id_without_output_path_and_bounds_bytes(self):
        class Selector:
            def __enter__(self):self.active=True;return self
            def __exit__(self,*args):pass
            def register(self,*args):pass
            def unregister(self,*args):self.active=False
            def get_map(self):return self.active
            def select(self,*args):return [(type('Key',(),{'fileobj':process.stdout})(),None)]
        class Process:
            returncode=None;pid=12345
            def __init__(self):
                self.stdout=tempfile.TemporaryFile();self.stdout.write(b'fixture');self.stdout.seek(0)
            def wait(self,timeout):self.returncode=0;return 0
        for limit in [1,100]:
            with self.subTest(limit=limit):
                process=Process();self.dest=self.root/str(limit);self.dest.mkdir()
                with contextlib.ExitStack() as stack:
                    directory=m.base.Directory.open(self.dest,stack)
                    target=m.base.File(directory,'migration.tar',stack,create=True)
                    with patch.object(m.subprocess,'Popen',return_value=process) as popen, \
                         patch.object(m.selectors,'DefaultSelector',Selector),patch.object(m,'MAX_BYTES',limit), \
                         patch.object(m.shutil,'which',return_value='/usr/bin/docker'),patch.object(m.os,'killpg') as kill:
                        if limit == 1:
                            with self.assertRaises(m.base.BundleError):m.save_image(target,self.image_id,m.Budget(m.time.monotonic()),{})
                            kill.assert_called_once_with(12345,signal.SIGKILL)
                        else:
                            m.save_image(target,self.image_id,m.Budget(m.time.monotonic()),{})
                            kill.assert_not_called()
                        self.assertEqual(popen.call_args.args[0],['/usr/bin/docker','--host=unix:///var/run/docker.sock','image','save',self.image_id])
                        self.assertTrue(process.stdout.closed)

    def test_cli_uncertain_receipt_is_safely_projected(self):
        error=m.base.BundleError('BUNDLE_COMPLETION_UNCERTAIN',receipt={'source_commit':COMMIT,'manifest_sha256':'b'*64})
        stderr=io.StringIO();stdout=io.StringIO()
        with patch.object(m,'run',side_effect=error),contextlib.redirect_stderr(stderr),contextlib.redirect_stdout(stdout):
            self.assertEqual(m.main(['export','--run','--expected-commit',COMMIT,'--destination',str(self.dest),'--source-directory',str(self.root)]),2)
        self.assertEqual(stdout.getvalue(),'')
        value=json.loads(stderr.getvalue().splitlines()[-1])
        self.assertEqual(value,{'status':'BUNDLE_COMPLETION_UNCERTAIN','tool_commit':COMMIT,'manifest_sha256':'b'*64})

    def test_restore_failure_after_completion_cannot_report_success(self):
        original=signal.getsignal(signal.SIGTERM); real_signal=signal.signal
        def setter(signum,handler):
            real_signal(signum,handler)
            if signum == signal.SIGTERM and handler == original:raise OSError('PRIVATE_RESTORE')
        with patch.object(m.signal,'signal',side_effect=setter),self.assertRaises(m.base.BundleError) as error:
            self.export()
        self.assertEqual(error.exception.code,'BUNDLE_COMPLETION_UNCERTAIN')
        self.assertNotIn('MIGRATION_REHEARSAL_STARTED_NS',os.environ)

    def test_complete_marker_and_digest_fields_are_strict(self):
        result=self.export()
        raw=json.loads((self.dest/'manifest.json').read_bytes())
        self.assertEqual(raw['context_manifest_sha256'],self.receipt['context_manifest_sha256'])
        self.assertEqual(raw['build_context_sha256'],self.receipt['build_context_sha256'])
        (self.dest/'COMPLETE').write_bytes(b'false')
        with self.assertRaises(m.base.BundleError):self.verify(result)

    def test_final_deadline_checked_after_signal_restoration(self):
        original=signal.getsignal(signal.SIGTERM); real_signal=signal.signal
        now=m.time.monotonic; expired=[False]
        def setter(signum,handler):
            result=real_signal(signum,handler)
            if signum == signal.SIGTERM and handler == original:expired[0]=True
            return result
        with patch.object(m.signal,'signal',side_effect=setter), \
             patch.object(m.time,'monotonic',side_effect=lambda:now()+(4000 if expired[0] else 0)), \
             self.assertRaises(m.base.BundleError) as error:
            self.export()
        self.assertEqual(error.exception.code,'BUNDLE_COMPLETION_UNCERTAIN')
        self.assertTrue((self.dest/'COMPLETE').exists())

    def test_verifier_deadline_checked_after_timer_restoration(self):
        result=self.export();real_signal=signal.signal;now=m.time.monotonic;expired=[False]
        previous=signal.getsignal(signal.SIGALRM)
        def setter(signum,handler):
            value=real_signal(signum,handler)
            if signum == signal.SIGALRM and handler == previous:expired[0]=True
            return value
        with patch.object(m.signal,'signal',side_effect=setter), \
             patch.object(m.time,'monotonic',side_effect=lambda:now()+(700 if expired[0] else 0)), \
             self.assertRaises(m.base.BundleError):self.verify(result)

    def test_existing_alarm_is_not_overwritten(self):
        with patch.object(m.signal,'getitimer',return_value=(5.0,0.0)), \
             patch.object(m.signal,'signal') as setter, self.assertRaises(m.base.BundleError):
            with m.bounded(1):self.fail('must not enter')
        setter.assert_not_called()

    def test_archive_gate_reuses_existing_outer_and_inner_policy(self):
        with patch.object(m.base,'archive_gate',side_effect=m.base.BundleError('BUNDLE_ARCHIVE_REJECTED')) as gate, \
             self.assertRaises(m.base.BundleError):self.export()
        gate.assert_called_once()
        self.assertFalse((self.dest/'COMPLETE').exists())

    def test_full_success_receipt_no_extra_fields(self):
        self.assertIsNone(m.validate_receipt(self.receipt,COMMIT))
        for key in list(self.receipt):
            bad=dict(self.receipt);del bad[key]
            with self.subTest(key=key),self.assertRaises(m.base.BundleError):m.validate_receipt(bad,COMMIT)

    def test_export_stdout_failure_retains_safe_uncertainty_receipt(self):
        result={'status':m.EXPORTED,'tool_commit':COMMIT,'manifest_sha256':'b'*64}
        stderr=io.StringIO()
        class Broken:
            def write(self,_):raise BrokenPipeError('PRIVATE_STDOUT')
        with patch.object(m,'run',return_value=result),contextlib.redirect_stdout(Broken()),contextlib.redirect_stderr(stderr):
            self.assertEqual(m.main(['export','--run','--expected-commit',COMMIT,'--destination',str(self.dest),'--source-directory',str(self.root)]),2)
        self.assertIn('BUNDLE_COMPLETION_UNCERTAIN',stderr.getvalue())
        self.assertIn('b'*64,stderr.getvalue())
        self.assertNotIn('PRIVATE_STDOUT',stderr.getvalue())

if __name__ == '__main__': unittest.main()
