"""Signed HTTP synthetic upload and real coordinator, isolated SQLite/temp bytes."""
import asyncio
import hashlib
import json
import time
import uuid
from dataclasses import replace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, settings
from app.models.core import Artifact, Release
from app.models.security import ProjectMembership, SecurityPrincipal, SoftwareMembership
from app.models.upload import PrivateUploadSession
from app.services.private_upload_http import UploadHTTP, UploadPolicy
from test_private_upload_sessions import upload_db, component_db, creation_db, DATA, SCOPE, reserve, service
from test_application_release_creation import creation_client, request

BASE='/api/v1/private-uploads'


@pytest.fixture
def http_upload(upload_db, creation_client, monkeypatch):
    from app import main
    from app.api.private_uploads import get_upload_runtime
    db, ids, root = upload_db
    client, headers, _ = creation_client
    runtime = UploadHTTP(UploadPolicy(str(root),SCOPE,1024,1,.1,1),
                         sessionmaker(bind=db.get_bind(),expire_on_commit=False))
    monkeypatch.setattr(settings,'private_upload_http_enabled',True)
    main.app.dependency_overrides[get_upload_runtime] = lambda:runtime
    yield client,headers,db,ids,root,runtime
    main.app.dependency_overrides.pop(get_upload_runtime,None)


def command(client,headers,ids):
    result = client.get(BASE+'/context',params={'component_id':str(ids['component'])},headers=headers)
    assert result.status_code == 200, result.text
    return dict(request_id=str(uuid.uuid4()),component_id=str(ids['component']),expected_bytes=len(DATA),
        sha256=hashlib.sha256(DATA).hexdigest(),expected_context_digest=result.json()['context_digest'],reason='Synthetic HTTP test')


def send(client,headers,body,data=DATA):
    return client.put(BASE+'/'+body['request_id']+'/content',content=data,
                      headers={**headers,'Content-Type':'application/octet-stream'})


def test_signed_context_reserve_receive_original_receipt_and_no_artifact(http_upload):
    client,headers,db,ids,root,runtime=http_upload
    body=command(client,headers,ids)
    first=client.post(BASE+'/reservations',json=body,headers=headers)
    assert first.status_code==201,first.text
    replay=client.post(BASE+'/reservations',json=body,headers=headers)
    assert replay.status_code==200 and replay.json()==first.json()
    stored=send(client,headers,body)
    assert stored.status_code==200,stored.text
    assert stored.json()['state']=='STORED_PRIVATE'
    recovery=client.get(BASE+'/receipts/'+body['request_id'],headers=headers)
    assert recovery.json()['stored_receipt']==stored.json()
    assert recovery.json()['reservation']==first.json()
    before={p.name:p.read_bytes() for p in root.iterdir()}
    assert send(client,headers,body).status_code==409
    assert {p.name:p.read_bytes() for p in root.iterdir()}==before
    assert db.scalar(select(func.count()).select_from(Artifact))==0
    for response in (first,replay,stored,recovery):
        assert response.headers['cache-control']=='private, no-store'
        assert 'x-browser-session' in response.headers['vary'].lower()
        assert str(root) not in response.text and DATA.decode() not in response.text
    assert client.get(BASE+'/receipts/'+body['request_id']).status_code==401


@pytest.mark.parametrize('kind',['digest','extra','duplicate','malformed'])
def test_invalid_reservation_is_sanitized_and_does_not_store(http_upload,kind):
    client,headers,db,ids,root,_=http_upload; body=command(client,headers,ids)
    if kind=='digest': body['expected_context_digest']='0'*64
    if kind=='extra': body['filename']='PRIVATE_SENTINEL'
    data=json.dumps(body)
    if kind=='duplicate': data=data[:-1]+',"reason":"PRIVATE_SENTINEL"}'
    if kind=='malformed': data='PRIVATE_SENTINEL'
    response=client.post(BASE+'/reservations',content=data,headers={**headers,'Content-Type':'application/json'})
    assert response.status_code in (409,422)
    assert 'PRIVATE_SENTINEL' not in response.text and str(root) not in response.text
    assert list(root.iterdir())==[]


@pytest.mark.parametrize('kind',['project','software','principal','released','base','expiry'])
def test_changes_during_ingress_are_rechecked_before_storage(upload_db,kind):
    db,ids,root=upload_db; svc=service(db,root); body,_=reserve(svc,db,ids)
    runtime=UploadHTTP(UploadPolicy(str(root),SCOPE,1024,1,.1,1),sessionmaker(bind=db.get_bind(),expire_on_commit=False))
    req=request(db,ids); req.state.token_expires=time.time()+60
    req.scope['headers'] += [(b'content-type',b'application/octet-stream'),(b'content-length',str(len(DATA)).encode())]
    db.rollback()
    async def receive():
        assert not db.in_transaction()
        if kind=='project': db.get(ProjectMembership,ids['pm']).status='SUSPENDED'
        elif kind=='software': db.get(SoftwareMembership,ids['sm']).status='SUSPENDED'
        elif kind=='principal': db.get(SecurityPrincipal,ids['actor']).status='DISABLED'
        elif kind=='released': db.get(Release,ids['release']).status='RELEASED'
        elif kind=='base': db.get(Release,ids['standard']).status='REVOKED'
        else: req.state.token_expires=time.time()-1
        db.commit()
        return {'type':'http.request','body':DATA,'more_body':False}
    req._receive=receive
    with pytest.raises(HTTPException): asyncio.run(runtime.receive(body['request_id'],req))
    assert list(root.iterdir())==[]
    db.expire_all()
    assert db.get(PrivateUploadSession,body['request_id']).state=='RESERVED'


def test_response_lost_after_commit_recovers_only_original_receipt(http_upload,monkeypatch):
    client,headers,db,ids,root,runtime=http_upload; body=command(client,headers,ids)
    assert client.post(BASE+'/reservations',json=body,headers=headers).status_code==201
    original=runtime.call
    def lost(operation,*args,**kwargs):
        result=original(operation,*args,**kwargs)
        if operation=='receive': raise OSError('PRIVATE_SENTINEL '+str(root))
        return result
    monkeypatch.setattr(runtime,'call',lost)
    response=send(client,headers,body)
    assert response.status_code==503 and 'PRIVATE_SENTINEL' not in response.text and str(root) not in response.text
    recovery=client.get(BASE+'/receipts/'+body['request_id'],headers=headers)
    assert recovery.json()['state']=='STORED_PRIVATE'
    assert recovery.json()['stored_receipt']['request_id']==body['request_id']
    assert send(client,headers,body).status_code==409


def test_disabled_all_routes_are_private_and_inert(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(settings,'private_upload_http_enabled',False)
    with TestClient(app) as client:
        for method,path in [('get','/context'),('post','/reservations'),('put','/'+str(uuid.uuid4())+'/content'),('get','/receipts/'+str(uuid.uuid4()))]:
            response=getattr(client,method)(BASE+path)
            assert response.status_code==403
            assert response.headers['cache-control']=='private, no-store'
            assert 'x-browser-session' in response.headers['vary'].lower()


def test_enabled_configuration_requires_all_explicit_bounds():
    from pydantic import ValidationError
    with pytest.raises(ValidationError): Settings(_env_file=None,private_upload_http_enabled=True)
    policy=dict(private_upload_http_enabled=True,private_upload_root='/synthetic/not/accessed',
        private_upload_scope_id=SCOPE,private_upload_max_bytes=1024,private_upload_total_seconds=1,
        private_upload_idle_seconds=.1,private_upload_transfers=1)
    assert Settings(_env_file=None,**policy).private_upload_http_enabled
    for name,value in [('private_upload_max_bytes',8*1024*1024+1),('private_upload_transfers',0),
        ('private_upload_total_seconds',float('inf')),('private_upload_idle_seconds',2),
        ('private_upload_root','/a/../b'),('private_upload_scope_id',uuid.UUID(int=0))]:
        with pytest.raises(ValidationError): Settings(_env_file=None,**{**policy,name:value})


@pytest.mark.parametrize('kind',['other_actor','released','base','project','scope','consumed'])
def test_actual_coordinator_prebody_denials_do_not_read(upload_db,kind):
    db,ids,root=upload_db; svc=service(db,root); values,_=reserve(svc,db,ids)
    if kind=='consumed':
        import io
        svc.receive(values['request_id'],io.BytesIO(DATA),request(db,ids))
    if kind=='other_actor':
        other=SecurityPrincipal(issuer=settings.oidc_issuer_url,subject='other-upload',principal_type='USER',display_name='Other synthetic actor',status='ACTIVE')
        db.add(other);db.commit();ids={**ids,'actor':other.id}
    if kind=='released': db.get(Release,ids['release']).status='RELEASED'
    if kind=='base': db.get(Release,ids['standard']).status='REVOKED'
    if kind=='project': db.get(ProjectMembership,ids['pm']).status='SUSPENDED'
    db.commit();req=request(db,ids);req.state.token_expires=time.time()+60;db.rollback()
    req.scope['headers'] += [(b'content-type',b'application/octet-stream'),(b'content-length',str(len(DATA)).encode())]
    async def never(): raise AssertionError('denied request consumed body')
    req._receive=never
    runtime=UploadHTTP(UploadPolicy(str(root),uuid.uuid4() if kind=='scope' else SCOPE,1024,1,.1,1),sessionmaker(bind=db.get_bind(),expire_on_commit=False))
    before={p.name:p.read_bytes() for p in root.iterdir()}
    with pytest.raises(HTTPException): asyncio.run(runtime.receive(values['request_id'],req))
    assert {p.name:p.read_bytes() for p in root.iterdir()}==before


def test_sessions_created_used_and_closed_in_same_worker_before_network(upload_db):
    import threading
    from sqlalchemy.orm import Session
    db,ids,root=upload_db;values,_=reserve(service(db,root),db,ids)
    req=request(db,ids);req.state.token_expires=time.time()+60;db.rollback()
    req.scope['headers'] += [(b'content-type',b'application/octet-stream'),(b'content-length',str(len(DATA)).encode())]
    events=[]; main_thread=threading.get_ident()
    class Tracked(Session):
        def __init__(self,*args,**kwargs):
            self.owner=threading.get_ident();events.append(('open',self.owner));super().__init__(*args,**kwargs)
        def close(self):
            assert threading.get_ident()==self.owner!=main_thread
            assert not self.in_transaction();events.append(('close',self.owner));super().close()
    runtime=UploadHTTP(UploadPolicy(str(root),SCOPE,1024,1,.1,1),sessionmaker(bind=db.get_bind(),class_=Tracked,expire_on_commit=False))
    async def receive():
        assert [kind for kind,_ in events]==['open','close']
        return {'type':'http.request','body':DATA,'more_body':False}
    req._receive=receive
    assert asyncio.run(runtime.receive(values['request_id'],req))['state']=='STORED_PRIVATE'
    assert [kind for kind,_ in events]==['open','close','open','close']


class FrozenTestIngress:
    """Single-loop test entry only, not a production or cross-writer barrier."""
    def __init__(self,runtime):
        self.runtime=runtime; self.frozen=False; self.active=0

    async def receive(self,key,req):
        if self.frozen: raise RuntimeError('test ingress frozen')
        self.active+=1
        try: return await self.runtime.receive(key,req)
        finally: self.active-=1

    def freeze(self): self.frozen=True

    def capture(self,callback):
        if not self.frozen or self.active: raise RuntimeError('test ingress not drained')
        callback()


def test_frozen_entry_counts_body_wait_after_preflight_session_closed(upload_db):
    import threading
    from sqlalchemy.orm import Session
    from private_upload_loopback import inspect_disk
    db,ids,root=upload_db
    a,ar=reserve(service(db,root),db,ids)
    b,br=reserve(service(db,root),db,ids)
    assert a['request_id']!=b['request_id'] and ar['object_id']!=br['object_id']
    def make_request():
        req=request(db,ids);req.state.token_expires=time.time()+120
        req.scope['headers'] += [(b'content-type',b'application/octet-stream'),
            (b'content-length',str(len(DATA)).encode())]
        return req
    ra,rb=make_request(),make_request();db.rollback()
    events=[];main_thread=threading.get_ident()
    class Tracked(Session):
        def __init__(self,*args,**kwargs):
            self.owner=threading.get_ident();events.append(('open',self.owner))
            super().__init__(*args,**kwargs)
        def close(self):
            assert threading.get_ident()==self.owner!=main_thread
            assert not self.in_transaction()
            super().close();events.append(('close',self.owner))
    # Two slots deliberately leave capacity for B; rejection must be the test gate.
    runtime=UploadHTTP(UploadPolicy(str(root),SCOPE,1024,60,30,2),
        sessionmaker(bind=db.get_bind(),class_=Tracked,expire_on_commit=False))
    gate=FrozenTestIngress(runtime); captures=[];b_reads=[]
    async def scenario():
        waiting=asyncio.Event();release=asyncio.Event();a_reads=[]
        async def body_a():
            a_reads.append(1)
            assert [kind for kind,_ in events]==['open','close']
            if len(a_reads)==1:
                return {'type':'http.request','body':DATA[:3],'more_body':True}
            waiting.set();await release.wait()
            return {'type':'http.request','body':DATA[3:],'more_body':False}
        async def body_b():
            b_reads.append(1)
            raise AssertionError('frozen B must not read body')
        ra._receive=body_a;rb._receive=body_b
        task=asyncio.create_task(gate.receive(a['request_id'],ra))
        try:
            await asyncio.wait_for(waiting.wait(),5)
            assert not task.done() and gate.active==1 and not db.in_transaction()
            assert [kind for kind,_ in events]==['open','close']
            assert list(root.iterdir())==[]
            gate.freeze()
            with pytest.raises(RuntimeError,match='not drained'):
                gate.capture(lambda:captures.append('captured'))
            assert captures==[]
            assert runtime.permits.acquire(False)  # B has spare real runtime capacity
            runtime.permits.release()
            with pytest.raises(RuntimeError,match='frozen'):
                await gate.receive(b['request_id'],rb)
            assert b_reads==[] and [kind for kind,_ in events]==['open','close']
            assert list(root.iterdir())==[] and gate.active==1
            release.set()
            stored=await asyncio.wait_for(asyncio.shield(task),5)
            assert stored['request_id']==str(a['request_id'])
            assert stored['object_id']==ar['object_id'] and stored['state']=='STORED_PRIVATE'
            assert gate.active==0 and len(a_reads)==2
            assert [kind for kind,_ in events]==['open','close','open','close']
            recovered=service(db,root).receipt(a['request_id'],request(db,ids))
            assert recovered['stored_receipt']==stored and recovered['reservation']==ar
            witness=inspect_disk(root,stored['object_id'],len(DATA),hashlib.sha256(DATA).hexdigest())
            assert witness['sha256']==stored['sha256']
            assert (root/(stored['object_id']+'.blob')).read_bytes()==DATA
            other=service(db,root).receipt(b['request_id'],request(db,ids))
            assert other['state']=='RESERVED' and other['reservation']==br
            assert other['stored_receipt'] is None
            assert not (root/(br['object_id']+'.part')).exists()
            assert not (root/(br['object_id']+'.blob')).exists()
            gate.capture(lambda:captures.append('captured'))
            assert captures==['captured'] and gate.frozen
        finally:
            release.set()
            await asyncio.wait_for(asyncio.shield(task),5)
    asyncio.run(scenario())


def test_frozen_entry_waits_for_cancelled_real_storage_worker(upload_db,monkeypatch):
    import threading
    from sqlalchemy.orm import Session
    from app.services.local_artifact_storage import LocalArtifactStorage
    from private_upload_loopback import inspect_disk
    db,ids,root=upload_db
    values,reservation=reserve(service(db,root),db,ids)
    req=request(db,ids);req.state.token_expires=time.time()+120;db.rollback()
    req.scope['headers'] += [(b'content-type',b'application/octet-stream'),
        (b'content-length',str(len(DATA)).encode())]
    sessions=[];main_thread=threading.get_ident();body_reads=[];storage_reads=[]
    class Tracked(Session):
        def __init__(self,*args,**kwargs):
            self.owner=threading.get_ident();sessions.append('open')
            super().__init__(*args,**kwargs)
        def close(self):
            assert threading.get_ident()==self.owner!=main_thread
            assert not self.in_transaction()
            super().close();sessions.append('close')
    runtime=UploadHTTP(UploadPolicy(str(root),SCOPE,1024,60,30,1),
        sessionmaker(bind=db.get_bind(),class_=Tracked,expire_on_commit=False))
    gate=FrozenTestIngress(runtime);captures=[];release=threading.Event()
    original_stage=LocalArtifactStorage.stage
    async def scenario():
        loop=asyncio.get_running_loop();entered=asyncio.Event()
        def stage(storage,descriptor,source):
            assert descriptor.object_id==reservation['object_id']
            class GatedReader:
                def read(self,count):
                    storage_reads.append(count)
                    if len(storage_reads)==1:
                        assert threading.get_ident()!=main_thread
                        assert body_reads==[len(DATA)]
                        loop.call_soon_threadsafe(entered.set)
                        assert release.wait(5), 'test storage barrier timed out'
                    return source.read(count)
            return original_stage(storage,descriptor,GatedReader())
        monkeypatch.setattr(LocalArtifactStorage,'stage',stage)
        async def body():
            assert sessions==['open','close']
            body_reads.append(len(DATA))
            return {'type':'http.request','body':DATA,'more_body':False}
        req._receive=body
        task=asyncio.create_task(gate.receive(values['request_id'],req))
        try:
            await asyncio.wait_for(entered.wait(),5)
            # Actual stage has opened its exclusive .part, after HTTP digest validation.
            assert sessions==['open','close','open'] and gate.active==1
            part=root/(reservation['object_id']+'.part')
            assert part.is_file() and part.stat().st_size==0
            gate.freeze();assert task.cancel()
            # FIFO loop checkpoint: cancellation is delivered before this callback.
            # Worker progress itself is controlled solely by the threading Event.
            delivered=asyncio.Event();loop.call_soon(delivered.set)
            await asyncio.wait_for(delivered.wait(),5)
            assert not task.done() and task.cancelling()==1 and gate.active==1
            assert not runtime.permits.acquire(False)
            with pytest.raises(RuntimeError,match='not drained'):
                gate.capture(lambda:captures.append('captured'))
            assert captures==[] and sessions==['open','close','open']
            assert part.stat().st_size==0 and len(storage_reads)==1
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(task),5)
            assert task.cancelled() and gate.active==0
            assert sessions==['open','close','open','close']
            assert runtime.permits.acquire(False);runtime.permits.release()
            recovered=service(db,root).receipt(values['request_id'],request(db,ids))
            stored=recovered['stored_receipt']
            assert recovered['state']=='STORED_PRIVATE' and recovered['reservation']==reservation
            assert stored['request_id']==str(values['request_id'])
            assert stored['object_id']==reservation['object_id']
            row=db.get(PrivateUploadSession,values['request_id'])
            assert row.state=='STORED_PRIVATE' and row.release_component_id==ids['component']
            witness=inspect_disk(root,stored['object_id'],len(DATA),hashlib.sha256(DATA).hexdigest())
            assert witness['sha256']==stored['sha256']
            assert (root/(stored['object_id']+'.blob')).read_bytes()==DATA
            assert body_reads==[len(DATA)]
            gate.capture(lambda:captures.append('captured'))
            assert captures==['captured'] and gate.frozen
        finally:
            release.set()
            try: await asyncio.wait_for(asyncio.shield(task),5)
            except asyncio.CancelledError: pass
    asyncio.run(scenario())
