"""Same-run lifecycle contracts. All acquisition, Docker, HTTP and DB are mocked."""
import copy
from contextlib import ExitStack
import inspect
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import offline_migration_database_rehearsal as m
import offline_api_image_preparation as preparation
import offline_migrated_api_probe as probe

COMMIT = 'a'*40
MIGRATION_IMAGE = 'sha256:'+'b'*64
API_IMAGE = 'sha256:'+'e'*64
CIDS = {'pg':'c'*64, 'migration':'d'*64, 'api':'f'*64}


def guard_envelope():
    # Synthetic rows only. Runtime parser/comparator still execute unchanged.
    facts=json.loads((ROOT/'deploy/offline/migration-schema-0029.json').read_text())['facts']
    catalog=probe.guard.catalog
    groups={name:[] for name in catalog.LIMITS}
    for name in catalog.FUNCTIONS:
        groups['functions'].append(dict(namespace='public',name=name,identity_arguments='',
            result='trigger',language='plpgsql',security_definer=False,
            body_sha256=facts['function:'+name]['body_sha256'],body_bytes=100))
    for name in catalog.TRIGGERS:
        fact=facts['trigger:'+name]
        groups['triggers'].append(dict(namespace='public',table=fact['table'],name=name,
            function_namespace='public',function_name=fact['function'],function_arguments='',
            type_bits=27,enabled='O',internal=False,constraint=False,argument_count=0,
            argument_bytes=0,has_when=False,definition='PRIVATE_SENTINEL'))
    observation=dict(format='slc-pg16-catalog-observation-v2',status='CATALOG_COLLECTED_NOT_ACCEPTANCE',
        namespace='public',namespace_oid=2200,server_version_num=160015,database_verified=False,
        complete_schema_verified=False,transaction_completed=False,observations=groups)
    return dict(format='slc-migrated-api-guard-observation-v1',rollback_completed=True,
        connection_closed=True,observation=observation)


def snapshot(c, state):
    return {'Id':c.cid, 'Image':c.image_id, 'Name':'/'+c.name, 'Path':c.entrypoint,
        'Args':list(c.args), 'Config':{'Image':c.image_id,
            'Labels':{m.LABEL:c.token,'org.opencontainers.image.revision':COMMIT},
            'User':c.user,'WorkingDir':c.workdir,'Entrypoint':[c.entrypoint],'Cmd':list(c.args),
            'Healthcheck':{'Test':['NONE']},'Env':[k+'='+v for k,v in c.env.items()],
            'Volumes':{'/var/lib/postgresql/data':{}} if c.kind=='pg' else None,
            'ExposedPorts':{'5432/tcp':{}} if c.kind=='pg' else None},
        'HostConfig':{'NetworkMode':c.network,'PublishAllPorts':False,'Privileged':False,
            'ReadonlyRootfs':True,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges'],
            'Tmpfs':dict(c.tmpfs),'LogConfig':{'Type':'none','Config':{}},
            'RestartPolicy':{'Name':'no','MaximumRetryCount':0},'PidMode':'','IpcMode':'private',
            'CgroupnsMode':'private','Memory':1073741824,'MemorySwap':1073741824,
            'NanoCpus':1000000000,'PidsLimit':128,'ShmSize':8388608},
        'State':{'Status':state,'Running':state=='running','Paused':False,'Restarting':False,
            'Dead':False,'OOMKilled':False,'Error':'','ExitCode':0,'Pid':101 if c.kind=='pg' else 102},
        'Mounts':[], 'NetworkSettings':{'Ports':{},'Networks':
            {'none':{'IPAddress':'','GlobalIPv6Address':'','Gateway':''}} if c.kind=='pg' else {}}}


class LifecycleTests(unittest.TestCase):
    def run_case(self, *, enabled=True, failure=None, prepare_mutation=None,
                 probe_mutation=None, expire_migration_stage=False, preparation_time=0,
                 budget_mutation_after_probe=False, guard_failure=None, guard_mutation=None):
        self.events=[]; self.calls=[]; self.objects=[]; self.states={}; self.clock=100.0
        self.budget=None; self.probe_budget=None; self.source_calls=[]
        self.guard_budget=None; self.guard_program=None; self.guard_calls=0
        real_init=m.OwnedContainer.__init__
        real_probe=probe.run_probe
        def init(c,*args,**kwargs):
            real_init(c,*args,**kwargs); self.objects.append(c)
        def guard_prepare(commit,budget):
            self.events.append('guard_prepare'); self.guard_budget=budget
            self.assertEqual(commit,COMMIT)
            if guard_failure=='prepare': raise m.Blocked('GUARD_PREPARE_FAILURE')
            return 'MOCK_BOUND_GUARD_PROGRAM'
        def build(commit,**kwargs):
            self.events.append('migration_prepare')
            return {'status':m.builder.SUCCESS,'source_commit':commit,'database_connected':False,
                'migrations_executed':False,'containers_removed':2,'image_id':MIGRATION_IMAGE,
                'context_manifest_sha256':'1'*64,'build_context_sha256':'2'*64}
        def prepare(commit,*,root,budget):
            self.events.append('api_prepare'); self.budget=budget
            self.assertEqual(commit,COMMIT); self.assertFalse(Path(root).exists())
            if failure=='prepare': raise m.Blocked('PREPARE_FAILURE')
            self.clock+=preparation_time
            r=preparation.receipt(commit,API_IMAGE,'3'*64,'4'*64)
            if prepare_mutation: prepare_mutation(r)
            return r
        def run_probe(**kwargs):
            self.events.append('api_probe'); self.probe_budget=kwargs['budget']
            self.guard_program=kwargs['guard_program']
            self.assertIs(kwargs['budget'],self.budget)
            pg=next(c for c in self.objects if c.kind=='pg')
            self.assertIs(kwargs['pg'],pg); self.assertFalse(pg.cleaned)
            self.assertEqual(kwargs['netns'],'net:[123]')
            self.assertEqual(kwargs['image_id'],API_IMAGE)
            if expire_migration_stage: self.clock+=310
            r=real_probe(**kwargs)
            if probe_mutation: probe_mutation(r)
            if budget_mutation_after_probe is not False:
                self.clock=3365.0  # Original3400, only5 seconds before reserved3370.
                self.cleanup_start=len(self.calls)
                kwargs['budget'].deadline=budget_mutation_after_probe
            return r
        def command(args,**kwargs):
            self.assertEqual(args[:2],['docker','--host=unix:///var/run/docker.sock'])
            args=args[2:]; self.calls.append((args,kwargs)); self.events.append(args[0])
            if args[0]=='pull': return 0,b''
            if args[:2]==['image','inspect']:
                if args[2]==m.PG_IMAGE:
                    return 0,json.dumps([{'Id':m.PG_ID,'Os':'linux','Architecture':'amd64',
                        'RepoDigests':[m.PG_IMAGE], 'Config':{'Entrypoint':['docker-entrypoint.sh'],
                        'Cmd':['postgres'],'Env':['PGDATA=/var/lib/postgresql/data'],'OnBuild':[]}}]).encode()
                return 0,b'[{}]'
            if args[0]=='create':
                c=next(c for c in self.objects if c.name==args[args.index('--name')+1])
                self.events.append('create_'+c.kind); c.cidfile.write_text(CIDS[c.kind])
                self.states[c.kind]='created'; return 0,CIDS[c.kind].encode()+b'\n'
            c=next(c for c in self.objects if c.cid and c.cid in args)
            if args[:2]==['container','inspect']:
                return 0,json.dumps([snapshot(c,self.states[c.kind])]).encode()
            if args[0]=='start':
                self.states[c.kind]='exited' if c.kind=='migration' else 'running'
                if c.kind=='migration' and failure=='migration': return 1,b''
                return 0,b'MIGRATION_COMMAND_COMPLETED\n' if c.kind=='migration' else c.cid.encode()+b'\n'
            if args[0]=='exec':
                if args[-1]==m.NETWORK_PROBE: return 0,b'net:[123]\n'
                if args[-1]==m.EMPTY_SQL:
                    return 0,json.dumps({'version':160015,'relations':0,'functions':0}).encode()
                if args[-1]==m.OBSERVE_SQL:
                    self.events.append('observe')
                    return 0,json.dumps({} if failure=='observation' else m.EXPECTED_OBSERVATION).encode()
                if 'MOCK_BOUND_GUARD_PROGRAM' in args:
                    self.events.append('guard_collect'); self.guard_calls+=1
                    phase='before' if self.guard_calls==1 else 'after'
                    if guard_failure==phase: return 2,b''
                    if isinstance(guard_failure,tuple) and guard_failure[0]==phase: raise guard_failure[1]
                    if guard_failure=='exhaust_before': self.clock+=120
                    if isinstance(guard_failure,tuple) and guard_failure[0]=='mutate_budget':
                        self.budget.deadline=guard_failure[1]
                    value=guard_envelope()
                    if guard_mutation and phase=='after': guard_mutation(value['observation'])
                    return 0,json.dumps(value).encode()
                if probe.PROCESS_PROGRAM in args: return 0,json.dumps(probe.PROCESS_RECEIPT).encode()
                if probe.PROBE_PROGRAM in args:
                    self.events.append('http:'+args[-1])
                    if isinstance(failure,BaseException): raise failure
                    return (1,b'') if failure=='probe' else (0,json.dumps({'case':args[-1],'passed':True}).encode())
            if args[0]=='rm':
                self.events.append('remove_'+c.kind)
                if failure=='cleanup_'+c.kind: return 1,b''
                if isinstance(failure,tuple) and failure[0]==c.kind: raise failure[1]
                return 0,c.cid.encode()+b'\n'
            self.fail(args)
        with ExitStack() as stack:
            root=stack.enter_context(tempfile.TemporaryDirectory())
            patches=[patch.object(m.tempfile,'mkdtemp',return_value=root),
                patch.object(m,'source_binding',side_effect=lambda *a,**k:self.source_calls.append((a,k))),
                patch.object(m.builder,'run',side_effect=build),
                patch.object(probe.guard,'prepare',side_effect=guard_prepare),
                patch.object(preparation,'prepare',side_effect=prepare),
                patch.object(probe,'run_probe',side_effect=run_probe),
                patch.object(m.builder,'host',return_value=(['docker','--host=unix:///var/run/docker.sock'],{})),
                patch.object(m.builder,'verify_image',return_value={'PATH':'/usr/bin'}),
                patch.object(probe.startup,'verify_image',return_value={'PATH':'/usr/bin'}),
                patch.object(m.builder,'command',side_effect=command),
                patch.object(m.OwnedContainer,'__init__',init),
                patch.object(m.time,'monotonic',side_effect=lambda:self.clock),
                patch.object(m.time,'monotonic_ns',side_effect=lambda:int(self.clock*10**9)),
                patch.dict('os.environ',{'MIGRATION_REHEARSAL_STARTED_NS':'100000000000'})]
            for p in patches: stack.enter_context(p)
            return m.run(COMMIT,include_api=enabled)

    def removals(self):
        return [e for e in self.events if e.startswith('remove_')]

    def test_default_internal_option_is_false(self):
        self.assertIs(inspect.signature(m.run).parameters['include_api'].default,False)

    def test_legacy_mode_never_prepares_or_probes_api(self):
        r=self.run_case(enabled=False)
        self.assertFalse(r['application_started']); self.assertNotIn('api_prepare',self.events)
        self.assertNotIn('api_probe',self.events)
        self.assertEqual(self.removals(),['remove_migration','remove_pg'])

    def test_complete_same_run_order_and_exact_original_budget(self):
        r=self.run_case()
        expected=['migration_prepare','api_prepare','create_pg','create_migration','observe',
                  'api_probe','create_api','remove_api','remove_migration','remove_pg']
        positions=[self.events.index(e) for e in expected]
        self.assertEqual(positions,sorted(positions)); self.assertIs(self.budget,self.probe_budget)
        self.assertEqual(r['status'],'LIMITED_MIGRATED_API_LIFECYCLE_PASSED_NOT_DEPLOYMENT')
        self.assertEqual(r['joint_containers_removed'],3)
        self.assertEqual(r['api_image_id'],API_IMAGE); self.assertTrue(r['application_started'])
        self.assertFalse(r['readonly_role_verified']); self.assertFalse(r['provenance_authenticated'])

    def test_cli_cannot_enable_api(self):
        with patch.object(m,'run',side_effect=AssertionError('must not run')), patch('sys.stderr',new_callable=io.StringIO):
            self.assertEqual(m.main(['--run','--expected-commit',COMMIT,'--include-api']),2)

    def test_truthy_options_are_rejected_before_any_work(self):
        for value in (1,'true',None,[],{}):
            with self.subTest(value=value), self.assertRaises(m.Blocked): self.run_case(enabled=value)
            self.assertFalse(self.events)

    def test_preparation_failure_precedes_pg_and_has_no_cleanup(self):
        with self.assertRaises(m.Blocked): self.run_case(failure='prepare')
        self.assertNotIn('create_pg',self.events); self.assertEqual(self.removals(),[])

    def test_preparation_receipt_is_exact_and_source_bound(self):
        for key,value in [('format','other'),('status','ok'),('source_commit','9'*40),
                ('image_id',MIGRATION_IMAGE),('image_id',m.PG_ID),('image_id','tag'),
                ('application_started',0),('database_connected',True),('provenance_authenticated',True),
                ('context_manifest_sha256','x'),('build_context_sha256',False),('extra',True)]:
            with self.subTest(key=key,value=value), self.assertRaises(m.Blocked):
                self.run_case(prepare_mutation=lambda r:r.update({key:value}))
            self.assertNotIn('create_pg',self.events)

    def test_missing_migration_or_observation_skips_api_and_cleans_owned(self):
        for failure in ('migration','observation'):
            with self.subTest(failure=failure),self.assertRaises(m.Blocked): self.run_case(failure=failure)
            self.assertNotIn('api_probe',self.events)
            self.assertEqual(self.removals(),['remove_migration','remove_pg'])

    def test_api_failure_cleanup_does_not_skip_outer_cleanup(self):
        for failure in ('probe','cleanup_api','cleanup_migration','cleanup_pg'):
            with self.subTest(failure=failure), self.assertRaises(m.Blocked): self.run_case(failure=failure)
            self.assertEqual(self.removals(),['remove_api','remove_migration','remove_pg'])

    def test_probe_control_exception_survives_all_cleanup(self):
        for error in (KeyboardInterrupt(),SystemExit(7)):
            with self.subTest(error=type(error)),self.assertRaises(type(error)) as caught:
                self.run_case(failure=error)
            self.assertIs(caught.exception,error)
            self.assertEqual(self.removals(),['remove_api','remove_migration','remove_pg'])

    def test_outer_cleanup_control_exception_is_preserved(self):
        for kind in ('migration','pg'):
            for error in (KeyboardInterrupt(),SystemExit(7)):
                with self.subTest(kind=kind,error=type(error)),self.assertRaises(type(error)) as caught:
                    self.run_case(failure=(kind,error))
                self.assertIs(caught.exception,error)
                self.assertEqual(self.removals(),['remove_api','remove_migration','remove_pg'])

    def test_probe_receipt_is_exact_before_success(self):
        for key,value in [('source_commit','9'*40),('api_image_id',MIGRATION_IMAGE),('cases_passed',True),
                ('database_ready',1),('api_container_removed',False),('postgres_removed_by_helper',True),
                ('observation_after',{}),('readonly_role_verified',True),('extra',0)]:
            with self.subTest(key=key),self.assertRaises(m.Blocked):
                self.run_case(probe_mutation=lambda r:r.update({key:value}))
            self.assertEqual(self.removals(),['remove_api','remove_migration','remove_pg'])

    def test_api_uses_outer_adapter_after_migration_stage_deadline(self):
        r=self.run_case(expire_migration_stage=True)
        self.assertTrue(r['application_started'])

    def test_mutated_budget_cannot_extend_or_prevent_outer_cleanup(self):
        for deadline in (4400.0,2400.0,None):
            with self.subTest(deadline=deadline),self.assertRaises(m.Blocked) as caught:
                self.run_case(budget_mutation_after_probe=deadline)
            self.assertEqual(str(caught.exception),'BUDGET_CHANGED')
            self.assertEqual(self.removals(),['remove_api','remove_migration','remove_pg'])
            self.assertTrue(self.calls[self.cleanup_start:])
            self.assertTrue(all(0 < kw['timeout'] <= 5 for _,kw in self.calls[self.cleanup_start:]))

    def test_insufficient_remaining_time_stops_before_pg(self):
        with self.assertRaises(m.Blocked): self.run_case(preparation_time=2000)
        self.assertNotIn('create_pg',self.events)


class SourceAndReceiptTests(unittest.TestCase):
    def test_opted_in_binding_covers_loaded_runtime_and_transitive_helpers(self):
        seen=[]
        def read(_fd,args,_limit):
            path=args[1].split(':',1)[1]; seen.append(path)
            return (ROOT/path).read_bytes()
        with patch.object(m.builder.migration,'git_read',side_effect=read):
            m.source_binding(COMMIT,include_api=True)
        self.assertEqual(set(seen),m.API_RUNTIME_SOURCES)
        self.assertTrue(preparation.TOOLS <= set(seen))
        self.assertIn('scripts/offline_migrated_api_probe.py',seen)

    def test_runtime_bytes_and_module_location_fail_before_execution(self):
        def read(_fd,args,_limit): return (ROOT/args[1].split(':',1)[1]).read_bytes()
        with patch.object(m.builder.migration,'git_read',side_effect=read):
            with patch.object(probe,'__file__','/tmp/different_probe.py'),self.assertRaises(m.Blocked):
                m.source_binding(COMMIT,include_api=True)
        with patch.object(m.builder.migration,'git_read',return_value=b'changed'),self.assertRaises(m.Blocked):
            m.source_binding(COMMIT,include_api=True)

    def test_preparation_receipt_rejects_each_missing_field(self):
        good=preparation.receipt(COMMIT,API_IMAGE,'3'*64,'4'*64)
        for key in good:
            value=copy.deepcopy(good); del value[key]
            with self.subTest(key=key),self.assertRaises(m.Blocked):
                m._api_preparation_receipt(value,COMMIT,MIGRATION_IMAGE,preparation)

    def test_probe_receipt_rejects_missing_fields_and_boolean_integer_aliases(self):
        good={'format':'slc-migrated-api-probe-v2','status':'LIMITED_MIGRATED_API_PASSED_NOT_DEPLOYMENT',
            'source_commit':COMMIT,'api_image_id':API_IMAGE,'cases_passed':5,'database_ready':True,
            'api_container_removed':True,'postgres_removed_by_helper':False,
            'observation_before':dict(m.EXPECTED_OBSERVATION),'observation_after':dict(m.EXPECTED_OBSERVATION),
            'guard_coverage':'api-alive-five-http-cases-three-functions-six-triggers',
            'guard_checks_before':probe.guard.expected_checks(),'guard_checks_after':probe.guard.expected_checks(),
            'guard_transactions_closed':2,
            'readonly_role_verified':False,'complete_schema_verified':False,
            'provenance_authenticated':False,'limitations':probe.LIMITATIONS}
        m._api_probe_receipt(good,COMMIT,API_IMAGE,probe)
        for key in good:
            value=copy.deepcopy(good); del value[key]
            with self.subTest(missing=key),self.assertRaises(m.Blocked):
                m._api_probe_receipt(value,COMMIT,API_IMAGE,probe)
        for position in ('observation_before','observation_after'):
            for key,expected in m.EXPECTED_OBSERVATION.items():
                if type(expected) is int:
                    value=copy.deepcopy(good); value[position][key]=bool(expected)
                    with self.subTest(position=position,key=key),self.assertRaises(m.Blocked):
                        m._api_probe_receipt(value,COMMIT,API_IMAGE,probe)

    def test_workflow_remains_without_api_opt_in(self):
        text=(ROOT/'.github/workflows/offline-migration-database-rehearsal.yml').read_text()
        self.assertNotIn('include_api',text); self.assertNotIn('--include-api',text)
        self.assertNotIn('offline_api_image_preparation',text)


if __name__=='__main__': unittest.main()
