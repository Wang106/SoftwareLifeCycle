#!/usr/bin/env python3
"""Explicit image-to-owned-empty-PG rehearsal; import/help never run anything.

Actual --run needs separate approval for acquisition, isolated trust and DDL.
CLI remains migration-only. Internal include_api needs separately approved runtime;
no external target option, role grants, retry, export or company acceptance.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
import time
import uuid

import offline_migration_image_rehearsal as builder

Blocked = builder.Blocked
require = builder.require
exact = builder.exact
ROOT = Path(__file__).resolve().parents[1]
HEAD = '0029_changeover_batch_history'
PG_IMAGE = 'postgres@sha256:5983db9a9c6ad225a48a46cfe2e03e6680b1826662befd0465eb05b34cb1c64e'
PG_ID = 'sha256:cadebe7c08430c896edac883fa92f8de2c36e330805e770fbee8a7eae13f144f'
LABEL = 'org.software-lifecycle.migration-database-rehearsal'
RUNTIME_SOURCES = frozenset({'scripts/offline_migration_database_rehearsal.py',
    '.github/workflows/offline-migration-database-rehearsal.yml'})
API_RUNTIME_SOURCES = builder.BUILD_SOURCES | RUNTIME_SOURCES | frozenset({
    'scripts/offline_api_image_preparation.py', 'scripts/offline_migrated_api_probe.py',
    'scripts/offline_api_startup_rehearsal.py', 'scripts/offline_database_rehearsal.py',
    'scripts/offline_database_readiness.py', 'scripts/offline_migrated_api_guard.py',
    'scripts/offline_pg_catalog_evidence.py', 'scripts/offline_pg_guard_contracts.py',
    'scripts/offline_migration_schema_evidence.py', 'deploy/offline/migration-schema-0029.json'})
PG_TMPFS = {
    '/var/lib/postgresql/data':'rw,noexec,nosuid,nodev,size=536870912,uid=999,gid=999,mode=0700',
    '/var/run/postgresql':'rw,noexec,nosuid,nodev,size=16777216,uid=999,gid=999,mode=0770',
    '/tmp':'rw,noexec,nosuid,nodev,size=16777216,uid=999,gid=999,mode=0700'}
PG_ARGS = ['postgres', '-c', 'listen_addresses=127.0.0.1', '-c', 'unix_socket_directories=/var/run/postgresql',
           '-c', 'max_connections=10', '-c', 'shared_buffers=32MB', '-c', 'statement_timeout=5000',
           '-c', 'lock_timeout=1000', '-c', 'idle_in_transaction_session_timeout=15000']
NETWORK_PROBE = 'test "$(cat /proc/1/comm)" = postgres && test "$(ls /sys/class/net)" = lo && readlink /proc/1/ns/net'
MIGRATE = '''import os, sys
assert os.getuid() == os.getgid() == 65532
assert set(os.listdir('/sys/class/net')) == {'lo'}
assert os.readlink('/proc/self/ns/net') == sys.argv[1]
sys.path.insert(0, '/app')
from alembic import command
from alembic.config import Config
command.upgrade(Config('/app/alembic.ini'), '0029_changeover_batch_history')
print('MIGRATION_COMMAND_COMPLETED')
'''
EMPTY_SQL = "SELECT json_build_object('version',current_setting('server_version_num')::int,'relations',(SELECT count(*) FROM pg_catalog.pg_class WHERE relnamespace='public'::regnamespace),'functions',(SELECT count(*) FROM pg_catalog.pg_proc WHERE pronamespace='public'::regnamespace));"
OBSERVE_SQL = """BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT json_build_object(
 'version',current_setting('server_version_num')::int,
 'head',(SELECT version_num FROM public.alembic_version),
 'head_rows',(SELECT count(*) FROM public.alembic_version),
 'version_type',(SELECT format_type(atttypid,atttypmod) FROM pg_catalog.pg_attribute WHERE attrelid='public.alembic_version'::regclass AND attname='version_num'),
 'selected_tables',(SELECT count(*) FROM pg_catalog.pg_class WHERE relnamespace='public'::regnamespace AND relkind='r' AND relname IN ('alembic_version','releases','release_snapshots','changeover_baselines','changeover_corrections','batch_baselines','batch_corrections')),
 'functions',(SELECT count(*) FROM pg_catalog.pg_proc WHERE pronamespace='public'::regnamespace AND proname IN ('reject_changeover_batch_history_mutation','guard_changeover_physical_write','guard_batch_physical_write')),
 'triggers',(SELECT count(*) FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid WHERE c.relnamespace='public'::regnamespace AND NOT t.tgisinternal AND t.tgenabled='O' AND t.tgname IN ('changeover_baselines_append_only','changeover_corrections_append_only','batch_baselines_append_only','batch_corrections_append_only','changeover_physical_write_guard','batch_physical_write_guard')),
 'release_rows',(SELECT count(*) FROM public.releases),
 'snapshot_rows',(SELECT count(*) FROM public.release_snapshots),
 'audit_rows',(SELECT count(*) FROM public.audit_events),
 'deployment_rows',(SELECT count(*) FROM public.deployments));
ROLLBACK;"""
EXPECTED_OBSERVATION = {'version':160015,'head':HEAD,'head_rows':1,'version_type':'character varying(64)',
                        'selected_tables':7,'functions':3,'triggers':6,'release_rows':0,'snapshot_rows':0,
                        'audit_rows':0,'deployment_rows':0}
LIMITATIONS = ('Trusted checkout/local daemon synthetic new database only; not full schema, SELECT-only role, '
               'API, offline transfer, physical host isolation, backup/restore or company acceptance. '
               'Temporary superuser trust is not production authentication. No retained image artifact; '
               'CLI termination cannot prove daemon work stopped; interruption can leave owned resources.')

API_LIMITATIONS = ('Trusted reviewed checkout/local daemon, same-run synthetic new database only; '
    'receipts and hashes are consistency, not provenance authentication or authorization. '
    'Nine guard contracts bracket five HTTP cases while API is alive, not after removal. '
    'Limited readiness/read-path/refusal checks and selected structures/counts, not full schema, '
    'SELECT-only roles, real identity, browser, physical isolation, backup/restore or company acceptance. '
    'Temporary superuser trust is not production authentication. Removal is not graceful shutdown. '
    'CLI termination and host loss can leave resources; no retry, prune or retained image export.')


def shared_budget():
    require('MIGRATION_REHEARSAL_STARTED_NS' in os.environ, 'SHARED_BUDGET_REQUIRED')
    return builder.Budget.from_environment()


def source_binding(commit, *, include_api=False):
    require(type(commit) is str and builder.migration.HEX40.fullmatch(commit), 'SOURCE_REJECTED')
    require(Path(__file__).absolute() == ROOT / 'scripts/offline_migration_database_rehearsal.py')
    with builder.migration.directory(ROOT) as fd:
        for path in sorted(API_RUNTIME_SOURCES if include_api else RUNTIME_SOURCES):
            if include_api and path.startswith('scripts/'):
                module=sys.modules.get(Path(path).stem)
                require(module is not None and Path(module.__file__).absolute()==ROOT/path,
                        'RUNTIME_LOCATION_REJECTED')
            raw = builder.migration.git_read(fd, ['show', commit + ':' + path], builder.migration.MAX_SOURCE_FILE)
            require(raw == builder.migration.safe_read(ROOT / path, builder.migration.MAX_SOURCE_FILE), 'JOINT_SOURCE_MISMATCH')
    # The original builder independently binds its code, recipe and full source tree.


def network_identity(raw):
    require(type(raw) is bytes and re.fullmatch(b'net:\\[[1-9][0-9]{0,19}\\]\\n', raw), 'NETWORK_IDENTITY_REJECTED')
    return raw.decode().strip()


def validate_observation(value):
    require(exact(value, EXPECTED_OBSERVATION), 'DATABASE_OBSERVATION_REJECTED')


def environment(values):
    require(type(values) is list and len(values) <= 24, 'PG_ENV_REJECTED')
    result = {}
    for item in values:
        require(type(item) is str and len(item) <= 2048 and '=' in item, 'PG_ENV_REJECTED')
        key, value = item.split('=',1)
        require(key in {'PATH','LANG','GOSU_VERSION','PG_MAJOR','PG_VERSION','PG_SHA256','PGDATA'}
                and key not in result, 'PG_ENV_REJECTED')
        result[key] = value
    require(result.get('PGDATA') == '/var/lib/postgresql/data', 'PG_ENV_REJECTED')
    return result


class OwnedContainer:
    def __init__(self, root, kind, image_id, commit, baked, *, pg_cid=None, netns=None):
        require(kind in ('pg','migration') and re.fullmatch('sha256:[0-9a-f]{64}', image_id))
        require(builder.migration.HEX40.fullmatch(commit))
        self.root,self.kind,self.image_id,self.commit = Path(root),kind,image_id,commit
        self.token=uuid.uuid4().hex; self.name='slc-joint-'+kind+'-'+self.token
        self.cidfile=self.root/(kind+'.cid'); self.cid=None
        self.attempted=self.cleanup_attempted=self.cleaned=False
        self.pg_cid=pg_cid
        if kind == 'pg':
            require(image_id == PG_ID)
            self.env=dict(baked, POSTGRES_HOST_AUTH_METHOD='trust', POSTGRES_INITDB_ARGS='--auth-local=trust --auth-host=trust', POSTGRES_DB='slc_migration')
            self.entrypoint='docker-entrypoint.sh'; self.args=list(PG_ARGS)
            self.tmpfs=PG_TMPFS; self.network='none'; self.user='999:999'; self.workdir='/'
        else:
            require(type(pg_cid) is str and re.fullmatch('[0-9a-f]{64}',pg_cid), 'PG_CID_REQUIRED')
            require(type(netns) is str and re.fullmatch(r'net:\[[1-9][0-9]{0,19}\]',netns), 'NETWORK_IDENTITY_REJECTED')
            self.env=dict(baked, HOME='/tmp', PYTHONDONTWRITEBYTECODE='1', DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:5432/slc_migration?connect_timeout=5', AUTH_MODE='disabled', READ_ONLY_MODE='false', SEED_ON_STARTUP='false')
            self.entrypoint='/usr/local/bin/python'; self.args=['-I','-B','-c',MIGRATE,netns]
            self.tmpfs=builder.TMPFS; self.network='container:'+pg_cid; self.user='65532:65532'; self.workdir='/app'

    def create_args(self):
        args=['create','--cidfile',str(self.cidfile),'--name',self.name,'--label',LABEL+'='+self.token,
              '--pull=never','--platform=linux/amd64','--network='+self.network,'--log-driver=none','--restart=no',
              '--read-only','--user='+self.user,'--workdir='+self.workdir,'--cap-drop=ALL','--security-opt=no-new-privileges',
              '--pids-limit=128','--memory=1g','--memory-swap=1g','--cpus=1','--shm-size=8m','--ipc=private','--cgroupns=private','--no-healthcheck',
              '--entrypoint',self.entrypoint]
        for key,value in self.tmpfs.items(): args += ['--tmpfs',key+':'+value]
        for key,value in self.env.items(): args += ['--env',key+'='+value]
        return args+[self.image_id,*self.args]

    def record(self):
        raw=builder.migration.safe_read(self.cidfile,65)
        require(re.fullmatch(b'[0-9a-f]{64}\\n?',raw), 'CONTAINER_ID_UNCERTAIN')
        cid=raw.decode().strip()
        require(self.cid in (None,cid),'CONTAINER_ID_UNCERTAIN'); self.cid=cid

    def inspect(self, child, *, state=None):
        require(self.cid is not None,'CONTAINER_ID_UNCERTAIN')
        code,raw=child(['container','inspect',self.cid],timeout=15)
        require(code == 0,'CONTAINER_IDENTITY_UNCERTAIN')
        data=builder.document(raw,array=True)
        require(len(data)==1 and type(data[0]) is dict,'CONTAINER_REJECTED'); d=data[0]
        c,h,s,n=(d.get(k) for k in ('Config','HostConfig','State','NetworkSettings'))
        require(all(type(v) is dict for v in (c,h,s,n)),'CONTAINER_REJECTED')
        require(d.get('Id')==self.cid and d.get('Image')==self.image_id and d.get('Name')=='/'+self.name
                and d.get('Path')==self.entrypoint and exact(d.get('Args'),self.args)
                and c.get('Image')==self.image_id and type(c.get('Labels')) is dict
                and c['Labels'].get(LABEL)==self.token and c.get('User')==self.user and c.get('WorkingDir')==self.workdir
                and exact(c.get('Entrypoint'),[self.entrypoint]) and exact(c.get('Cmd'),self.args)
                and exact(c.get('Healthcheck'),{'Test':['NONE']}),'CONTAINER_REJECTED')
        require(type(c.get('Env')) is list and len(c['Env'])==len(self.env)
                and set(c['Env'])=={k+'='+v for k,v in self.env.items()},'CONTAINER_ENV_REJECTED')
        if self.kind=='pg':
            require(exact(c.get('Volumes'),{'/var/lib/postgresql/data':{}})
                    and exact(c.get('ExposedPorts'),{'5432/tcp':{}}),'PG_MOUNTS_REJECTED')
        else:
            require(c.get('Volumes') in (None,{}) and c.get('ExposedPorts') in (None,{})
                    and c['Labels'].get('org.opencontainers.image.revision')==self.commit,'IMAGE_REJECTED')
        expected={'NetworkMode':self.network,'PublishAllPorts':False,'Privileged':False,'ReadonlyRootfs':True,
                  'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges'],'Tmpfs':self.tmpfs,
                  'LogConfig':{'Type':'none','Config':{}},'RestartPolicy':{'Name':'no','MaximumRetryCount':0},
                  'PidMode':'','IpcMode':'private','CgroupnsMode':'private','Memory':1073741824,'MemorySwap':1073741824,
                  'NanoCpus':1000000000,'PidsLimit':128,'ShmSize':8388608}
        require(all(exact(h.get(k),v) for k,v in expected.items()),'CONTAINER_LIMITS_REJECTED')
        require(h.get('PortBindings') in (None,{}) and all(h.get(k) in (None,[]) for k in
                ('Binds','Mounts','VolumesFrom','CapAdd','Devices','DeviceRequests','DeviceCgroupRules','ExtraHosts','Dns','DnsSearch','DnsOptions')),'CONTAINER_ATTACHMENT_REJECTED')
        mounts=d.get('Mounts')
        require(type(mounts) is list and len(mounts)<=len(self.tmpfs) and all(type(v) is dict and v.get('Type')=='tmpfs' and v.get('Destination') in self.tmpfs for v in mounts),'CONTAINER_MOUNTS_REJECTED')
        require(n.get('Ports') in (None,{}, {'5432/tcp':None}) and type(n.get('Networks')) is dict,'NETWORK_REJECTED')
        if self.kind=='pg':
            require(set(n['Networks'])=={'none'},'NETWORK_REJECTED'); network=n['Networks']['none']
            require(type(network) is dict and all(network.get(k)=='' for k in ('IPAddress','GlobalIPv6Address','Gateway')),'NETWORK_REJECTED')
        else: require(n['Networks']=={},'NETWORK_REJECTED')
        if state is not None:
            require(s.get('Status')==state and s.get('Running') is (state=='running')
                    and all(s.get(k) is False for k in ('Paused','Restarting','Dead','OOMKilled')) and s.get('Error')=='','PROCESS_STATE_REJECTED')
            if state=='exited': require(type(s.get('ExitCode')) is int and s['ExitCode']==0,'PROCESS_EXIT_REJECTED')
        return d

    def create(self, child):
        require(not self.attempted and not os.path.lexists(self.cidfile),'CREATE_COLLISION')
        with (self.root/(self.kind+'-custody.json')).open('x') as handle:
            os.chmod(handle.name,0o600)
            json.dump({'name':self.name,'label':LABEL,'token':self.token,'image_id':self.image_id,'source_commit':self.commit},handle)
            handle.flush(); os.fsync(handle.fileno())
        self.attempted=True
        try: code,raw=child(self.create_args(),timeout=30,limit=1024)
        finally: self.record()
        self.inspect(child)
        require(code==0 and raw.strip()==self.cid.encode(),'CREATE_FAILED')

    def cleanup(self, child):
        if not self.attempted or self.cleaned: return
        require(not self.cleanup_attempted and self.cid is not None,'CLEANUP_UNCERTAIN')
        self.cleanup_attempted=True
        self.inspect(child)
        code,raw=child(['rm','--force',self.cid],timeout=20,limit=1024)
        require(code==0 and raw.strip()==self.cid.encode(),'CLEANUP_UNCERTAIN'); self.cleaned=True


def psql(cid, query):
    require(re.fullmatch('[0-9a-f]{64}',cid),'CONTAINER_ID_UNCERTAIN')
    return ['exec','--user=999:999','--env=PGCONNECT_TIMEOUT=5',cid,'psql','--no-psqlrc','--quiet',
            '--tuples-only','--no-align','--no-password','--set=ON_ERROR_STOP=1','--host=127.0.0.1',
            '--username=postgres','--dbname=slc_migration','--command',query]


def receipt(commit,image,context_digest,build_digest):
    return {'format':'slc-offline-migration-database-rehearsal-v1',
            'status':'MIGRATION_IMAGE_EMPTY_DATABASE_PASSED_NOT_DEPLOYMENT','source_commit':commit,
            'migration_image_id':image,'postgres_image_id':PG_ID,'context_manifest_sha256':context_digest,
            'build_context_sha256':build_digest,'migration_head':HEAD,'observation':dict(EXPECTED_OBSERVATION),
            'preparation_containers_removed':2,'joint_containers_removed':2,'application_started':False,
            'readonly_role_verified':False,'complete_schema_verified':False,'limitations':LIMITATIONS}


def _api_preparation_receipt(value, commit, migration_image, preparation):
    require(type(value) is dict, 'API_BUILD_RECEIPT_REJECTED')
    image=value.get('image_id')
    require(type(image) is str and re.fullmatch('sha256:[0-9a-f]{64}',image)
            and image not in (migration_image,PG_ID), 'API_BUILD_RECEIPT_REJECTED')
    for key in ('context_manifest_sha256','build_context_sha256'):
        require(type(value.get(key)) is str and builder.migration.HEX64.fullmatch(value[key]),
                'API_BUILD_RECEIPT_REJECTED')
    require(exact(value,preparation.receipt(commit,image,value['context_manifest_sha256'],
                                          value['build_context_sha256'])), 'API_BUILD_RECEIPT_REJECTED')
    return image


def _api_probe_receipt(value, commit, image, probe):
    require(exact(value,{'format':'slc-migrated-api-probe-v2',
        'status':'LIMITED_MIGRATED_API_PASSED_NOT_DEPLOYMENT','source_commit':commit,
        'api_image_id':image,'cases_passed':5,'database_ready':True,
        'api_container_removed':True,'postgres_removed_by_helper':False,
        'observation_before':EXPECTED_OBSERVATION,'observation_after':EXPECTED_OBSERVATION,
        'guard_coverage':'api-alive-five-http-cases-three-functions-six-triggers',
        'guard_checks_before':probe.guard.expected_checks(),'guard_checks_after':probe.guard.expected_checks(),
        'guard_transactions_closed':2,
        'readonly_role_verified':False,'complete_schema_verified':False,
        'provenance_authenticated':False,'limitations':probe.LIMITATIONS}), 'API_PROBE_RECEIPT_REJECTED')


def run(commit, *, include_api=False):
    """Internal opt-in only; CLI/workflow cannot enable API execution.

    A trusted caller must obtain separate actual-runtime approval and install
    SIGTERM handling (as main does) before calling. No receipt grants authority.
    """
    require(type(include_api) is bool, 'ARGUMENTS_REJECTED')
    budget=shared_budget()
    original_deadline=budget.deadline
    if include_api:
        # Lazy imports: probe imports this module for the live owned PG type.
        import offline_api_image_preparation as preparation
        import offline_migrated_api_probe as probe
        source_binding(commit,include_api=True)
        guard_program=probe.guard.prepare(commit,budget)
    else:
        source_binding(commit)
    root=Path(tempfile.mkdtemp(prefix='slc-migration-database-'))
    build_root=root/'build'; build_root.mkdir(mode=0o700)
    prepared=builder.run(commit,root=build_root)
    require(type(prepared) is dict and prepared.get('status')==builder.SUCCESS and prepared.get('source_commit')==commit
            and prepared.get('database_connected') is False and prepared.get('migrations_executed') is False
            and type(prepared.get('containers_removed')) is int and prepared['containers_removed']==2,'BUILD_RECEIPT_REJECTED')
    image=prepared.get('image_id'); require(type(image) is str and re.fullmatch('sha256:[0-9a-f]{64}',image),'BUILD_RECEIPT_REJECTED')
    for key in ('context_manifest_sha256','build_context_sha256'):
        require(type(prepared.get(key)) is str and builder.migration.HEX64.fullmatch(prepared[key]),'BUILD_RECEIPT_REJECTED')
    # Preserve original start, never grant a second 55-minute window. Insufficient
    # time fails before any PG container creation; no attempt to resume later.
    api_prepared=None; api_image=None
    if include_api:
        api_prepared=preparation.prepare(commit,root=root/'api-build',budget=budget)
        require(budget.deadline==original_deadline,'BUDGET_CHANGED')
        api_image=_api_preparation_receipt(api_prepared,commit,image,preparation)
    # API preparation retains its existing 630-second reserve; this stronger
    # downstream floor can reject after preparation, always before PG creation.
    budget.reserve(1330 if include_api else 1000)
    runtime=root/'joint'; runtime.mkdir(mode=0o700)
    prefix,env=builder.host(runtime,budget)
    def command(args,*,timeout=30,limit=65536,reserve=100):
        if include_api: require(budget.deadline==original_deadline,'BUDGET_CHANGED')
        return builder.command(prefix+args,env=env,timeout=budget.allowance(timeout,reserve),limit=limit)
    def cleanup_command(args,*,timeout=20,limit=65536):
        # Cleanup never reads the mutable work Budget. The helper still owns
        # exact CID verification and a shorter phase deadline/reserve.
        remaining=original_deadline-time.monotonic()-30
        require(remaining>0,'CLEANUP_UNCERTAIN')
        return builder.command(prefix+args,env=env,timeout=min(timeout,remaining),limit=limit)
    code,_=command(['pull','--platform=linux/amd64',PG_IMAGE],timeout=600,reserve=730 if include_api else 400)
    require(code==0,'PG_PULL_FAILED_OR_UNCERTAIN')
    code,raw=command(['image','inspect',PG_IMAGE]); require(code==0,'PG_IMAGE_REJECTED')
    images=builder.document(raw,array=True); require(len(images)==1 and type(images[0]) is dict,'PG_IMAGE_REJECTED')
    pg_image=images[0]; cfg=pg_image.get('Config')
    require(pg_image.get('Id')==PG_ID and pg_image.get('Os')=='linux' and pg_image.get('Architecture')=='amd64'
            and pg_image.get('Variant') in (None,'') and PG_IMAGE in pg_image.get('RepoDigests',[])
            and type(cfg) is dict and exact(cfg.get('Entrypoint'),['docker-entrypoint.sh'])
            and exact(cfg.get('Cmd'),['postgres']) and cfg.get('OnBuild') in (None,[]),'PG_IMAGE_REJECTED')
    pg_env=environment(cfg.get('Env'))
    code,raw=command(['image','inspect',image]); require(code==0,'IMAGE_REJECTED')
    migration_env=builder.verify_image(builder.document(raw,array=True),image,commit)
    budget.reserve(730 if include_api else 400)
    joint_deadline=min(time.monotonic()+300,budget.deadline-(460 if include_api else 130))
    def work(args,*,timeout=30,limit=65536):
        remaining=joint_deadline-time.monotonic(); require(remaining>0,'JOINT_TIMEOUT')
        return command(args,timeout=min(timeout,remaining),limit=limit,reserve=430 if include_api else 100)
    pg=OwnedContainer(runtime,'pg',PG_ID,commit,pg_env); migration=None
    original=None; cleanup_failed=[]; api_result=None
    try:
        pg.create(work)
        code,raw=work(['start',pg.cid],timeout=30,limit=1024)
        require(code==0 and raw.strip()==pg.cid.encode(),'PG_START_FAILED')
        ready_deadline=min(joint_deadline,time.monotonic()+90)
        netns=None
        while time.monotonic()<ready_deadline:
            pg.inspect(work,state='running')
            code,raw=work(['exec','--user=999:999',pg.cid,'/bin/sh','-c',NETWORK_PROBE],timeout=5,limit=128)
            if code==0:
                candidate=network_identity(raw)
                code,raw=work(psql(pg.cid,EMPTY_SQL),timeout=10)
                if code==0:
                    require(exact(builder.document(raw),{'version':160015,'relations':0,'functions':0}),'EMPTY_DATABASE_REJECTED')
                    netns=candidate; break
            time.sleep(.2)
        require(netns is not None,'PG_NOT_READY')
        pg.inspect(work,state='running')
        code,raw=work(['exec','--user=999:999',pg.cid,'/bin/sh','-c',NETWORK_PROBE],timeout=5,limit=128)
        require(code==0 and network_identity(raw)==netns,'NETWORK_CHANGED')
        migration=OwnedContainer(runtime,'migration',image,commit,migration_env,pg_cid=pg.cid,netns=netns)
        migration.create(work)
        code,raw=work(['start','--attach',migration.cid],timeout=180)
        migration.inspect(work,state='exited')
        require(code==0 and raw==b'MIGRATION_COMMAND_COMPLETED\n','MIGRATION_FAILED')
        pg.inspect(work,state='running')
        code,raw=work(psql(pg.cid,OBSERVE_SQL),timeout=15)
        require(code==0,'DATABASE_OBSERVATION_FAILED'); validate_observation(builder.document(raw))
        if include_api:
            require(budget.deadline==original_deadline,'BUDGET_CHANGED')
            # Do not pass work: its migration-stage deadline has now served its
            # purpose. The probe owns API removal; this finally retains PG.
            api_result=probe.run_probe(pg=pg,netns=netns,image_id=api_image,
                                      source_commit=commit,command=command,budget=budget,guard_program=guard_program,
                                      cleanup_command=cleanup_command)
            require(budget.deadline==original_deadline,'BUDGET_CHANGED')
            _api_probe_receipt(api_result,commit,api_image,probe)
    except BaseException as exc:
        original=exc
    finally:
        cleanup_deadline=min(time.monotonic()+90,(original_deadline if include_api else budget.deadline)-30)
        def clean(args,*,timeout=20,limit=65536):
            remaining=cleanup_deadline-time.monotonic(); require(remaining>0,'CLEANUP_UNCERTAIN')
            return builder.command(prefix+args,env=env,timeout=min(timeout,remaining),limit=limit)
        for container in (migration,pg):
            if container is not None:
                try: container.cleanup(clean)
                except BaseException as error:
                    cleanup_failed.append(container.kind)
                    if original is None and not isinstance(error,Exception): original=error
    if original is not None:
        if cleanup_failed: original.add_note('JOINT_CLEANUP_UNCONFIRMED')
        raise original
    require(not cleanup_failed and migration is not None and migration.cleaned and pg.cleaned,'CLEANUP_UNCERTAIN')
    budget.reserve(0)
    result=receipt(commit,image,prepared['context_manifest_sha256'],prepared['build_context_sha256'])
    if include_api:
        result.update(format='slc-offline-migration-api-lifecycle-v2',
            status='LIMITED_MIGRATED_API_LIFECYCLE_PASSED_NOT_DEPLOYMENT',
            api_image_id=api_image,api_context_manifest_sha256=api_prepared['context_manifest_sha256'],
            api_build_context_sha256=api_prepared['build_context_sha256'],api_cases_passed=5,
            joint_containers_removed=3,application_started=True,database_ready=True,
            guard_coverage=api_result['guard_coverage'],guard_checks_before=api_result['guard_checks_before'],
            guard_checks_after=api_result['guard_checks_after'],guard_transactions_closed=2,
            api_container_removed=True,provenance_authenticated=False,limitations=API_LIMITATIONS)
    return result


class Parser(argparse.ArgumentParser):
    def error(self,_message): raise Blocked('ARGUMENTS_REJECTED')


def main(argv=None):
    previous=None; attempted=False
    try:
        parser=Parser(description=__doc__)
        parser.add_argument('--run',action='store_true'); parser.add_argument('--expected-commit',required=True)
        args=parser.parse_args(argv)
        require(args.run and builder.migration.HEX40.fullmatch(args.expected_commit),'ARGUMENTS_REJECTED')
        previous=signal.getsignal(signal.SIGTERM); attempted=True
        def interrupted(_sig,_frame): raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM,interrupted)
        result=run(args.expected_commit)
        print(json.dumps(result,sort_keys=True))
        return 0
    except (Exception,KeyboardInterrupt):
        print('MIGRATION_DATABASE_BLOCKED_OR_UNCERTAIN; no automatic retry or deployment acceptance.',file=sys.stderr)
        return 2
    finally:
        if attempted: signal.signal(signal.SIGTERM,previous)


if __name__=='__main__': sys.exit(main())
