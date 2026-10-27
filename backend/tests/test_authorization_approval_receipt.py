"""Read-only original approval receipts with current authority, never a new approval."""
import copy
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.security import ProjectMembership, SecurityPrincipal, BrowserSession
from app.services.audit import AuditEventService
from app.services.revocation import RevocationService
from test_authorization_approval import (approval_db, approval_client, actor_request, body, submit,
                                        service, counts, TOKEN)  # noqa:F401
from test_authorization_approval_postgres import approval_pg  # noqa:F401
from test_command_concurrency_postgres import pg  # noqa:F401


@pytest.fixture(params=['sqlite','postgres'])
def receipt_db(request):
    if request.param == 'sqlite':
        yield request.getfixturevalue('approval_db')
    else:
        engine, ids = request.getfixturevalue('approval_pg')
        with Session(engine, expire_on_commit=False) as db:
            yield db, ids


def read(db, ids, values, name='approver', request=None):
    return service(db).receipt(ids['number'], request or actor_request(db, ids, name), values['request_id'])


def test_readonly_original_after_later_revocation_has_no_effect(receipt_db, monkeypatch):
    db, ids = receipt_db; values = body(db, ids); original = submit(db, ids, values)
    RevocationService(db).revoke('AUTHORIZATION',ids['authorization'],'Later synthetic revocation',request_id=uuid.uuid4())
    monkeypatch.setattr(settings,'read_only_mode',True); before=counts(db)
    assert read(db,ids,values)==original
    assert not db.in_transaction()
    assert counts(db)==before
    assert set(original)=={'authorization_id','authorization_no','request_id','audit_event_no','applied_status',
        'approved_at','creator_principal_id','approver_principal_id','expected_context_digest','reason'}


@pytest.mark.parametrize('case',['unknown','other_actor'])
def test_foreign_and_unknown_receipts_generic404(receipt_db,case):
    db,ids=receipt_db;values=body(db,ids);submit(db,ids,values);before=counts(db)
    if case=='unknown':values={**values,'request_id':uuid.uuid4()}
    with pytest.raises(HTTPException) as error:read(db,ids,values,'other' if case=='other_actor' else 'approver')
    assert error.value.status_code==404 and error.value.detail=='approval_receipt_not_found'
    assert not db.in_transaction() and counts(db)==before


@pytest.mark.parametrize('case',['membership','principal','creator','service','admin'])
def test_current_authority_rechecked_before_history(receipt_db,case):
    db,ids=receipt_db;values=body(db,ids);submit(db,ids,values)
    if case=='membership':db.get(ProjectMembership,ids['grants']['approver']).status='SUSPENDED';db.commit()
    if case=='principal':db.get(SecurityPrincipal,ids['people']['approver']).status='DISABLED';db.commit()
    before=counts(db)
    with pytest.raises(HTTPException) as error:read(db,ids,values,case if case in ('creator','service','admin') else 'approver')
    assert error.value.status_code in (401,403) and not db.in_transaction()
    assert counts(db)==before


@pytest.mark.parametrize('revoked',[False,True])
def test_current_browser_session_required_when_claimed(receipt_db,revoked):
    db,ids=receipt_db;values=body(db,ids);original=submit(db,ids,values);now=datetime.now(timezone.utc);sid=uuid.uuid4()
    db.add(BrowserSession(id=sid,principal_id=ids['people']['approver'],token_digest=hashlib.sha256(TOKEN.encode()).hexdigest(),
        created_at=now,expires_at=now+timedelta(minutes=5),revoked_at=now if revoked else None));db.commit();before=counts(db)
    request=actor_request(db,ids,session_id=sid)
    if revoked:
        with pytest.raises(HTTPException) as error:read(db,ids,values,request=request)
        assert error.value.status_code==401
    else:assert read(db,ids,values,request=request)==original
    assert not db.in_transaction() and counts(db)==before


@pytest.mark.parametrize('case',['missing_receipt','legacy','wrong_target','wrong_action','wrong_reason','wrong_context','extra_receipt','wrong_time'])
def test_malformed_original_evidence_is_not_receipt(receipt_db,monkeypatch,case):
    db,ids=receipt_db;values=body(db,ids);original=AuditEventService.record
    def malformed(self,**kw):
        if kw['event_type']=='AUTHORIZATION_APPROVED':
            kw=copy.deepcopy(kw);p=kw['payload']
            if case=='missing_receipt':p.pop('receipt')
            elif case=='legacy':p['actor_source']='NOT_PROVIDED'
            elif case=='wrong_target':kw['entity_id']=ids['release']
            elif case=='wrong_action':kw['action']='OTHER'
            elif case=='wrong_reason':p['receipt']['reason']='Altered reason'
            elif case=='wrong_context':p['context']['project_id']=str(uuid.uuid4())
            elif case=='extra_receipt':p['receipt']['secret']='must not leak'
            elif case=='wrong_time':p['receipt']['approved_at']='invalid'
        return original(self,**kw)
    with monkeypatch.context() as patch:
        patch.setattr(AuditEventService,'record',malformed);submit(db,ids,values)
    before=counts(db)
    with pytest.raises(HTTPException) as error:read(db,ids,values)
    assert error.value.status_code==404 and error.value.detail=='approval_receipt_not_found'
    assert not db.in_transaction() and counts(db)==before


@pytest.mark.parametrize('method,suffix,disabled',[('GET','',False),('HEAD','',False),('GET','/',False),('HEAD','/',False),('GET','',True)])
def test_private_middleware_readonly_route(approval_client,monkeypatch,method,suffix,disabled):
    client,headers,ids=approval_client;root='/api/v1/authorizations/'+ids['number']
    context=client.get(root+'/approval-context',headers=headers).json();request_id=str(uuid.uuid4())
    original=client.post(root+'/approval',headers=headers,json={'request_id':request_id,
        'expected_context_digest':context['context_digest'],'reason':'Synthetic receipt route'}).json()
    monkeypatch.setattr(settings,'read_only_mode',True)
    if disabled:monkeypatch.setattr(settings,'auth_mode','disabled')
    response=client.request(method,root+'/approval-receipts/'+request_id+suffix,headers=headers,follow_redirects=False)
    assert response.status_code==(401 if disabled else 307 if suffix else 405 if method=='HEAD' else 200)
    assert response.headers['cache-control']=='private, no-store'
    if not disabled:assert 'x-browser-session' in response.headers['vary'].lower()
    if response.status_code==200:assert response.json()==original


def test_missing_token_receipt_is_private_401(approval_client):
    client,_headers,ids=approval_client
    response=client.get('/api/v1/authorizations/'+ids['number']+'/approval-receipts/'+str(uuid.uuid4()))
    assert response.status_code==401 and response.headers['cache-control']=='private, no-store'
