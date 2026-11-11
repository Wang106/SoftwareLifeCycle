"""Internal helper for the explicitly opted-in, same-run coordinator.

The caller establishes approval, reviewed checkout/image provenance, original
budget and ownership of a freshly migrated PG before calling. Live objects and
custody/inspect comparisons are consistency checks, not provenance authentication.
No CLI, downloader, daemon selection, migration, role creation or external target.
Import and direct invocation of this file (including --help) perform no work.
"""
import copy
import json
import math
from pathlib import Path
import re
import time

import offline_api_startup_rehearsal as startup
import offline_migration_database_rehearsal as joint
import offline_migrated_api_guard as guard

Blocked = joint.Blocked
require = joint.require
exact = joint.exact
LIMITATIONS = ('Trusted-caller helper; consistency only, not provenance or authorization. '
    'Default read-only PostgreSQL sessions using temporary superuser trust are not a SELECT-only role. '
    'Nine selected guard contracts bracket five HTTP cases while API is alive, not before startup or after removal. '
    'Selected empty catalogs, structures and four row counts only; not full schema, all data, '
    'real identity, browser, physical isolation or company deployment acceptance. '
    'API removal is not graceful application shutdown. Caller still owns PG cleanup. '
    'CLI termination cannot prove daemon work stopped; uncertainty can leave resources.')
ENVIRONMENT = dict(startup.ENVIRONMENT,
    DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:5432/slc_migration?connect_timeout=5',
    PGCONNECT_TIMEOUT='5',
    PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=5000 '
              '-c lock_timeout=1000 -c idle_in_transaction_session_timeout=15000')
UVICORN_ARGS = list(startup.UVICORN_ARGS)
CASES = {
    'ready': ('GET','/health/ready',200,{'status':'ready','version':'0.18.50',
        'database_revision':joint.HEAD},False),
    'application_empty': ('GET','/api/v1/release-catalog/application?limit=1',200,
        {'kind':'application','items':[],'total':0,'limit':1,'offset':0,'next_offset':None},False),
    'audit_empty': ('GET','/api/v1/audit/events?limit=1',200,
        {'items':[],'total':0,'event_type_counts':{},'limit':1,'offset':0,'next_offset':None},False),
    'business_denied': ('POST','/api/v1/deployments',403,{'detail':'read_only_mode'},False),
    'identity_disabled': ('GET','/api/v1/security/me',401,{'detail':'oidc_not_enabled'},True),
}

# The existing HTTP transport has exact bounded framing, duplicate-key rejection,
# no redirects/proxy and a fixed loopback address. Reuse its reviewed body with
# this module's closed set of cases; do not mutate the old no-DB program/contract.
PROBE_PROGRAM = ('import http.client, json, sys\nCASES = json.loads(%r)\n' % json.dumps(CASES)
                 + 'def pairs' + startup.PROBE_PROGRAM.split('def pairs',1)[1])
PROCESS_RECEIPT = {'process':'pid1_uvicorn','loopback_only':True,'nonroot':True,'shared_pg_netns':True}
PROCESS_PROGRAM = '''import json, os, sys
EXPECTED = json.loads(%r)
def read(path):
    with open(path, 'rb') as handle: value=handle.read(65537)
    if len(value)>65536: raise ValueError()
    return value
def main():
    if os.readlink('/proc/self/ns/net') != sys.argv[1]: raise ValueError()
    if os.readlink('/proc/1/ns/net') != sys.argv[1]: raise ValueError()
    if set(os.listdir('/sys/class/net')) != {'lo'}: raise ValueError()
    if read('/proc/1/cmdline').split(b'\\0') != [v.encode() for v in EXPECTED]+[b'']: raise ValueError()
    status=dict(line.split(':',1) for line in read('/proc/1/status').decode().splitlines() if ':' in line)
    for key in ('Uid','Gid'):
        if status[key].split() != ['65532']*4: raise ValueError()
    for key in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'):
        if int(status[key],16) != 0: raise ValueError()
    if status['NoNewPrivs'].strip()!='1' or status['Seccomp'].strip()!='2': raise ValueError()
    listeners=[]
    for path in ('/proc/net/tcp','/proc/net/tcp6'):
        for line in read(path).decode().splitlines()[1:]:
            fields=line.split()
            if len(fields)<4: raise ValueError()
            if fields[3]=='0A': listeners.append((path,fields[1]))
    if sorted(listeners) != [('/proc/net/tcp','0100007F:1538'),('/proc/net/tcp','0100007F:1F40')]: raise ValueError()
    print(json.dumps(%r,sort_keys=True))
try:
    main()
except BaseException:
    sys.exit(2)
''' % (json.dumps(['/usr/local/bin/python',*UVICORN_ARGS]), PROCESS_RECEIPT)


def _identity(container):
    keys=('root','kind','image_id','commit','token','name','cidfile','pg_cid',
          'env','entrypoint','args','tmpfs','network','user','workdir')
    return copy.deepcopy({key:getattr(container,key) for key in keys})


def _pid(document, previous):
    pid=document['State'].get('Pid')
    require(type(pid) is int and pid>0 and previous in (None,pid),'PROCESS_ID_CHANGED')
    return pid


class _PGLease:
    """Borrow a live coordinator object, not a receipt or a security capability."""
    def __init__(self, pg, netns, commit):
        require(type(pg) is joint.OwnedContainer and pg.kind=='pg'
                and pg.image_id==joint.PG_ID and pg.commit==commit,'PG_CUSTODY_REQUIRED')
        require(type(pg.cid) is str and re.fullmatch('[0-9a-f]{64}',pg.cid)
                and type(pg.token) is str and re.fullmatch('[0-9a-f]{32}',pg.token)
                and pg.name=='slc-joint-pg-'+pg.token and pg.cidfile==pg.root/'pg.cid',
                'PG_CUSTODY_REQUIRED')
        require(type(netns) is str and re.fullmatch(r'net:\[[1-9][0-9]{0,19}\]',netns),
                'NETWORK_IDENTITY_REJECTED')
        # Reconstruct the fixed PG policy, rather than letting mutable caller
        # fields redefine what a successful inspect means.
        init={'POSTGRES_HOST_AUTH_METHOD':'trust',
              'POSTGRES_INITDB_ARGS':'--auth-local=trust --auth-host=trust','POSTGRES_DB':'slc_migration'}
        baked=joint.environment([key+'='+value for key,value in pg.env.items() if key not in init])
        require(exact(pg.env,baked|init) and pg.pg_cid is None
                and pg.entrypoint=='docker-entrypoint.sh' and exact(pg.args,joint.PG_ARGS)
                and exact(pg.tmpfs,joint.PG_TMPFS) and pg.network=='none'
                and pg.user=='999:999' and pg.workdir=='/','PG_POLICY_CHANGED')
        self.pg,self.netns,self.cid=pg,netns,pg.cid
        self.identity=_identity(pg)
        self.pid=None
        self.custody={'name':pg.name,'label':joint.LABEL,'token':pg.token,
                      'image_id':joint.PG_ID,'source_commit':commit}
        self.local_check()

    def local_check(self):
        pg=self.pg
        require(pg.attempted is True and pg.cleaned is False and pg.cleanup_attempted is False
                and pg.cid==self.cid and exact(_identity(pg),self.identity),'PG_CUSTODY_CHANGED')
        require(joint.builder.migration.safe_read(pg.cidfile,65) in
                (self.cid.encode(),(self.cid+'\n').encode()),'PG_CUSTODY_CHANGED')
        raw=joint.builder.migration.safe_read(pg.root/'pg-custody.json',4096)
        require(exact(joint.builder.document(raw),self.custody),'PG_CUSTODY_CHANGED')

    def check(self, command):
        self.local_check()
        self.pid=_pid(self.pg.inspect(command,state='running'),self.pid)
        code,raw=command(['exec','--user=999:999',self.cid,'/bin/sh','-c',joint.NETWORK_PROBE],
                         timeout=5,limit=128)
        require(code==0 and joint.network_identity(raw)==self.netns,'NETWORK_CHANGED')
        self.local_check()

    def observe(self, command):
        self.check(command)
        code,raw=command(joint.psql(self.cid,joint.OBSERVE_SQL),timeout=15,limit=4096)
        require(code==0,'DATABASE_OBSERVATION_FAILED')
        observation=joint.builder.document(raw)
        joint.validate_observation(observation)
        return observation


class _APIContainer(joint.OwnedContainer):
    """Reuse fixed container checks/custody/one-shot removal, never PG cleanup."""
    def __init__(self, root, image_id, commit, baked, pg_cid, netns):
        super().__init__(root,'migration',image_id,commit,baked,pg_cid=pg_cid,netns=netns)
        # Complete all specialization before any create or custody-file write.
        self.kind='api'; self.name='slc-migrated-api-'+self.token
        self.cidfile=Path(root)/'api.cid'
        self.env=dict(baked)|ENVIRONMENT
        self.args=list(UVICORN_ARGS)
        self.pid=None
        self._recorded_cid=None
        self._fixed=_identity(self)

    def _check(self):
        require(exact(_identity(self),self._fixed),'API_POLICY_CHANGED')
        require(self.cid is None or self.cid!=self.pg_cid,'API_CID_REJECTED')
        require(self._recorded_cid is None or self.cid==self._recorded_cid,'API_CID_CHANGED')

    def record(self):
        self._check()
        super().record()
        self._check()
        self._recorded_cid=self.cid

    def create(self, command):
        self._check()
        super().create(command)

    def inspect(self, command, *, state=None):
        self._check()
        result=super().inspect(command,state=state)
        if state=='running': self.pid=_pid(result,self.pid)
        return result

    def execute(self, command, program, *args):
        self.inspect(command,state='running')
        return command(['exec','--user=65532:65532',self.cid,
                        '/usr/local/bin/python','-I','-B','-c',program,*args],timeout=8,limit=4096)


def _compare_observations(before, after):
    joint.validate_observation(before)
    joint.validate_observation(after)
    require(exact(before,after),'DATABASE_CHANGED')


def _bounded(command, budget, seconds, reserve):
    original_deadline=budget.deadline
    deadline=min(time.monotonic()+seconds,original_deadline-30-reserve)
    def call(args, *, timeout=15, limit=65536):
        require(budget.deadline==original_deadline,'BUDGET_CHANGED')
        remaining=min(deadline-time.monotonic(),budget.allowance(timeout,reserve))
        require(remaining>0,'API_STAGE_TIMEOUT')
        return command(args,timeout=min(timeout,remaining),limit=limit)
    return call


def run_probe(*, pg, netns, image_id, source_commit, command, budget, guard_program, cleanup_command):
    """Trusted caller only; requires the coordinator's verified guard program.

    command must be that coordinator's bounded, local-daemon adapter (stderr
    suppressed, output capped, no retries). budget is its original 55-minute
    Budget. The caller validates build/source provenance and retains PG cleanup
    in its own finally block, including when this function raises BaseException.
    cleanup_command uses the same daemon but the frozen original deadline, not
    the mutable work Budget; it is used only by this helper's owned cleanup.
    No boolean, label, CID, JSON receipt or this function grants authorization.
    """
    require(type(image_id) is str and re.fullmatch('sha256:[0-9a-f]{64}',image_id)
            and type(source_commit) is str and re.fullmatch('[0-9a-f]{40}',source_commit),
            'ARGUMENTS_REJECTED')
    require(callable(command) and callable(cleanup_command) and type(budget) is joint.builder.Budget
            and type(budget.deadline) in (int,float) and math.isfinite(budget.deadline),
            'TRUSTED_COORDINATOR_REQUIRED')
    require(type(guard_program) is str and 0 < len(guard_program.encode('utf-8')) <= 65536,
            'GUARD_PROGRAM_REJECTED')
    original_deadline=budget.deadline
    budget.reserve(300)
    lease=_PGLease(pg,netns,source_commit)
    def adapter(args,**kwargs):
        require(budget.deadline==original_deadline,'BUDGET_CHANGED')
        return command(args,**kwargs)
    work=_bounded(adapter,budget,120,120)
    before=lease.observe(work)
    code,raw=work(['image','inspect',image_id])
    require(code==0,'IMAGE_IDENTITY_REJECTED')
    baked=startup.verify_image(raw,image_id,source_commit)
    api=_APIContainer(pg.root,image_id,source_commit,baked,lease.cid,netns)
    original=None; cleanup_failed=False; after_failed=False; after=None
    guards_before=None; guards_after=None
    def observe_guards():
        # Private catalog IPC has a separate cap. HTTP framing/limits stay fixed.
        lease.check(work)
        api.inspect(work,state='running')
        code,raw=work(['exec','--user=65532:65532',api.cid,
            '/usr/local/bin/python','-I','-B','-c',guard_program,netns],
            timeout=45,limit=524288)
        require(code==0,'GUARD_COLLECTION_FAILED_OR_UNCERTAIN')
        result=guard.parse_and_check(raw)
        lease.check(work)
        api.inspect(work,state='running')
        return result
    try:
        lease.check(work)
        api.create(work)
        code,raw=work(['start',api.cid],timeout=15,limit=1024)
        require(code==0 and raw.strip()==api.cid.encode(),'API_START_FAILED')
        for _ in range(20):
            code,raw=api.execute(work,PROCESS_PROGRAM,netns)
            if code==0:
                require(exact(startup.document(raw),PROCESS_RECEIPT),'API_PROCESS_REJECTED')
                break
            require(code==2 and raw==b'','API_PROCESS_REJECTED')
            time.sleep(.2)
        else: raise Blocked('API_STARTUP_TIMEOUT')
        lease.check(work)
        guards_before=observe_guards()
        for name in CASES:
            code,raw=api.execute(work,PROBE_PROGRAM,name)
            require(code==0 and exact(startup.document(raw),{'case':name,'passed':True}),'API_PROBE_REJECTED')
        guards_after=observe_guards()
        guard.checked_pair(guards_before,guards_after)
        code,raw=api.execute(work,PROCESS_PROGRAM,netns)
        require(code==0 and exact(startup.document(raw),PROCESS_RECEIPT),'API_PROCESS_REJECTED')
    except BaseException as error:
        original=error
    finally:
        cleanup_deadline=min(time.monotonic()+40,original_deadline-30-80)
        def clean(args,*,timeout=20,limit=65536):
            remaining=cleanup_deadline-time.monotonic()
            require(remaining>0,'API_CLEANUP_UNCONFIRMED')
            return cleanup_command(args,timeout=min(timeout,remaining),limit=limit)
        try: api.cleanup(clean)
        except BaseException as error:
            cleanup_failed=True
            if original is None and not isinstance(error,Exception): original=error
        # Never claim an end-state while the API could still be writing/reading.
        if api.cleaned:
            try:
                require(budget.deadline==original_deadline,'BUDGET_CHANGED')
                post=_bounded(adapter,budget,30,40)
                after=lease.observe(post)
                _compare_observations(before,after)
            except BaseException as error:
                after_failed=True
                if original is None and not isinstance(error,Exception): original=error
    if original is not None:
        if cleanup_failed: original.add_note('API_CLEANUP_UNCONFIRMED')
        if after_failed: original.add_note('POST_API_DATABASE_UNCONFIRMED')
        raise original
    require(not cleanup_failed and api.cleaned,'API_CLEANUP_UNCONFIRMED')
    require(not after_failed and after is not None,'POST_API_DATABASE_UNCONFIRMED')
    return {'format':'slc-migrated-api-probe-v2','status':'LIMITED_MIGRATED_API_PASSED_NOT_DEPLOYMENT',
            'source_commit':source_commit,'api_image_id':image_id,'cases_passed':len(CASES),
            'database_ready':True,'api_container_removed':True,'postgres_removed_by_helper':False,
            'observation_before':before,'observation_after':after,
            'guard_coverage':'api-alive-five-http-cases-three-functions-six-triggers',
            'guard_checks_before':guards_before['checks'],'guard_checks_after':guards_after['checks'],
            'guard_transactions_closed':2,'readonly_role_verified':False,
            'complete_schema_verified':False,'provenance_authenticated':False,'limitations':LIMITATIONS}
