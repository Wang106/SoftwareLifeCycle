import uuid
import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import select
from test_impact_assessments import context
from test_change_coverage import coverage_context
from app.models.resource import ResourceLink
from app.models.audit import AuditEvent
from app.models.core import Customer, Project, Supplier
from app.models.testing import TestRelease as TestVersion, DvpExecution
from app.services.resource_links import ResourceInput, AuditEventService
from app.api.resources import create_resource, resource_detail, resource_catalog


def data(target, **kwargs):
    values = dict(request_id=uuid.uuid4(),entity_type='RELEASE',entity_id=target.id,title='Report',location_kind='WEB_URL',
        location='https://example.com/report.pdf',description='Evidence reference',actor_name='Engineer',reason='Bench review')
    values.update(kwargs); return ResourceInput(**values)


def catalog(db,**kwargs):
    args = dict(entity_type=None,entity_id=None,location_kind=None,q=None,limit=50,offset=0,db=db)
    args.update(kwargs); return resource_catalog(**args)


def test_idempotency_audit_and_snapshot_label(context):
    db,_,release,snapshot,_=context
    request=data(snapshot,entity_type='SNAPSHOT'); response=Response()
    row=create_resource(request,response,db)
    assert response.status_code==201 and row['entity_href']=='/snapshots/SNAP-1'
    assert create_resource(request,response,db)==row and response.status_code==200
    event=db.scalars(select(AuditEvent)).one()
    assert event.entity_type=='RESOURCE_LINK' and event.entity_id==request.request_id
    assert event.payload_json['target_id']==str(snapshot.id) and 'location' not in event.payload_json
    snapshot.snapshot_no='RENAMED';db.commit()
    assert resource_detail(request.request_id,db)['entity_ref']=='SNAP-1'
    assert len(db.scalars(select(ResourceLink)).all())==1


@pytest.mark.parametrize('field,value',[('title','Other'),('location','https://example.com/new'),('reason','Other'),('actor_name','Other'),('description','Other'),('entity_type','ISSUE')])
def test_idempotency_conflicts(context,field,value):
    db,_,release,*_=context
    request=data(release);create_resource(request,Response(),db)
    with pytest.raises(HTTPException) as error: create_resource(request.model_copy(update={field:value}),Response(),db)
    assert error.value.status_code==409 and len(db.scalars(select(AuditEvent)).all())==1


def test_missing_target_and_detail(context):
    db,_,release,*_=context
    with pytest.raises(HTTPException) as error: create_resource(data(release,entity_id=uuid.uuid4()),Response(),db)
    assert error.value.status_code==404 and not db.scalars(select(ResourceLink)).all()
    with pytest.raises(HTTPException) as error: resource_detail(uuid.uuid4(),db)
    assert error.value.status_code==404


def test_audit_failure_rolls_back(context,monkeypatch):
    db,_,release,*_=context
    def fail(*args,**kwargs): raise RuntimeError('audit unavailable')
    monkeypatch.setattr(AuditEventService,'record',fail)
    with pytest.raises(RuntimeError): create_resource(data(release),Response(),db)
    assert not db.scalars(select(ResourceLink)).all()


@pytest.mark.parametrize('kind,location',[
    ('WEB_URL','https://example.com/a?q=1#section'),('WEB_URL','http://example.com:8080/report'),
    ('LOCAL_PATH','/opt/reports/result.pdf'),('LOCAL_PATH',r'C:\Reports\result.pdf'),
    ('NETWORK_PATH',r'\\server\share\report.pdf'),('NETWORK_PATH','//server/share/report.pdf')])
def test_allowed_locations(kind,location):
    request=data(type('T',(),{'id':uuid.uuid4()})(),location_kind=kind,location=location)
    assert request.location==location


@pytest.mark.parametrize('kind,location',[
    ('WEB_URL','javascript:alert(1)'),('WEB_URL','data:text/html,hi'),('WEB_URL','file:///tmp/x'),
    ('WEB_URL','//example.com/file'),('WEB_URL','https://user:password@example.com'),('WEB_URL','https://user@example.com'),
    ('WEB_URL','https://example.com:bad/file'),('WEB_URL','https://example.com\\@other.com'),
    ('WEB_URL','https://example.com/%0afile'),('WEB_URL','https://example.com/a b'),
    ('LOCAL_PATH','../report'),('LOCAL_PATH','C:report'),('LOCAL_PATH','https://example.com'),
    ('NETWORK_PATH',r'\\server'),('NETWORK_PATH','//server/'),('NETWORK_PATH','/reports/file'),
    ('LOCAL_PATH','/tmp/a\nb')])
def test_rejects_unsafe_or_wrong_location(kind,location):
    with pytest.raises(ValidationError): data(type('T',(),{'id':uuid.uuid4()})(),location_kind=kind,location=location)


@pytest.mark.parametrize('field,value',[('title',' '),('actor_name','\t'),('reason',' '),('description','a\x00b'),('entity_type','UNKNOWN'),('location_kind','S3'),('status','ACTIVE')])
def test_input_validation(context,field,value):
    _,_,release,*_=context
    with pytest.raises(ValidationError): data(release,**{field:value})


def test_filtered_counts_literal_search_and_stable_paging(context):
    db,issue,release,snapshot,_=context
    create_resource(data(release,title='Report %_',description='Bench'),Response(),db)
    create_resource(data(issue,entity_type='ISSUE',title='Issue log',location_kind='LOCAL_PATH',location='/reports/a'),Response(),db)
    create_resource(data(snapshot,entity_type='SNAPSHOT',title='Frozen report'),Response(),db)
    first=catalog(db,limit=1);second=catalog(db,limit=1,offset=first['next_offset'])
    assert first['total']==second['total']==3 and first['items'][0]['id']!=second['items'][0]['id']
    assert first['kind_counts']=={'WEB_URL':2,'LOCAL_PATH':1}
    assert catalog(db,entity_type='ISSUE',entity_id=issue.id)['total']==1
    assert catalog(db,entity_type='ISSUE',entity_id=release.id)['total']==0
    assert catalog(db,location_kind='WEB_URL')['total']==2
    assert catalog(db,q='%_')['total']==1 and catalog(db,q='%missing')['total']==0
    assert catalog(db,offset=3)['items']==[] and catalog(db,offset=3)['next_offset'] is None


def test_all_target_routes(coverage_context):
    db,issue,release,snapshot,scr,criterion,points,items=coverage_context
    supplier=db.scalars(select(Supplier)).one()
    customer=Customer(code='C',name='Customer');db.add(customer);db.flush()
    project=Project(customer_id=customer.id,project_code='P',name='Project')
    version=TestVersion(test_release_no='TR-1',release_id=release.id,snapshot_id=snapshot.id,purpose_scope='SOFTWARE_TEST',status='DRAFT')
    execution=DvpExecution(dvp_item_id=items[0].id,execution_no=5,release_id=release.id,snapshot_id=snapshot.id,result='FAIL')
    db.add_all([project,version,execution]);db.commit()
    expected=[('SUPPLIER',supplier,f'/suppliers/{supplier.code}'),('CUSTOMER',customer,'/customers/C'),('PROJECT',project,f'/projects/{project.id}'),
        ('RELEASE',release,f'/releases/standard/{release.id}'),('SNAPSHOT',snapshot,f'/snapshots/{snapshot.snapshot_no}'),
        ('SCR',scr,f'/changes/{scr.request_no}'),('ISSUE',issue,f'/issues/{issue.issue_no}'),('DVP_ITEM',items[0],f'/testing/dvp/{items[0].id}'),
        ('TEST_RELEASE',version,'/testing/releases/TR-1'),('DVP_EXECUTION',execution,f'/testing/dvp/{items[0].id}')]
    for kind,target,href in expected:
        row=create_resource(data(target,entity_type=kind),Response(),db)
        assert row['entity_href']==href
    assert catalog(db)['total']==10 and len(db.scalars(select(AuditEvent)).all())==10


def test_original_resource_audit_has_complete_private_request_digest(context):
    import hashlib
    import json
    db, _, release, *_ = context
    request = data(release, title=' 中文标题 ', location='https://example.com/证据?q=1', description='说明')
    create_resource(request, Response(), db)
    event = db.scalars(select(AuditEvent)).one()
    fields = ['request_id','entity_type','entity_id','title','location_kind','location','description','actor_name','reason']
    values = request.model_dump(mode='json')
    expected = hashlib.sha256(json.dumps([values[k] for k in fields], ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
    assert event.payload_json['request_sha256'] == expected
    assert event.payload_json['request_digest_version'] == 1
    assert 'location' not in event.payload_json and 'description' not in event.payload_json
    assert 'request' not in event.payload_json
    original = dict(event.payload_json)
    release.version = 'RENAMED'; db.commit()
    create_resource(request, Response(), db)
    assert event.payload_json == original


@pytest.mark.parametrize('field', ['title','location','description','actor_name','reason'])
def test_resource_rejects_unpaired_surrogate_before_digest(context, field):
    _, _, release, *_ = context
    with pytest.raises(ValidationError):
        data(release, **{field: '\ud800'})
