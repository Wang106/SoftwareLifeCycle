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
