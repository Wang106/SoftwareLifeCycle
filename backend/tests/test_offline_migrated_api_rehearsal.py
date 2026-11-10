"""Default-off entrypoint contracts; no acquisition, daemon, HTTP or DB work."""
from contextlib import ExitStack
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
if importlib.util.find_spec('offline_migrated_api_rehearsal'):
    import offline_migrated_api_rehearsal as m
else:
    m=None
COMMIT='a'*40
STAMP='MIGRATION_REHEARSAL_STARTED_NS'
SCRIPT='scripts/offline_migrated_api_rehearsal.py'
WORKFLOW='.github/workflows/offline-migrated-api-rehearsal.yml'


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(m,'default-off migrated API entrypoint missing')

    def invoke(self,args,*,source_error=None,run_error=None,stamp='current',mutate_stamp=False,signal_error=None):
        self.order=[]; self.handlers=[]; self.output=io.StringIO(); self.error=io.StringIO()
        self.previous=object(); marker=str(time.monotonic_ns()) if stamp=='current' else stamp
        env={} if marker is None else {STAMP:marker}
        def install(sig,handler):
            self.handlers.append((sig,handler))
            if signal_error==len(self.handlers): raise ValueError('PRIVATE')
        def source(commit,budget):
            self.order.append('source'); self.assertEqual(commit,COMMIT)
            self.assertIs(type(budget),m.joint.builder.Budget)
            self.assertIsNot(self.handlers[0][1],self.previous)
            if mutate_stamp: os.environ[STAMP]=str(time.monotonic_ns())
            if source_error is not None: raise source_error
        def run(commit,*,include_api):
            self.order.append('run'); self.assertEqual(commit,COMMIT); self.assertIs(include_api,True)
            self.assertEqual(os.environ[STAMP],marker)
            if run_error is not None: raise run_error
            return {'synthetic_contract':True}
        with patch.dict(os.environ,env,clear=True),patch.object(m,'verify_sources',side_effect=source), \
             patch.object(m.joint,'run',side_effect=run),patch.object(m.signal,'getsignal',return_value=self.previous), \
             patch.object(m.signal,'signal',side_effect=install),patch('sys.stdout',self.output),patch('sys.stderr',self.error):
            return m.main(args)

    def test_import_and_missing_or_unknown_arguments_never_run(self):
        for args in ([],['--run'],['--expected-commit',COMMIT],
                     ['--run','--expected-commit',COMMIT,'--database-url','PRIVATE'],
                     ['--run','--expected-commit','A'*40]):
            with self.subTest(args=args):
                self.assertEqual(self.invoke(args),2); self.assertEqual(self.order,[])
                self.assertEqual(self.handlers,[]); self.assertEqual(self.output.getvalue(),'')
                self.assertNotIn('PRIVATE',self.error.getvalue())
        with patch.object(m.joint,'run',side_effect=AssertionError('no run')), \
             patch.object(m.joint.builder.migration,'bounded_command',side_effect=AssertionError('no Git')):
            runpy.run_path(str(ROOT/SCRIPT),run_name='import_contract')

    def test_help_exits_without_work_or_signal_change(self):
        with self.assertRaises(SystemExit) as caught: self.invoke(['--help'])
        self.assertEqual(caught.exception.code,0); self.assertEqual(self.order,[])
        self.assertEqual(self.handlers,[])

    def test_explicit_run_orders_source_then_canonical_coordinator_and_restores_handler(self):
        self.assertEqual(self.invoke(['--run','--expected-commit',COMMIT]),0)
        self.assertEqual(self.order,['source','run'])
        self.assertEqual(json.loads(self.output.getvalue()),{'synthetic_contract':True})
        self.assertEqual(self.handlers[-1],(signal.SIGTERM,self.previous))
        with self.assertRaises(KeyboardInterrupt): self.handlers[0][1](signal.SIGTERM,None)

    def test_missing_bad_future_expired_marker_blocks_before_source(self):
        # A fresh runner can have uptime below 3301 seconds. Clamp-to-one would
        # then create a valid young marker instead of an expired one.
        with patch.object(time,'monotonic',return_value=4000.0), \
             patch.object(time,'monotonic_ns',return_value=4000*10**9):
            now=time.monotonic_ns()
            for stamp in (None,'','0','abc','+1',str(now+10**10),str(now-3301*10**9)):
                with self.subTest(stamp=stamp):
                    self.assertEqual(self.invoke(['--run','--expected-commit',COMMIT],stamp=stamp),2)
                    self.assertEqual(self.order,[]); self.assertEqual(self.output.getvalue(),'')
                    self.assertEqual(self.handlers[-1],(signal.SIGTERM,self.previous))

    def test_valid_markers_on_young_and_old_hosts(self):
        for now,stamp in ((100.0,'1'),(100.0,'current'),(4000.0,'current')):
            with self.subTest(now=now,stamp=stamp), \
                 patch.object(time,'monotonic',return_value=now), \
                 patch.object(time,'monotonic_ns',return_value=int(now*10**9)):
                self.assertEqual(self.invoke(['--run','--expected-commit',COMMIT],stamp=stamp),0)
                self.assertEqual(self.order,['source','run'])
                self.assertEqual(self.handlers[-1],(signal.SIGTERM,self.previous))

    def test_source_and_run_errors_are_sanitized_and_restore_handler(self):
        for field in ('source_error','run_error'):
            for error in (ValueError('PRIVATE'),KeyboardInterrupt()):
                with self.subTest(field=field,error=type(error)):
                    self.assertEqual(self.invoke(['--run','--expected-commit',COMMIT],**{field:error}),2)
                    self.assertEqual(self.output.getvalue(),''); self.assertNotIn('PRIVATE',self.error.getvalue())
                    self.assertEqual(self.handlers[-1],(signal.SIGTERM,self.previous))
                    if field=='source_error': self.assertEqual(self.order,['source'])

    def test_system_exit_restores_handler_without_reclassification(self):
        for field in ('source_error','run_error'):
            error=SystemExit(7)
            with self.subTest(field=field),self.assertRaises(SystemExit) as caught:
                self.invoke(['--run','--expected-commit',COMMIT],**{field:error})
            self.assertIs(caught.exception,error)
            self.assertEqual(self.handlers[-1],(signal.SIGTERM,self.previous))
            self.assertEqual(self.output.getvalue(),'')

    def test_signal_install_or_restore_failure_cannot_emit_success(self):
        for call in (1,2):
            with self.subTest(call=call):
                self.assertEqual(self.invoke(['--run','--expected-commit',COMMIT],signal_error=call),2)
                self.assertEqual(self.output.getvalue(),''); self.assertNotIn('PRIVATE',self.error.getvalue())
                self.assertEqual(self.handlers[-1],(signal.SIGTERM,self.previous))

    def test_marker_change_during_source_check_cannot_refresh_budget(self):
        self.assertEqual(self.invoke(['--run','--expected-commit',COMMIT],mutate_stamp=True),2)
        self.assertEqual(self.order,['source']); self.assertEqual(self.output.getvalue(),'')

    def test_real_main_execution_keeps_single_coordinator_class_and_restores_signal(self):
        program=r'''
import json,os,pathlib,runpy,signal,sys,time
from unittest.mock import patch
root=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(root/'scripts'))
import offline_migration_database_rehearsal as joint
import offline_migrated_api_probe as probe
previous=signal.getsignal(signal.SIGTERM)
os.environ['MIGRATION_REHEARSAL_STARTED_NS']=str(time.monotonic_ns())
def git(command,**kwargs):
    return (root/command[-1].split(':',1)[1]).read_bytes()
def run(commit,*,include_api):
    assert commit=='a'*40 and include_api is True
    assert probe.joint is joint and probe.joint.OwnedContainer is joint.OwnedContainer
    assert signal.getsignal(signal.SIGTERM) is not previous
    return {'canonical':True}
sys.argv=[str(root/'scripts/offline_migrated_api_rehearsal.py'),'--run','--expected-commit','a'*40]
with patch.object(joint,'run',side_effect=run),patch.object(joint.builder.migration,'bounded_command',side_effect=git):
    try: runpy.run_path(sys.argv[0],run_name='__main__')
    except SystemExit as result: assert result.code==0
    else: raise AssertionError('missing main exit')
assert signal.getsignal(signal.SIGTERM) is previous
'''
        result=subprocess.run([sys.executable,'-I','-B','-c',program,str(ROOT)],
                              capture_output=True,timeout=10,check=False)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertEqual(json.loads(result.stdout),{'canonical':True})


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(m,'budget-bounded source validation missing')
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.blobs={SCRIPT:b'reviewed entrypoint\n',WORKFLOW:b'reviewed workflow\n'}
        for path,raw in self.blobs.items():
            target=self.root/path; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(raw)
        self.clock=100.0; self.calls=[]

    def check(self,*,mismatch=None,changed_location=False,clock=None,mutate_budget=False):
        def git(command,**kwargs):
            self.calls.append((command,kwargs)); path=command[-1].split(':',1)[1]
            self.clock+=1
            if mutate_budget: budget.deadline+=1000
            return b'changed' if path==mismatch else self.blobs[path]
        with ExitStack() as stack:
            stack.enter_context(patch.object(m.joint.time,'monotonic',side_effect=lambda:self.clock))
            budget=m.joint.builder.Budget(self.clock)
            if clock is not None: self.clock=clock
            stack.enter_context(patch.object(m,'ROOT',self.root))
            stack.enter_context(patch.object(m,'__file__',str(self.root/SCRIPT)))
            stack.enter_context(patch.object(m.joint,'__file__',str(self.root/('wrong.py' if changed_location else 'scripts/offline_migration_database_rehearsal.py'))))
            stack.enter_context(patch.object(m.joint.builder.migration,'bounded_command',side_effect=git))
            return m.verify_sources(COMMIT,budget)

    def test_exact_sources_git_hardening_and_fd_anchoring(self):
        self.check()
        self.assertEqual({c[-1].split(':',1)[1] for c,_ in self.calls},set(self.blobs))
        for command,kw in self.calls:
            for flag in ('--no-pager','--no-replace-objects','--no-lazy-fetch','core.fsmonitor=false','core.hooksPath=/dev/null'):
                self.assertIn(flag,command)
            self.assertEqual(kw['env']['GIT_CONFIG_GLOBAL'],'/dev/null')
            self.assertEqual(kw['env']['GIT_CONFIG_NOSYSTEM'],'1')
            self.assertEqual(kw['env']['GIT_NO_LAZY_FETCH'],'1')
            self.assertEqual(kw['env']['GIT_TERMINAL_PROMPT'],'0')
            self.assertTrue(kw['cwd'].startswith('/proc/self/fd/'))
            self.assertEqual(kw['pass_fds'],(int(kw['cwd'].rsplit('/',1)[1]),))
            self.assertLessEqual(kw['limit'],65536); self.assertLessEqual(kw['timeout'],20)

    def test_source_mismatch_and_coordinator_location_fail_closed(self):
        for path in self.blobs:
            with self.subTest(path=path),self.assertRaises(m.joint.Blocked): self.check(mismatch=path)
        self.calls=[]
        with self.assertRaises(m.joint.Blocked): self.check(changed_location=True)
        self.assertEqual(self.calls,[])

    def test_each_git_read_preserves_original_downstream_budget(self):
        self.check(clock=2037.0)
        self.assertEqual([kw['timeout'] for _,kw in self.calls],[3.0,2.0])
        self.calls=[]; self.clock=100.0
        with self.assertRaises(m.joint.Blocked): self.check(clock=2040.0)
        self.assertEqual(self.calls,[])

    def test_budget_mutation_rejects_without_second_read(self):
        with self.assertRaises(m.joint.Blocked): self.check(mutate_budget=True)
        self.assertEqual(len(self.calls),1)

    def test_linked_source_is_not_read(self):
        target=self.root/SCRIPT; target.unlink(); target.symlink_to(self.root/WORKFLOW)
        with self.assertRaises((m.joint.Blocked,m.joint.builder.migration.Blocked,OSError)):
            self.check()


class WorkflowTests(unittest.TestCase):
    def text(self):
        path=ROOT/WORKFLOW
        self.assertTrue(path.is_file(),'default-off workflow missing')
        return path.read_text()

    def test_manual_boolean_default_false_and_whole_job_guard(self):
        text=self.text()
        self.assertIn('workflow_dispatch:',text)
        self.assertRegex(text,r'run_migrated_api:\n(?:[^\n]*\n){0,4}        type: boolean\n        required: false\n        default: false')
        self.assertIn('if: ${{ inputs.run_migrated_api == true }}',text)
        for event in ('push:','pull_request:','schedule:','workflow_run:'): self.assertNotIn(event,text)

    def test_original_time_concurrency_limits_and_no_expansion(self):
        text=self.text()
        for expected in ('contents: read','group: offline-migration-database-rehearsal',
                'cancel-in-progress: false','runs-on: ubuntu-24.04','timeout-minutes: 60',
                'persist-credentials: false','actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
                'scripts/offline_migrated_api_rehearsal.py --run --expected-commit "$GITHUB_SHA"'):
            self.assertIn(expected,text)
        self.assertLess(text.index('MIGRATION_REHEARSAL_STARTED_NS='),text.index('actions/checkout@'))
        self.assertEqual(text.count('MIGRATION_REHEARSAL_STARTED_NS='),1)
        for forbidden in ('upload-artifact','actions/cache','secrets.','continue-on-error:','--retry','docker system prune'):
            self.assertNotIn(forbidden,text)
        self.assertNotIn('--include-api',(ROOT/'.github/workflows/offline-migration-database-rehearsal.yml').read_text())


if __name__=='__main__': unittest.main()
