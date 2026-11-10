"""Local synthetic contracts only. Every Docker/HTTP/PG operation is mocked."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import offline_migration_database_rehearsal as joint

if importlib.util.find_spec('offline_migrated_api_probe'):
    import offline_migrated_api_probe as m
else:
    m = None

COMMIT = 'a' * 40
IMAGE = 'sha256:' + 'b' * 64
PG_CID = 'c' * 64
API_CID = 'd' * 64
NETNS = 'net:[123]'


def snapshot(c, state='running', pid=101):
    return {'Id':c.cid, 'Image':c.image_id, 'Name':'/'+c.name,
        'Path':c.entrypoint, 'Args':list(c.args),
        'Config':{'Image':c.image_id,
            'Labels':{joint.LABEL:c.token,'org.opencontainers.image.revision':COMMIT},
            'User':c.user,'WorkingDir':c.workdir,'Entrypoint':[c.entrypoint], 'Cmd':list(c.args),
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
            'Dead':False,'OOMKilled':False,'Error':'','ExitCode':0,'Pid':pid},
        'Mounts':[], 'NetworkSettings':{'Ports':{},'Networks':
            {'none':{'IPAddress':'','GlobalIPv6Address':'','Gateway':''}} if c.kind=='pg' else {}}}


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(m, 'migrated API helper missing')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pg = joint.OwnedContainer(self.root, 'pg', joint.PG_ID, COMMIT,
                                      {'PGDATA':'/var/lib/postgresql/data'})
        self.pg.cid = PG_CID
        self.pg.attempted = True
        self.pg.cidfile.write_text(PG_CID+'\n')
        (self.root/'pg-custody.json').write_text(json.dumps({
            'name':self.pg.name,'label':joint.LABEL,'token':self.pg.token,
            'image_id':joint.PG_ID,'source_commit':COMMIT}))
        self.budget = joint.builder.Budget(joint.time.monotonic())

    def test_no_execution_cli_or_import_side_effect(self):
        self.assertFalse(hasattr(m, 'main'))
        self.assertNotIn("if __name__", (ROOT/'scripts/offline_migrated_api_probe.py').read_text())

    def test_live_custody_is_required_not_receipt(self):
        for value in ({'cid':PG_CID}, None, object()):
            with self.subTest(value=type(value)), self.assertRaises(m.Blocked):
                m._PGLease(value, NETNS, COMMIT)
        self.pg.cleaned = True
        with self.assertRaises(m.Blocked): m._PGLease(self.pg, NETNS, COMMIT)

    def test_missing_custody_or_mismatched_cid_is_rejected(self):
        self.pg.cidfile.write_text(API_CID+'\n')
        with self.assertRaises(m.Blocked): m._PGLease(self.pg, NETNS, COMMIT)
        self.pg.cidfile.write_text(PG_CID+'\n')
        (self.root/'pg-custody.json').write_text('{}')
        with self.assertRaises(m.Blocked): m._PGLease(self.pg, NETNS, COMMIT)

    def test_pg_pid_and_object_state_are_stable(self):
        lease=m._PGLease(self.pg,NETNS,COMMIT)
        def command(args,**kw):
            return (0,json.dumps([snapshot(self.pg,pid=101)]).encode()) if args[:2]==['container','inspect'] else (0,b'net:[123]\n')
        lease.check(command)
        changed=snapshot(self.pg,pid=102)
        with self.assertRaises(m.Blocked): lease.check(lambda *a,**k:(0,json.dumps([changed]).encode()))
        self.pg.env['POSTGRES_DB']='other'
        with self.assertRaises(m.Blocked): lease.check(command)

    def test_container_fixed_environment_and_security(self):
        api=m._APIContainer(self.root,IMAGE,COMMIT,{},PG_CID,NETNS)
        args=api.create_args()
        for value in ('--network=container:'+PG_CID,'--read-only','--user=65532:65532',
                      '--cap-drop=ALL','--security-opt=no-new-privileges','--memory=1g','--pids-limit=128'):
            self.assertIn(value,args)
        self.assertEqual(api.env['READ_ONLY_MODE'],'true')
        self.assertEqual(api.env['SEED_ON_STARTUP'],'false')
        self.assertEqual(api.env['AUTH_MODE'],'disabled')
        self.assertIn('default_transaction_read_only=on',api.env['PGOPTIONS'])
        self.assertEqual(api.env['DATABASE_URL'],'postgresql+psycopg://postgres@127.0.0.1:5432/slc_migration?connect_timeout=5')
        self.assertFalse(any(arg.startswith(('--publish','--volume','--dns','--hostname')) for arg in args))

    def test_api_rejects_pg_cid_and_pid_restart(self):
        api=m._APIContainer(self.root,IMAGE,COMMIT,{},PG_CID,NETNS)
        api.cid=PG_CID
        with self.assertRaises(m.Blocked): api.inspect(lambda *a,**k:(0,json.dumps([snapshot(api)]).encode()),state='running')
        api.cid=API_CID
        api.inspect(lambda *a,**k:(0,json.dumps([snapshot(api)]).encode()),state='running')
        with self.assertRaises(m.Blocked): api.inspect(lambda *a,**k:(0,json.dumps([snapshot(api,pid=102)]).encode()),state='running')

    def test_api_rejects_mutated_environment_before_command(self):
        api=m._APIContainer(self.root,IMAGE,COMMIT,{},PG_CID,NETNS)
        api.env['READ_ONLY_MODE']='false'
        with self.assertRaises(m.Blocked): api.create(lambda *a,**k:self.fail('must not create'))

    def test_probe_cases_have_exact_ready_empty_and_denials(self):
        self.assertEqual(m.CASES['ready'][2],200)
        self.assertEqual(m.CASES['ready'][3]['database_revision'],joint.HEAD)
        for name in ('application_empty','audit_empty'):
            self.assertEqual(m.CASES[name][2],200)
            extra={'kind':'application'} if name=='application_empty' else {'event_type_counts':{}}
            self.assertEqual(m.CASES[name][3],{'items':[],'total':0,'limit':1,'offset':0,'next_offset':None}|extra)
        self.assertEqual(m.CASES['business_denied'][2:4],(403,{'detail':'read_only_mode'}))
        self.assertEqual(m.CASES['identity_disabled'][2],401)

    def test_observation_compares_every_field_and_type(self):
        before=copy.deepcopy(joint.EXPECTED_OBSERVATION)
        m._compare_observations(before,copy.deepcopy(before))
        for key in before:
            bad=dict(before); bad[key]=None
            with self.subTest(key=key), self.assertRaises(m.Blocked): m._compare_observations(before,bad)
        with self.assertRaises(m.Blocked): m._compare_observations(before,before|{'audit_rows':False})

    def test_insufficient_original_budget_prevents_any_command(self):
        self.budget.deadline=joint.time.monotonic()+100
        with self.assertRaises(m.Blocked):
            m.run_probe(pg=self.pg,netns=NETNS,image_id=IMAGE,source_commit=COMMIT,
                command=lambda *a,**k:self.fail('no execution'),budget=self.budget)

    def test_external_targets_and_extra_sql_not_accepted(self):
        for extra in ({'database_url':'PRIVATE'},{'sql':'SELECT 1'},{'container_id':PG_CID}):
            with self.assertRaises(TypeError): m.run_probe(**extra)

    def test_process_program_is_separate_and_does_not_replace_old_probe(self):
        self.assertIn('0100007F:1538',m.PROCESS_PROGRAM)
        self.assertIn('0100007F:1F40',m.PROCESS_PROGRAM)
        self.assertIn("os.readlink('/proc/self/ns/net')",m.PROCESS_PROGRAM)
        self.assertNotIn('0100007F:1538',m.startup.PROCESS_PROGRAM)

    def test_source_and_image_fields_are_not_authentication_claims(self):
        self.assertIn('not provenance authentication',m.__doc__)
        self.assertIn('not a SELECT-only role',m.LIMITATIONS)

    def daemon(self, fail=None):
        test=self
        class FakeDaemon:
            api=None
            removed=False
            running=False
            observations=0
            calls=[]
            def __call__(self,args,**kwargs):
                self.calls.append(args)
                test.assertGreater(kwargs['timeout'],0)
                test.assertLessEqual(kwargs['timeout'],{'create':30,'rm':20}.get(args[0],15))
                if args[:2]==['image','inspect']:
                    value=[{'Id':IMAGE,'Os':'linux','Architecture':'amd64','Variant':'',
                        'Config':{'Labels':{'org.opencontainers.image.revision':COMMIT},
                        'User':'65532:65532','WorkingDir':'/app','Entrypoint':['/bin/false'],
                        'Cmd':None,'Env':['PYTHON_VERSION=3.12.14'],'Volumes':None,
                        'Healthcheck':None,'OnBuild':None}}]
                    return 0,json.dumps(value).encode()
                if args[:2]==['container','inspect']:
                    c=test.pg if args[2]==PG_CID else self.api
                    state='running' if c is test.pg or self.running else 'created'
                    return 0,json.dumps([snapshot(c,state=state,pid=101 if c is test.pg else 201)]).encode()
                if args[0]=='create':
                    if fail=='missing_cid': return 1,b''
                    Path(args[args.index('--cidfile')+1]).write_text(API_CID+'\n')
                    return 0,API_CID.encode()+b'\n'
                if args[0]=='start':
                    self.running=True
                    if fail=='start_interrupt': raise KeyboardInterrupt()
                    return 0,API_CID.encode()+b'\n'
                if args[0]=='exec' and PG_CID in args:
                    if args[-1]==joint.NETWORK_PROBE: return 0,b'net:[123]\n'
                    test.assertEqual(args,joint.psql(PG_CID,joint.OBSERVE_SQL))
                    self.observations+=1
                    if fail in ('post_interrupt','probe_post_interrupt') and self.observations==2:
                        raise KeyboardInterrupt('post interruption')
                    value=dict(joint.EXPECTED_OBSERVATION)
                    if fail=='post_change' and self.observations==2: value['audit_rows']=1
                    return 0,json.dumps(value).encode()
                if args[0]=='exec' and API_CID in args:
                    if args[-2]==m.PROCESS_PROGRAM: return 0,json.dumps(m.PROCESS_RECEIPT).encode()
                    test.assertEqual(args[-2],m.PROBE_PROGRAM)
                    if fail in ('probe','probe_cleanup','probe_cleanup_interrupt','probe_post_interrupt'): return 2,b''
                    return 0,json.dumps({'case':args[-1],'passed':True}).encode()
                if args==['rm','--force',API_CID]:
                    if fail in ('cleanup_interrupt','probe_cleanup_interrupt'):
                        raise KeyboardInterrupt('cleanup interruption')
                    if fail in ('cleanup','probe_cleanup'): return 1,b''
                    self.removed=True
                    return 0,API_CID.encode()+b'\n'
                test.fail('unexpected command '+repr(args[:3]))
        return FakeDaemon()

    def run_fake(self,daemon):
        original=m._APIContainer
        def factory(*args,**kwargs):
            result=original(*args,**kwargs); daemon.api=result; return result
        with patch.object(m,'_APIContainer',side_effect=factory), patch.object(joint.os,'chmod'):
            return m.run_probe(pg=self.pg,netns=NETNS,image_id=IMAGE,source_commit=COMMIT,
                command=daemon,budget=self.budget)

    def test_full_mock_sequence_removes_only_api_before_post_observation(self):
        daemon=self.daemon()
        result=self.run_fake(daemon)
        self.assertTrue(result['database_ready'])
        self.assertTrue(result['api_container_removed'])
        for field in ('readonly_role_verified','complete_schema_verified','provenance_authenticated','postgres_removed_by_helper'):
            self.assertFalse(result[field])
        self.assertEqual(daemon.observations,2)
        self.assertEqual([args for args in daemon.calls if args[0]=='rm'],[['rm','--force',API_CID]])
        remove=daemon.calls.index(['rm','--force',API_CID])
        self.assertIn(joint.psql(PG_CID,joint.OBSERVE_SQL),daemon.calls[remove+1:])
        self.assertEqual(result['observation_before'],result['observation_after'])

    def test_probe_failure_preserved_with_cleanup_and_post_observation(self):
        daemon=self.daemon('probe')
        with self.assertRaisesRegex(m.Blocked,'API_PROBE_REJECTED'): self.run_fake(daemon)
        self.assertTrue(daemon.removed)
        self.assertEqual(daemon.observations,2)

    def test_cleanup_failure_no_second_removal_no_post_snapshot(self):
        daemon=self.daemon('probe_cleanup')
        with self.assertRaisesRegex(m.Blocked,'API_PROBE_REJECTED') as caught: self.run_fake(daemon)
        self.assertIn('API_CLEANUP_UNCONFIRMED',caught.exception.__notes__)
        self.assertEqual(daemon.observations,1)
        self.assertEqual(sum(args[0]=='rm' for args in daemon.calls),1)

    def test_interrupt_preserved_and_only_api_removed(self):
        daemon=self.daemon('start_interrupt')
        with self.assertRaises(KeyboardInterrupt): self.run_fake(daemon)
        self.assertTrue(daemon.removed)
        self.assertEqual(daemon.observations,2)

    def test_missing_cid_never_guesses_target_or_deletes_pg(self):
        daemon=self.daemon('missing_cid')
        with self.assertRaises(Exception): self.run_fake(daemon)
        self.assertFalse(any(args[0]=='rm' for args in daemon.calls))
        self.assertEqual(daemon.observations,1)

    def test_changed_final_counts_fail_after_removal(self):
        daemon=self.daemon('post_change')
        with self.assertRaisesRegex(m.Blocked,'POST_API_DATABASE_UNCONFIRMED'): self.run_fake(daemon)
        self.assertTrue(daemon.removed)

    def test_api_cid_cannot_drift_after_initial_record(self):
        api=m._APIContainer(self.root,IMAGE,COMMIT,{},PG_CID,NETNS)
        api.cidfile.write_text(API_CID+'\n'); api.record()
        api.cid='e'*64
        with self.assertRaises(m.Blocked): api.inspect(lambda *a,**k:(0,json.dumps([snapshot(api)]).encode()),state='running')

    def test_first_cleanup_interrupt_is_preserved_with_uncertain_note(self):
        daemon=self.daemon('cleanup_interrupt')
        with self.assertRaisesRegex(KeyboardInterrupt,'cleanup interruption') as caught:
            self.run_fake(daemon)
        self.assertIn('API_CLEANUP_UNCONFIRMED',caught.exception.__notes__)
        self.assertEqual(daemon.observations,1)
        self.assertEqual(sum(args[0]=='rm' for args in daemon.calls),1)

    def test_first_post_observation_interrupt_is_preserved_with_note(self):
        daemon=self.daemon('post_interrupt')
        with self.assertRaisesRegex(KeyboardInterrupt,'post interruption') as caught:
            self.run_fake(daemon)
        self.assertIn('POST_API_DATABASE_UNCONFIRMED',caught.exception.__notes__)
        self.assertTrue(daemon.removed)

    def test_prior_work_failure_retained_when_cleanup_is_interrupted(self):
        daemon=self.daemon('probe_cleanup_interrupt')
        with self.assertRaisesRegex(m.Blocked,'API_PROBE_REJECTED') as caught:
            self.run_fake(daemon)
        self.assertIn('API_CLEANUP_UNCONFIRMED',caught.exception.__notes__)
        self.assertEqual(daemon.observations,1)

    def test_prior_work_failure_retained_when_post_observation_is_interrupted(self):
        daemon=self.daemon('probe_post_interrupt')
        with self.assertRaisesRegex(m.Blocked,'API_PROBE_REJECTED') as caught:
            self.run_fake(daemon)
        self.assertIn('POST_API_DATABASE_UNCONFIRMED',caught.exception.__notes__)
        self.assertTrue(daemon.removed)


class ProgramTests(unittest.TestCase):
    def setUp(self): self.assertIsNotNone(m)

    def process(self, *, endpoint='0100007F:1F40', netns=NETNS, devices=None, uid='65532', command=None):
        command=['/usr/local/bin/python',*m.UVICORN_ARGS] if command is None else command
        status='\n'.join([f'Uid: {uid} {uid} {uid} {uid}','Gid: 65532 65532 65532 65532',
            *[key+': 0000000000000000' for key in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb')],
            'NoNewPrivs: 1','Seccomp: 2'])
        values={'/proc/1/cmdline':b'\0'.join(v.encode() for v in command)+b'\0',
                '/proc/1/status':status.encode(),'/proc/net/tcp6':b'header\n',
                '/proc/net/tcp':('header\n0: 0100007F:1538 00000000:0000 0A\n1: '+endpoint+' 00000000:0000 0A\n').encode()}
        output=io.StringIO()
        with patch('builtins.open',side_effect=lambda path,*a,**k:io.BytesIO(values[path])), \
             patch('os.readlink',return_value=netns),patch('os.listdir',return_value=['lo'] if devices is None else devices), \
             patch.object(sys,'argv',['probe',NETNS]),patch('sys.stdout',output):
            exec(compile(m.PROCESS_PROGRAM,'<mock-process>','exec'),{})
        return json.loads(output.getvalue())

    def test_actual_process_program_accepts_only_expected_shared_loopback(self):
        self.assertEqual(self.process(),m.PROCESS_RECEIPT)
        for kwargs in ({'endpoint':'00000000:1F40'},{'endpoint':'0100007F:1538'},
                       {'netns':'net:[124]'},{'devices':['lo','eth0']},{'uid':'0'},
                       {'command':['/bin/sh']}):
            with self.subTest(kwargs=kwargs),self.assertRaises(SystemExit) as caught: self.process(**kwargs)
            self.assertEqual(caught.exception.code,2)

    def http(self,name,*,payload=None,status=None,headers=None):
        method,path,expected_status,expected,private=m.CASES[name]
        body=json.dumps(expected).encode() if payload is None else payload
        fields={'content-type':'application/json','content-length':str(len(body))}
        if private: fields.update({'cache-control':'private, no-store','pragma':'no-cache',
                                   'vary':'Authorization','www-authenticate':'Bearer'})
        if headers: fields.update(headers)
        class Response:
            status=expected_status
            def getheaders(self): return list(fields.items())
            def read(self,n): return body[:n]
        response=Response()
        if status is not None: response.status=status
        class Connection:
            def request(self,*args,**kwargs): self.requested=(args,kwargs)
            def getresponse(self): return response
            def close(self): pass
        connection=Connection(); output=io.StringIO()
        with patch('http.client.HTTPConnection',return_value=connection) as constructor, \
             patch.object(sys,'argv',['probe',name]),patch('sys.stdout',output):
            exec(compile(m.PROBE_PROGRAM,'<mock-http>','exec'),{})
        constructor.assert_called_once_with('127.0.0.1',8000,timeout=2)
        self.assertEqual(connection.requested[0],(method,path))
        return json.loads(output.getvalue())

    def test_actual_http_program_checks_all_exact_cases(self):
        for name in m.CASES:
            with self.subTest(name=name): self.assertEqual(self.http(name),{'case':name,'passed':True})

    def test_actual_http_program_rejects_framing_redirect_body_and_status(self):
        for kwargs in ({'status':503},{'payload':b'{"status":"ready","status":"ready"}'},
            {'payload':b'{}'},{'payload':b'x'*4097},{'headers':{'location':'http://external'}},
            {'headers':{'transfer-encoding':'chunked'}},{'headers':{'content-length':'000'}},
            {'headers':{'content-type':'text/plain'}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(SystemExit) as caught: self.http('ready',**kwargs)
            self.assertEqual(caught.exception.code,2)


if __name__=='__main__': unittest.main()
