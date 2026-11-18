"""Synthetic baseline selection: exact authorized ASR, no writes."""
import uuid
import pytest
from fastapi import HTTPException
from app.core.config import settings
from app.models.core import Release, ReleaseComponent, ComponentDefinition
from app.models.security import ProjectMembership, SoftwareMembership, SecurityPrincipal
from test_application_component_declaration import component_db, creation_db, creation_client, request, seed_components, service

def options(db, ids, **kw):
    return service(db).baseline_options(ids['release'], request(db, ids), **kw)

@pytest.mark.parametrize('kind', ['disabled','principal','project','software','draft','revoked','binding'])
def test_refuse_ineligible_selection(component_db, monkeypatch, kind):
    db, ids = component_db
    if kind == 'disabled': monkeypatch.setattr(settings,'application_component_declaration_enabled',False)
    elif kind == 'principal': db.get(SecurityPrincipal,ids['actor']).status='DISABLED'
    elif kind == 'project': db.get(ProjectMembership,ids['pm']).status='SUSPENDED'
    elif kind == 'software': db.get(SoftwareMembership,ids['sm']).status='SUSPENDED'
    elif kind == 'draft': db.get(Release,ids['release']).status='RELEASED'
    elif kind == 'revoked': db.get(Release,ids['standard']).status='REVOKED'
    else: db.get(Release,ids['release']).customer_scope_id=uuid.uuid4()
    db.commit()
    with pytest.raises(HTTPException): options(db,ids)
    assert not db.in_transaction()

def test_exact_baseline_pagination_preserves_instances(component_db):
    db,ids=component_db
    for version in ('same','same','other'):
        db.add(ReleaseComponent(release_id=ids['standard'],component_definition_id=ids['definition'],version=version,delta_type='ADDED'))
    db.add(ReleaseComponent(release_id=ids['release'],component_definition_id=ids['definition'],version='private-ASR',delta_type='ADDED'))
    inactive=ComponentDefinition(code='INACTIVE',name='Hidden',is_active=False);db.add(inactive);db.flush()
    db.add(ReleaseComponent(release_id=ids['standard'],component_definition_id=inactive.id,version='hidden',delta_type='ADDED'));db.commit()
    first=options(db,ids,limit=2)
    second=options(db,ids,limit=2,after=first['next_after'])
    rows=first['items']+second['items']
    assert first['release_id']==str(ids['release']) and first['standard_base_release_id']==str(ids['standard'])
    assert len(rows)==len({r['base_component_id'] for r in rows})==4
    assert [r['base_component_id'] for r in rows]==sorted(r['base_component_id'] for r in rows)
    assert all(r['component_definition_id']==str(ids['definition']) for r in rows)
    assert second['next_after'] is None and not db.in_transaction()

@pytest.mark.parametrize('limit',[0,51,-1,True,'25'])
def test_bounds(component_db,limit):
    db,ids=component_db
    with pytest.raises(HTTPException): options(db,ids,limit=limit)

def test_foreign_cursor_refused(component_db):
    db,ids=component_db
    with pytest.raises(HTTPException): options(db,ids,after=str(uuid.uuid4()))

def test_http_options_strict_private_query(creation_client,creation_db,monkeypatch):
    monkeypatch.setattr(settings,'application_component_declaration_enabled',True)
    client,headers,_=creation_client;db,raw=creation_db;ids=seed_components(db,raw)
    path='/api/v1/application-component-declaration/baseline-options'
    params={'release_id':str(ids['release'])}
    good=client.get(path,params=params,headers=headers)
    assert good.status_code==200,good.text
    assert good.headers['cache-control']=='private, no-store'
    assert len(good.json()['items'])==1
    assert client.get(path,params=params).status_code==401
    for extras in ({'standard_base_release_id':str(ids['standard'])},{'limit':'51'},{'limit':'1.0'},{'after':'bad'}):
        assert client.get(path,params={**params,**extras},headers=headers).status_code==422
    assert client.get(path,params=[('release_id',str(ids['release']))]*2,headers=headers).status_code==422

@pytest.mark.parametrize('target',['release','standard'])
def test_recorded_chain_revocation_refused(component_db,target):
    from app.models.revocation import ReleaseChainRevocation
    db,ids=component_db
    db.add(ReleaseChainRevocation(revocation_no='OPTIONS-REVOKED',release_id=ids[target],target_kind='RELEASE',snapshot_id=uuid.uuid4(),release_decision_id=uuid.uuid4(),reason='Synthetic',revoked_by='Synthetic'));db.commit()
    with pytest.raises(HTTPException): options(db,ids)
    assert not db.in_transaction()

def test_private_marker_not_discovered_even_with_malformed_audit(component_db):
    from app.models.audit import AuditEvent
    db,ids=component_db
    db.add(AuditEvent(event_no='EVT-ASRC-malformed',event_type='OTHER',action='CREATED',entity_type='RELEASE_COMPONENT',entity_id=ids['base'],entity_ref=str(ids['base']),actor_name='Synthetic',summary='Synthetic malformed receipt'));db.commit()
    assert options(db,ids)['items']==[]
    with pytest.raises(HTTPException): options(db,ids,after=str(ids['base']))

@pytest.mark.parametrize('kind',['revoked','expired','token','principal'])
def test_options_recheck_browser_session(component_db,kind):
    import hashlib
    from datetime import datetime,timedelta,timezone
    from app.models.security import BrowserSession
    from test_application_release_creation import TOKEN
    db,ids=component_db;now=datetime.now(timezone.utc);sid=uuid.uuid4()
    db.add(BrowserSession(id=sid,principal_id=uuid.uuid4() if kind=='principal' else ids['actor'],token_digest=hashlib.sha256((TOKEN+'x' if kind=='token' else TOKEN).encode()).hexdigest(),created_at=now-timedelta(minutes=5),expires_at=now+timedelta(minutes=-1 if kind=='expired' else 5),revoked_at=now if kind=='revoked' else None));db.commit()
    with pytest.raises(HTTPException) as exc: service(db).baseline_options(ids['release'],request(db,ids,sid))
    assert exc.value.status_code==401 and not db.in_transaction()
