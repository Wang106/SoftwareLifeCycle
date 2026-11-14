"""Synthetic-only orchestration contracts; never invoke Docker, DB or network."""
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
SPEC = importlib.util.find_spec('offline_migration_database_rehearsal')
if SPEC:
    import offline_migration_database_rehearsal as m
else:
    m = None
COMMIT = 'a' * 40
IMAGE = 'sha256:' + 'b' * 64
CID = 'c' * 64

class JointTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(m, 'joint migration image/database coordinator missing')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_cli_is_explicit_and_rejects_arbitrary_targets(self):
        for args in ([], ['--run'], ['--expected-commit', COMMIT],
                     ['--run', '--expected-commit', COMMIT, '--database-url', 'PRIVATE']):
            with patch.object(m, 'run', side_effect=AssertionError('must not run')), patch('sys.stderr', new_callable=io.StringIO) as err:
                self.assertEqual(m.main(args), 2)
                self.assertNotIn('PRIVATE', err.getvalue())

    def test_pg_create_has_no_external_network_and_only_tmpfs(self):
        c = m.OwnedContainer(self.root, 'pg', m.PG_ID, COMMIT, {})
        args = c.create_args()
        self.assertIn('--network=none', args)
        self.assertIn('--read-only', args)
        self.assertIn('--memory-swap=1g', args)
        self.assertIn('listen_addresses=127.0.0.1', args)
        self.assertNotIn('--publish', args)
        self.assertNotIn('--volume', args)
        self.assertEqual(c.env['POSTGRES_INITDB_ARGS'], '--auth-local=trust --auth-host=trust')

    def test_migration_joins_only_owned_full_cid(self):
        c = m.OwnedContainer(self.root, 'migration', IMAGE, COMMIT, {'PATH':'/usr/bin'}, pg_cid=CID, netns='net:[123]')
        args = c.create_args()
        self.assertIn('--network=container:' + CID, args)
        for word in ('--publish', '--expose', '--dns', '--hostname', '--add-host'):
            self.assertFalse(any(a.startswith(word) for a in args))
        self.assertIn('127.0.0.1:5432/slc_migration', c.env['DATABASE_URL'])
        for bad in ('name', 'c'*12, 'c'*63, 'c'*65):
            with self.assertRaises(m.Blocked): m.OwnedContainer(self.root, 'migration', IMAGE, COMMIT, {}, pg_cid=bad, netns='net:[123]')

    def test_observation_is_exact_and_not_acceptance(self):
        m.validate_observation(copy.deepcopy(m.EXPECTED_OBSERVATION))
        for key in m.EXPECTED_OBSERVATION:
            changed = copy.deepcopy(m.EXPECTED_OBSERVATION); changed[key] = None
            with self.subTest(key=key), self.assertRaises(m.Blocked): m.validate_observation(changed)
        with self.assertRaises(m.Blocked): m.validate_observation(m.EXPECTED_OBSERVATION | {'extra':0})

    def test_network_identity_only_lo_and_exact_inode(self):
        self.assertEqual(m.network_identity(b'net:[123]\n'), 'net:[123]')
        for raw in (b'net:[123]\neth0\n', b'PRIVATE', b'net:[0]\n', b'net:[123]\n\n'):
            with self.assertRaises(m.Blocked): m.network_identity(raw)
        self.assertIn("set(os.listdir('/sys/class/net')) == {'lo'}", m.MIGRATE)
        self.assertIn("os.readlink('/proc/self/ns/net') == sys.argv[1]", m.MIGRATE)

    def test_runtime_is_original_chain_no_shortcuts(self):
        self.assertIn("command.upgrade(Config('/app/alembic.ini'), '0030_private_upload_sessions')", m.MIGRATE)
        for forbidden in ('command.stamp', 'create_all', 'command.downgrade', 'seed_demo'):
            self.assertNotIn(forbidden, m.MIGRATE)
        self.assertIn("sys.path.insert(0, '/app')", m.MIGRATE)

    def test_missing_shared_budget_rejects_before_build(self):
        with patch.dict('os.environ', {}, clear=True), patch.object(m.builder, 'run', side_effect=AssertionError('must not build')):
            with self.assertRaises(m.Blocked): m.run(COMMIT)

    def test_source_contract_lists_new_runtime_files(self):
        self.assertIn('scripts/offline_migration_database_rehearsal.py', m.RUNTIME_SOURCES)
        self.assertIn('.github/workflows/offline-migration-database-rehearsal.yml', m.RUNTIME_SOURCES)

    def test_receipt_does_not_claim_offline_or_roles(self):
        receipt = m.receipt(COMMIT, IMAGE, 'd'*64, 'e'*64)
        self.assertEqual(receipt['status'], 'MIGRATION_IMAGE_EMPTY_DATABASE_PASSED_NOT_DEPLOYMENT')
        self.assertFalse(receipt['application_started'])
        self.assertFalse(receipt['readonly_role_verified'])
        self.assertFalse(receipt['complete_schema_verified'])
        self.assertEqual(receipt['joint_containers_removed'], 2)
        self.assertEqual(receipt['preparation_containers_removed'], 2)

    def test_cleanup_attempts_only_once_on_uncertainty(self):
        c = m.OwnedContainer(self.root, 'pg', m.PG_ID, COMMIT, {})
        c.attempted=True; c.cid=CID
        calls=[]
        def child(args, **kw):
            calls.append(args)
            return (1, b'')
        with self.assertRaises(m.Blocked): c.cleanup(child)
        with self.assertRaises(m.Blocked): c.cleanup(child)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('rm', calls[0])

    def test_no_cleanup_without_known_cid(self):
        c = m.OwnedContainer(self.root, 'pg', m.PG_ID, COMMIT, {})
        c.attempted=True
        with self.assertRaises(m.Blocked): c.cleanup(lambda *a, **k: self.fail('unknown target'))

    def test_budget_does_not_refresh_after_build(self):
        with patch.dict('os.environ', {'MIGRATION_REHEARSAL_STARTED_NS':'1000000000'}), patch.object(m.time,'monotonic',return_value=3290), patch.object(m.time,'monotonic_ns',return_value=3290000000000):
            b=m.shared_budget()
            with self.assertRaises(m.Blocked): b.reserve(300)

    def test_workflow_is_manual_and_no_existing_change(self):
        text=(ROOT/'.github/workflows/offline-migration-database-rehearsal.yml').read_text()
        self.assertIn('workflow_dispatch:', text)
        self.assertIn('contents: read',text)
        self.assertIn('timeout-minutes: 60',text)
        self.assertIn('persist-credentials: false',text)
        self.assertNotIn('schedule:',text)
        self.assertNotIn('pull_request:',text)
        self.assertNotIn('upload-artifact',text)

if __name__ == '__main__': unittest.main()

class InspectTests(JointTests):
    def snapshot(self,c,state='created'):
        return {'Id':c.cid,'Image':c.image_id,'Name':'/'+c.name,'Path':c.entrypoint,'Args':c.args,
                'Config':{'Image':c.image_id,'Labels':{m.LABEL:c.token,'org.opencontainers.image.revision':COMMIT},
                          'User':c.user,'WorkingDir':c.workdir,'Entrypoint':[c.entrypoint],'Cmd':c.args,
                          'Healthcheck':{'Test':['NONE']},'Env':[k+'='+v for k,v in c.env.items()],
                          'Volumes':{'/var/lib/postgresql/data':{}} if c.kind=='pg' else None,
                          'ExposedPorts':{'5432/tcp':{}} if c.kind=='pg' else None},
                'HostConfig':{'NetworkMode':c.network,'PublishAllPorts':False,'Privileged':False,'ReadonlyRootfs':True,
                              'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges'],'Tmpfs':c.tmpfs,
                              'LogConfig':{'Type':'none','Config':{}},'RestartPolicy':{'Name':'no','MaximumRetryCount':0},
                              'PidMode':'','IpcMode':'private','CgroupnsMode':'private','Memory':1073741824,
                              'MemorySwap':1073741824,'NanoCpus':1000000000,'PidsLimit':128,'ShmSize':8388608},
                'State':{'Status':state,'Running':state=='running','Paused':False,'Restarting':False,'Dead':False,'OOMKilled':False,'Error':'','ExitCode':0},
                'Mounts':[], 'NetworkSettings':{'Ports':{},'Networks':{'none':{'IPAddress':'','GlobalIPv6Address':'','Gateway':''}} if c.kind=='pg' else {}}}

    def container(self,kind):
        c=m.OwnedContainer(self.root,kind,m.PG_ID if kind=='pg' else IMAGE,COMMIT,{},**({} if kind=='pg' else {'pg_cid':'d'*64,'netns':'net:[123]'}))
        c.cid=CID
        return c

    def test_complete_inspection_accepts_only_owned_kind(self):
        for kind in ('pg','migration'):
            c=self.container(kind); value=self.snapshot(c)
            self.assertEqual(c.inspect(lambda *a,**kw:(0,json.dumps([value]).encode()))['Id'],CID)

    def test_host_limits_and_network_mutations_fail_closed(self):
        for kind in ('pg','migration'):
            c=self.container(kind)
            for key,value in [('NetworkMode','host'),('PublishAllPorts',True),('Privileged',True),('ReadonlyRootfs',False),
                              ('CapDrop',[]),('SecurityOpt',[]),('Tmpfs',{}),('LogConfig',{'Type':'json-file','Config':{}}),
                              ('Memory',0),('MemorySwap',-1),('NanoCpus',0),('PidsLimit',0),('Binds',['/host:/data']),
                              ('ExtraHosts',['bad:127.0.0.1']),('Dns',['1.1.1.1']),('PortBindings',{'5432/tcp':[{'HostPort':'5432'}]}),
                              ('Mounts',[{}]),('Devices',[{}])]:
                with self.subTest(kind=kind,key=key):
                    doc=self.snapshot(c); doc['HostConfig'][key]=value
                    with self.assertRaises(m.Blocked): c.inspect(lambda *a,**kw:(0,json.dumps([doc]).encode()))

    def test_config_identity_state_and_mount_mutations_reject(self):
        c=self.container('migration')
        mutations=[('Id','f'*64),('Image','sha256:'+'f'*64),('Name','/other'),('Path','/bin/sh'),('Args',[]),
                   ('Mounts',[{'Type':'volume','Destination':'/tmp'}])]
        for key,value in mutations:
            doc=self.snapshot(c);doc[key]=value
            with self.subTest(key=key),self.assertRaises(m.Blocked): c.inspect(lambda *a,**kw:(0,json.dumps([doc]).encode()))
        for key,value in [('User','0'),('WorkingDir','/'),('Env',['DATABASE_URL=PRIVATE']),('Volumes',{'/data':{}}),('ExposedPorts',{'80/tcp':{}}),('Labels',{})]:
            doc=self.snapshot(c);doc['Config'][key]=value
            with self.subTest(key=key),self.assertRaises(m.Blocked): c.inspect(lambda *a,**kw:(0,json.dumps([doc]).encode()))
        for key,value in [('ExitCode',1),('OOMKilled',True),('Error','failure'),('Running',True)]:
            doc=self.snapshot(c,'exited');doc['State'][key]=value
            with self.subTest(key=key),self.assertRaises(m.Blocked): c.inspect(lambda *a,**kw:(0,json.dumps([doc]).encode()),state='exited')

    def test_network_attachments_and_addresses_reject(self):
        for kind in ('pg','migration'):
            c=self.container(kind);doc=self.snapshot(c);doc['NetworkSettings']['Networks']['bridge']={}
            with self.assertRaises(m.Blocked):c.inspect(lambda *a,**kw:(0,json.dumps([doc]).encode()))
        c=self.container('pg');doc=self.snapshot(c);doc['NetworkSettings']['Networks']['none']['IPAddress']='172.1.2.3'
        with self.assertRaises(m.Blocked):c.inspect(lambda *a,**kw:(0,json.dumps([doc]).encode()))

    def test_create_partial_failure_retains_cid_and_requires_identity_cleanup(self):
        c=m.OwnedContainer(self.root,'pg',m.PG_ID,COMMIT,{})
        calls=[]
        def child(args,**kwargs):
            calls.append(args)
            if args[0]=='create': c.cidfile.write_text(CID); return 1,b''
            if args[:2]==['container','inspect']: return 0,json.dumps([self.snapshot(c)]).encode()
            if args[0]=='rm': return 0,CID.encode()+b'\n'
            self.fail(args)
        with self.assertRaises(m.Blocked):c.create(child)
        self.assertEqual(c.cid,CID)
        c.cleanup(child);self.assertTrue(c.cleaned)
        self.assertEqual(sum(a[0]=='create' for a in calls),1)
        self.assertEqual(sum(a[0]=='rm' for a in calls),1)
        c.cleanup(child)
        self.assertEqual(sum(a[0]=='rm' for a in calls),1)

    def test_create_missing_cid_never_searches_name(self):
        c=m.OwnedContainer(self.root,'pg',m.PG_ID,COMMIT,{})
        with self.assertRaises((m.Blocked,m.builder.migration.Blocked,OSError)):c.create(lambda *a,**k:(1,b''))
        self.assertIsNone(c.cid)
        with self.assertRaises(m.Blocked):c.cleanup(lambda *a,**k:self.fail('must not resolve by name'))

class OrchestrationTests(unittest.TestCase):
    def fixture(self,fail=None):
        self.calls=[];self.states={};self.objects={}
        self.created=[];self.real=m.OwnedContainer
        def factory(*a,**kw):
            c=self.real(*a,**kw);self.objects[c.kind]=c;return c
        self.factory=factory
        def command(args,**kw):
            args=args[2:];self.calls.append(args)
            if args[0]=='pull':return 0,b''
            if args[:2]==['image','inspect']:
                if args[2]==m.PG_IMAGE:
                    return 0,json.dumps([{'Id':m.PG_ID,'Os':'linux','Architecture':'amd64','RepoDigests':[m.PG_IMAGE],
                    'Config':{'Entrypoint':['docker-entrypoint.sh'],'Cmd':['postgres'],'Env':['PGDATA=/var/lib/postgresql/data'],'OnBuild':[]}}]).encode()
                return 0,json.dumps([{}]).encode()
            if args[0]=='create':
                kind='migration' if '--network=container:'+CID in args else 'pg'
                c=self.objects[kind];self.created.append(kind)
                c.cidfile.write_text(CID if kind=='pg' else 'd'*64)
                self.states[kind]='created';return 0,c.cidfile.read_bytes()+b'\n'
            kind=next(k for k,c in self.objects.items() if c.cid and c.cid in args)
            c=self.objects[kind]
            if args[:2]==['container','inspect']:
                return 0,json.dumps([InspectTests.snapshot(self,c,self.states[kind])]).encode()
            if args[0]=='start':
                self.states[kind]='running' if kind=='pg' else 'exited'
                if kind=='migration' and fail=='migration':return 1,b''
                return 0,(c.cid.encode()+b'\n' if kind=='pg' else b'MIGRATION_COMMAND_COMPLETED\n')
            if args[0]=='exec':
                if args[-1]==m.NETWORK_PROBE:return 0,b'net:[123]\n'
                if args[-1]==m.EMPTY_SQL:return 0,json.dumps({'version':160015,'relations':0,'functions':0}).encode()
                if args[-1]==m.OBSERVE_SQL:return 0,json.dumps(m.EXPECTED_OBSERVATION if fail!='observation' else {}).encode()
                self.fail(args)
            if args[0]=='rm':
                if kind=='migration' and fail=='cleanup':return 1,b''
                return 0,c.cid.encode()+b'\n'
            self.fail(args)
        self.command=command

    def run_fixture(self,fail=None):
        self.fixture(fail)
        prepared={'status':m.builder.SUCCESS,'source_commit':COMMIT,'database_connected':False,'migrations_executed':False,
                  'containers_removed':2,'image_id':IMAGE,'context_manifest_sha256':'e'*64,'build_context_sha256':'f'*64}
        with tempfile.TemporaryDirectory() as root,patch.object(m.tempfile,'mkdtemp',return_value=root), \
             patch.object(m,'source_binding'),patch.object(m.builder,'run',return_value=prepared), \
             patch.object(m.builder,'host',return_value=(['docker','--host=unix:///var/run/docker.sock'],{})), \
             patch.object(m.builder,'verify_image',return_value={'PATH':'/usr/bin'}), \
             patch.object(m.builder,'command',side_effect=self.command),patch.object(m,'OwnedContainer',side_effect=self.factory), \
             patch.dict('os.environ',{'MIGRATION_REHEARSAL_STARTED_NS':str(m.time.monotonic_ns())}):
            return m.run(COMMIT)

    def test_full_mock_path_and_reverse_cleanup(self):
        r=self.run_fixture()
        self.assertEqual(r['joint_containers_removed'],2)
        self.assertEqual(self.created,['pg','migration'])
        self.assertEqual([a[-1] for a in self.calls if a[0]=='rm'],['d'*64,CID])

    def test_migration_and_observation_failure_still_clean_both(self):
        for failure in ('migration','observation'):
            with self.subTest(failure=failure),self.assertRaises(m.Blocked):self.run_fixture(failure)
            self.assertEqual([a[-1] for a in self.calls if a[0]=='rm'],['d'*64,CID])

    def test_uncertain_migration_cleanup_does_not_skip_pg_cleanup(self):
        with self.assertRaises(m.Blocked):self.run_fixture('cleanup')
        self.assertEqual([a[-1] for a in self.calls if a[0]=='rm'],['d'*64,CID])
        self.assertFalse(self.objects['migration'].cleaned)
        self.assertTrue(self.objects['pg'].cleaned)
