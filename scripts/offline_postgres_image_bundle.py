#!/usr/bin/env python3
"""Default-off, fixed official PostgreSQL local image transfer, not DB acceptance.

Only export --run inspects a trusted local daemon and saves one existing immutable
ID once. No pull/build/load, containers, SQL, uploads or network fetch. Verify is
filesystem-only. Caller trusts audited tool source, external expected hashes and
local UID/daemon. Config hash binds official settings, not application provenance.
"""
import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time

import offline_image_bundle as base

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 'slc-postgres-image-handoff-v1'
EXPORTED = 'POSTGRES_IMAGE_BUNDLE_EXPORTED_NOT_DATABASE_ACCEPTANCE'
VERIFIED = 'POSTGRES_IMAGE_BUNDLE_VERIFIED_NOT_DATABASE_ACCEPTANCE'
# Verified original public OCI manifest/config bytes, not registry compressed layers.
# https://registry-1.docker.io/v2/library/postgres/manifests/sha256:5983db9a9c6ad225a48a46cfe2e03e6680b1826662befd0465eb05b34cb1c64e
REFERENCE = 'postgres@sha256:5983db9a9c6ad225a48a46cfe2e03e6680b1826662befd0465eb05b34cb1c64e'
IMAGE_ID = 'sha256:cadebe7c08430c896edac883fa92f8de2c36e330805e770fbee8a7eae13f144f'
CONFIG_SIZE = 10133
LAYER_COUNT = 14
FILES = frozenset({'postgres.tar','manifest.json','evidence.json'})
SOURCES = frozenset({'offline_postgres_image_bundle','offline_image_bundle','offline_readonly_preflight'})
MAX_BYTES = 2 * 1024**3
MAX_METADATA = 1024**2
FORBIDDEN_ENV = ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH',
                 'DOCKER_API_VERSION','BUILDX_BUILDER','BUILDKIT_HOST')
require = base.require


@contextmanager
def bounded(seconds):
    """SIGALRM budget with final deadline check; not a host hard timeout."""
    require(type(seconds) in (int,float) and 0 < seconds <= 1200)
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0,0.0))
    deadline=time.monotonic()+seconds
    previous=signal.getsignal(signal.SIGALRM);attempted=False
    def expired(_signum,_frame):raise base.BundleError('BUNDLE_IO_FAILED')
    try:
        attempted=True;signal.signal(signal.SIGALRM,expired)
        signal.setitimer(signal.ITIMER_REAL,seconds)
        yield
    finally:
        if attempted:
            try:signal.setitimer(signal.ITIMER_REAL,0)
            finally:signal.signal(signal.SIGALRM,previous)
    require(time.monotonic()<deadline,'BUNDLE_IO_FAILED')


def command(args,env,*,timeout=30,limit=MAX_METADATA,sink=None):
    """Bound all stdout before accumulation; discard stderr and never retry."""
    require(type(limit) is int and 0 < limit <= MAX_BYTES and 0 < timeout <= 600)
    process=subprocess.Popen(args,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
    deadline=time.monotonic()+timeout;output=bytearray();total=0
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout,selectors.EVENT_READ)
            while selector.get_map():
                require(time.monotonic()<deadline,'BUNDLE_IO_FAILED')
                for key,_ in selector.select(min(.1,max(.001,deadline-time.monotonic()))):
                    raw=os.read(key.fileobj.fileno(),min(base.CHUNK,limit+1-total))
                    if not raw:selector.unregister(key.fileobj)
                    else:
                        total+=len(raw);require(total<=limit,'BUNDLE_CAPACITY_REJECTED')
                        if sink is None:output.extend(raw)
                        else:base.write_bytes(sink,raw)
            require(time.monotonic()<deadline,'BUNDLE_IO_FAILED')
            require(process.wait(timeout=max(.001,deadline-time.monotonic()))==0,'BUNDLE_IO_FAILED')
        if sink is not None:
            require(total>0);sink.written()
        return bytes(output)
    finally:
        try:
            if process.returncode is None:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait(timeout=2)
        finally:process.stdout.close()


def source_binding(commit):
    """Read-only git calls bind all runtime modules and embedded fixed metadata."""
    require(base.hexadecimal(commit,40))
    modules={name:(Path(__file__) if name=='offline_postgres_image_bundle'
                   else Path(sys.modules[name].__file__)) for name in SOURCES}
    require(all(path.absolute()==ROOT/'scripts'/(name+'.py') for name,path in modules.items()))
    git=shutil.which('git',path=os.defpath);require(git is not None)
    env={'PATH':os.defpath,'HOME':'/nonexistent','LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1',
         'GIT_CONFIG_GLOBAL':'/dev/null','GIT_OPTIONAL_LOCKS':'0'}
    def read(args,limit=MAX_METADATA):
        return command([git,'--no-replace-objects','-c','core.fsmonitor=false',
                        '-c','core.untrackedCache=false','-c','core.hooksPath=/dev/null',*args],env,limit=limit)
    # Empty status is legitimate, whereas other commands must return bytes.
    status_args=['status','--porcelain','--untracked-files=all']
    with ExitStack() as stack:
        root=base.Directory.open(ROOT,stack)
        require(read(['rev-parse','HEAD'],128).decode().strip()==commit)
        require(read(status_args).strip()==b'')
        names={'scripts/'+name+'.py' for name in SOURCES}
        records=read(['ls-tree','-z',commit,'--',*sorted(names)]).split(b'\0')
        seen=set();scripts=root.child('scripts',stack)
        for record in filter(None,records):
            header,path=record.split(b'\t',1);mode,kind,oid=header.split(b' ');name=path.decode()
            require(name in names and name not in seen and mode==b'100644' and kind==b'blob'
                    and base.hexadecimal(oid.decode(),40))
            file=base.File(scripts,name.split('/')[1],stack)
            require(base.read_bytes(file,MAX_METADATA)==read(['cat-file','blob',oid.decode()]))
            seen.add(name)
        require(seen==names)
        require(read(status_args).strip()==b'');root.check()


def docker_args(*args):
    docker=shutil.which('docker',path=os.defpath);require(docker is not None)
    return [docker,'--host=unix:///var/run/docker.sock',*args]


def inspect_local_image(env):
    value=base.parse_json(command(docker_args('image','inspect',IMAGE_ID),env))
    require(type(value) is list and len(value)==1 and type(value[0]) is dict)
    item=value[0]
    require(base.exact(item.get('Id'),IMAGE_ID) and base.exact(item.get('Os'),'linux')
            and base.exact(item.get('Architecture'),'amd64') and item.get('Variant') in (None,'')
            and type(item.get('RepoDigests')) is list and REFERENCE in item['RepoDigests']
            and all(type(value) is str for value in item['RepoDigests']))


def save_image(file,env):
    command(docker_args('image','save',IMAGE_ID),env,timeout=600,limit=MAX_BYTES,sink=file)


def digest_file(file):
    file.check();os.lseek(file.fd,0,os.SEEK_SET);digest=hashlib.sha256();total=0
    while raw:=os.read(file.fd,base.CHUNK):
        total+=len(raw);require(total<=MAX_BYTES);digest.update(raw)
    require(0<total==file.initial.st_size);file.check();return digest.hexdigest()


def contract():
    return {'repository_digest':REFERENCE,'image_id':IMAGE_ID,'config_size':CONFIG_SIZE,
            'platform':'linux/amd64','layer_count':LAYER_COUNT,
            'manifest_media_type':'application/vnd.oci.image.manifest.v1+json'}


def evidence(commit):
    return {'format':'slc-postgres-image-handoff-evidence-v1','source_commit':commit,
        'checks':{'fixed_original_config':True,'ordered_uncompressed_layers':True,'strict_archive':True},
        'limitations':['Tool source_commit is not PostgreSQL source provenance',
            'No database or application startup, SQL, migration, backup or restore',
            'Official image entrypoint, environment and writable volume are retained',
            'No offline installation, production security or company acceptance',
            'No signature, publisher authentication or hostile same-UID protection']}


def check_item(item):
    require(type(item) is dict and set(item)=={'archive','size','sha256'})
    require(base.exact(item['archive'],'postgres.tar') and type(item['size']) is int
            and 0<item['size']<=MAX_BYTES and base.hexadecimal(item['sha256'],64))


def zero_container_config():
    return {**dict.fromkeys(('Hostname','Domainname','User','Image','WorkingDir'),''),
            **dict.fromkeys(('AttachStdin','AttachStdout','AttachStderr','Tty','OpenStdin','StdinOnce'),False),
            **dict.fromkeys(('Env','Cmd','Volumes','Entrypoint','OnBuild','Labels'),None)}


def legacy_helpers(names,data,config):
    """Moby 28 UTC compatibility metadata, never image/content authority.

    Exact fixed config projection and one full parent chain, with raw blob hashes.
    V1 CreateID hash is not recreated; immutable image/config and diff_ids remain
    the only content identity. Non-UTC/exporter variants fail closed.
    """
    require(len(names)==LAYER_COUNT)
    by_parent={};ids=set();total=0
    for name in names:
        require(re.fullmatch(r'blobs/sha256/[0-9a-f]{64}',name))
        raw=data(name);total+=len(raw);require(len(raw)<=16*1024 and total<=MAX_METADATA)
        require(hashlib.sha256(raw).hexdigest()==name.rsplit('/',1)[1])
        item=base.parse_json(raw)
        require(type(item) is dict and base.hexadecimal(item.get('id'),64))
        parent=item.get('parent','')
        require((parent=='' or base.hexadecimal(parent,64)) and parent not in by_parent and item['id'] not in ids)
        by_parent[parent]=item;ids.add(item['id'])
    parent=''
    for index in range(LAYER_COUNT):
        require(parent in by_parent)
        item=by_parent.pop(parent)
        expected={'id':item['id'],'created':'1970-01-01T00:00:00Z',
                  'container_config':zero_container_config(),'os':'linux'}
        if parent:expected['parent']=parent
        if index==LAYER_COUNT-1:
            expected.update(created=config.get('created'),architecture='amd64',
                            config={**zero_container_config(),**config['config']})
        require(base.exact(item,expected))
        parent=item['id']
    require(not by_parent)


def oci_metadata(data,config,descriptors,regular,needed):
    require(base.exact(base.parse_json(data('oci-layout')),{'imageLayoutVersion':'1.0.0'}))
    index=base.parse_json(data('index.json'))
    require(type(index) is dict and set(index)=={'schemaVersion','mediaType','manifests'}
            and base.exact(index['schemaVersion'],2)
            and base.exact(index['mediaType'],'application/vnd.oci.image.index.v1+json')
            and type(index['manifests']) is list and len(index['manifests'])==1)
    desc=index['manifests'][0]
    require(type(desc) is dict and set(desc)=={'mediaType','digest','size'}
            and base.exact(desc['mediaType'],'application/vnd.oci.image.manifest.v1+json')
            and type(desc['digest']) is str and re.fullmatch(r'sha256:[0-9a-f]{64}',desc['digest'])
            and type(desc['size']) is int and 0<desc['size']<=MAX_METADATA)
    name='blobs/sha256/'+desc['digest'][7:];raw=data(name)
    require(len(raw)==desc['size'] and hashlib.sha256(raw).hexdigest()==desc['digest'][7:])
    require(base.exact(base.parse_json(raw),{'schemaVersion':2,
        'mediaType':'application/vnd.oci.image.manifest.v1+json',
        'config':{'mediaType':'application/vnd.oci.image.config.v1+json','digest':IMAGE_ID,'size':CONFIG_SIZE},
        'layers':descriptors}))
    needed|={'oci-layout','index.json',name}
    helpers=regular-needed
    legacy_helpers(helpers,data,config)
    needed|=helpers


def archive_gate(file,item):
    """Independent PG protocol; never call or weaken the application image gate."""
    check_item(item);file.check();require(file.initial.st_size==item['size'])
    require(digest_file(file)==item['sha256'])
    path=base.PinnedArchive(file)
    base.bounded_outer_scan(path,item['size']);file.check()
    with tarfile.open(path,mode='r:') as archive:
        members={}
        for member in archive:
            name=member.name
            require(name and not name.startswith('/') and '\\' not in name
                    and all(part not in ('','.','..') for part in name.split('/'))
                    and name not in members and (member.isfile() or member.isdir()))
            require(not member.isdir() or member.size==0)
            members[name]=member
        def data(name):
            require(type(name) is str and name in members and members[name].isfile()
                    and 0<members[name].size<=MAX_METADATA)
            with archive.extractfile(members[name]) as stream:return stream.read()
        record=base.parse_json(data('manifest.json'))
        require(type(record) is list and len(record)==1 and type(record[0]) is dict)
        record=record[0];fields={'Config','RepoTags','Layers'}
        require(set(record) in (fields,fields|{'LayerSources'}))
        require(record['RepoTags'] is None or base.exact(record['RepoTags'],[]))
        sources='LayerSources' in record
        config_name=('blobs/sha256/'+IMAGE_ID[7:]) if sources else IMAGE_ID[7:]+'.json'
        require(base.exact(record['Config'],config_name))
        raw=data(config_name)
        require(len(raw)==CONFIG_SIZE and 'sha256:'+hashlib.sha256(raw).hexdigest()==IMAGE_ID)
        config=base.parse_json(raw)
        require(type(config) is dict and base.exact(config.get('os'),'linux')
                and base.exact(config.get('architecture'),'amd64') and config.get('variant') in (None,'')
                and type(config.get('config')) is dict)
        roots=config.get('rootfs')
        require(type(roots) is dict and set(roots)=={'type','diff_ids'} and base.exact(roots['type'],'layers'))
        ids=roots['diff_ids'];layers=record['Layers']
        require(type(ids) is list and len(ids)==LAYER_COUNT and all(type(x) is str
                and re.fullmatch(r'sha256:[0-9a-f]{64}',x) for x in ids) and len(set(ids))==len(ids)
                and type(layers) is list and len(layers)==len(ids) and all(type(x) is str for x in layers)
                and len(set(layers))==len(layers))
        if sources:require(type(record['LayerSources']) is dict and set(record['LayerSources'])==set(ids))
        needed={'manifest.json',config_name,*layers};descriptors=[]
        budget=base.preflight.LayerTarBudget(base.preflight.MAX_IMAGE_TAR_HEADERS,base.preflight.MAX_IMAGE_TAR_METADATA)
        for name,diff_id in zip(layers,ids):
            require(name=='blobs/sha256/'+diff_id[7:] if sources else re.fullmatch(r'[0-9a-f]{64}/layer.tar',name))
            require(name in members and members[name].isfile())
            descriptor={'mediaType':'application/vnd.oci.image.layer.v1.tar','digest':diff_id,'size':members[name].size}
            descriptors.append(descriptor)
            if sources:require(base.exact(record['LayerSources'][diff_id],descriptor))
            with archive.extractfile(members[name]) as stream:
                require('sha256:'+base.preflight.digest(stream)==diff_id)
            with archive.extractfile(members[name]) as stream:
                base.preflight.layer_tar_format(stream,members[name].size,budget)
        regular={name for name,member in members.items() if member.isfile()}
        if {'index.json','oci-layout'} & regular:
            require(sources and {'index.json','oci-layout'}<=regular)
            oci_metadata(data,config,descriptors,regular,needed)
        require(regular==needed)
        ancestors=set()
        for name in needed:
            parts=name.split('/')
            ancestors.update('/'.join(parts[:i]) for i in range(1,len(parts)))
        require(all(name in ancestors for name,member in members.items() if member.isdir()))
    file.check()


def verify_files(directory,files,commit,digest,completed):
    names=FILES|({'COMPLETE'} if completed else set());directory.names(names)
    raw=base.read_bytes(files['manifest.json'],base.MAX_JSON_BYTES)
    require(hashlib.sha256(raw).hexdigest()==digest)
    manifest=base.parse_json(raw)
    require(type(manifest) is dict and set(manifest)=={'format','source_commit','contract','image','evidence_sha256'})
    require(base.exact(manifest['format'],FORMAT) and base.exact(manifest['source_commit'],commit)
            and base.exact(manifest['contract'],contract()) and base.hexadecimal(manifest['evidence_sha256'],64))
    check_item(manifest['image'])
    raw=base.read_bytes(files['evidence.json'],base.MAX_JSON_BYTES)
    require(hashlib.sha256(raw).hexdigest()==manifest['evidence_sha256'] and base.exact(base.parse_json(raw),evidence(commit)))
    archive_gate(files['postgres.tar'],manifest['image'])
    for file in files.values():file.check()
    directory.names(names)


def verify_bundle(directory,*,expected_commit,expected_manifest_sha256):
    try:
        require(base.hexadecimal(expected_commit,40) and base.hexadecimal(expected_manifest_sha256,64))
        with bounded(600),ExitStack() as stack:
            root=base.Directory.open(directory,stack);root.names(FILES|{'COMPLETE'})
            marker=base.File(root,'COMPLETE',stack);require(marker.initial.st_size==0)
            files={name:base.File(root,name,stack) for name in sorted(FILES)}
            verify_files(root,files,expected_commit,expected_manifest_sha256,True)
            marker.check();root.names(FILES|{'COMPLETE'})
        return {'status':VERIFIED,'source_commit':expected_commit,'manifest_sha256':expected_manifest_sha256}
    except (Exception,KeyboardInterrupt,SystemExit):raise base.BundleError('BUNDLE_IO_FAILED') from None


def _run(commit,destination,state):
    require(base.hexadecimal(commit,40));base.check_destination(destination)
    require(not any(name in os.environ for name in FORBIDDEN_ENV))
    source_binding(commit)
    parts=base.path_parts(destination)
    with ExitStack() as stack:
        parent=base.Directory.open('/'+'/'.join(parts[:-1]),stack)
        space=os.fstatvfs(parent.fd)
        require(space.f_bavail*space.f_frsize>=MAX_BYTES+base.RESERVE_BYTES,'BUNDLE_CAPACITY_REJECTED')
        # Created outside transferred data; no inherited credentials or config.
        with tempfile.TemporaryDirectory(prefix='slc-postgres-save-') as config:
            env={'PATH':os.defpath,'HOME':'/nonexistent','LANG':'C.UTF-8','DOCKER_CONFIG':config}
            inspect_local_image(env)
            parent.check();os.mkdir(parts[-1],mode=0o700,dir_fd=parent.fd)
            directory=parent.child(parts[-1],stack);directory.names(set())
            files={'postgres.tar':base.File(directory,'postgres.tar',stack,create=True)}
            save_image(files['postgres.tar'],env)
        source_binding(commit)
        safe=base.canonical(evidence(commit))
        item={'archive':'postgres.tar','size':files['postgres.tar'].initial.st_size,'sha256':digest_file(files['postgres.tar'])}
        check_item(item)
        raw=base.canonical({'format':FORMAT,'source_commit':commit,'contract':contract(),'image':item,
                            'evidence_sha256':hashlib.sha256(safe).hexdigest()})
        digest=hashlib.sha256(raw).hexdigest();state['receipt']={'source_commit':commit,'manifest_sha256':digest}
        for name,data in [('evidence.json',safe),('manifest.json',raw)]:
            files[name]=base.File(directory,name,stack,create=True)
            base.write_bytes(files[name],data);files[name].written()
        verify_files(directory,files,commit,digest,False)
        for file in files.values():file.handle.close()
        directory.names(FILES);os.fsync(directory.fd)
        state['completion_attempted']=True
        marker=base.File(directory,'COMPLETE',stack,create=True);marker.written();marker.handle.close()
        directory.names(FILES|{'COMPLETE'});os.fsync(directory.fd);os.fsync(parent.fd)
    return {'status':EXPORTED,'source_commit':commit,'manifest_sha256':digest}


def run(commit,destination):
    state={'completion_attempted':False};previous=None;attempted=False
    try:
        with bounded(1200):
            try:
                previous=signal.getsignal(signal.SIGTERM)
                def interrupted(_signum,_frame):raise KeyboardInterrupt()
                attempted=True;signal.signal(signal.SIGTERM,interrupted)
                result=_run(commit,destination,state)
            finally:
                if attempted:signal.signal(signal.SIGTERM,previous)
        return result
    except (Exception,KeyboardInterrupt,SystemExit):
        code='BUNDLE_COMPLETION_UNCERTAIN' if state['completion_attempted'] else 'BUNDLE_IO_FAILED'
        raise base.BundleError(code,receipt=state.get('receipt')) from None


class Parser(argparse.ArgumentParser):
    def error(self,_message):raise base.BundleError()


def emit(stream,value):
    text=value+'\n'
    require(stream.write(text)==len(text),'BUNDLE_IO_FAILED')
    stream.flush()


def main(argv=None):
    completed=None
    try:
        parser=Parser(description=__doc__,allow_abbrev=False)
        parser.add_argument('mode',choices=['export','verify']);parser.add_argument('--run',action='store_true')
        parser.add_argument('--expected-commit',required=True);parser.add_argument('--destination')
        parser.add_argument('--directory');parser.add_argument('--expected-manifest-sha256')
        args=parser.parse_args(argv)
        if args.mode=='export':
            require(args.run and args.destination and args.directory is None and args.expected_manifest_sha256 is None)
            result=run(args.expected_commit,args.destination)
            completed=base.safe_receipt({key:result[key] for key in ('source_commit','manifest_sha256')})
        else:
            require(not args.run and args.directory and args.destination is None and args.expected_manifest_sha256)
            result=verify_bundle(args.directory,expected_commit=args.expected_commit,expected_manifest_sha256=args.expected_manifest_sha256)
        emit(sys.stdout,json.dumps(result,sort_keys=True));return 0
    except (Exception,KeyboardInterrupt,SystemExit) as error:
        if isinstance(error,SystemExit) and completed is None:
            raise
        receipt=completed or base.safe_receipt(getattr(error,'receipt',None))
        try:
            emit(sys.stderr,'POSTGRES_BUNDLE_BLOCKED_OR_UNCERTAIN; preserve partial output; no retry, load or database acceptance.')
            if receipt is not None and (completed is not None or getattr(error,'code',None)=='BUNDLE_COMPLETION_UNCERTAIN'):
                emit(sys.stderr,json.dumps({'status':'BUNDLE_COMPLETION_UNCERTAIN',**receipt},sort_keys=True))
        except (Exception,KeyboardInterrupt,SystemExit):
            pass
        return 2


if __name__=='__main__':sys.exit(main())
