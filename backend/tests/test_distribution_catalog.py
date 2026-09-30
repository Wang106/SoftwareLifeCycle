import uuid
import pytest
from pydantic import ValidationError
from sqlalchemy import event
from fastapi.testclient import TestClient
from test_impact_assessments import context
from app.main import app
from app.models.core import Customer, Project, Release
from app.models.snapshot import ReleaseSnapshot
from app.models.distribution import DeliveryPackage,DeliveryPackageItem,Distribution,SoftwareAuthorization
from app.models.production import Deployment,ProductionBatch
from app.api.distribution_catalog import DeliveryFilters,DistributionFilters,AuthorizationFilters,delivery_catalog,distribution_catalog,authorization_catalog
from app.api.distribution import list_deliveries,list_distributions,list_authorizations


@pytest.fixture
def chain(context):
    db,_,release,snapshot,_=context
    customer=Customer(code='CUS-A',name='Customer');db.add(customer);db.flush()
    project=Project(customer_id=customer.id,project_code='PROJ',name='Project')
    old=ReleaseSnapshot(release_id=release.id,snapshot_no='OLD',snapshot_number=0,content_hash='b'*64,status='FROZEN')
    db.add_all([project,old]);db.flush()
    packages=[DeliveryPackage(package_no='DP-%_',revision=n,release_id=release.id,snapshot_id=s.id,recipient_type='CUSTOMER',recipient_code=customer.code,purpose='PRODUCTION',status='DISTRIBUTED') for n,s in [(1,old),(2,snapshot)]]
    db.add_all(packages);db.flush()
    records=[Distribution(distribution_no=f'DIST-{n}',delivery_package_id=packages[0].id,recipient_type='CUSTOMER',recipient_code=customer.code,status='ACKNOWLEDGED') for n in [1,2]]
    db.add_all(records);db.flush()
    auth=[SoftwareAuthorization(authorization_no=f'PA-{n}',distribution_id=records[0].id,release_id=release.id,snapshot_id=old.id,customer_id=customer.id,project_id=project.id,site_code='SITE',line_code='LINE',purpose='PRODUCTION',status='APPROVED',batch_limit=limit) for n,limit in [(1,2),(2,None)]]
    db.add_all(auth);db.flush()
    db.add_all([DeliveryPackageItem(delivery_package_id=packages[0].id,snapshot_artifact_id=uuid.uuid4(),policy_decision='ALLOW') for _ in range(3)])
    dep=Deployment(deployment_no='DEP',authorization_id=auth[0].id,production_line_id=uuid.uuid4(),expected_release_id=release.id,expected_snapshot_id=old.id,status='MATCH')
    db.add(dep);db.flush()
    db.add_all([ProductionBatch(batch_no=f'B-{n}',deployment_id=dep.id,authorization_id=auth[0].id,release_id=release.id,snapshot_id=old.id,status=status) for n,status in [(1,'PLANNED'),(2,'COMPLETED')]])
    db.commit();return db,release,snapshot,old,packages,records,auth,customer,project


def test_exact_package_revision_and_no_count_multiplication(chain):
    db,release,snapshot,old,packages,records,auth,*_=chain
    d=delivery_catalog(DeliveryFilters(),db)
    assert d['total']==2 and d['status_counts']=={'DISTRIBUTED':2}
    assert [(r['revision'],r['artifact_count'],r['distribution_count']) for r in d['items']]==[(1,3,2),(2,0,0)]
    rows=distribution_catalog(DistributionFilters(),db)['items']
    assert rows[0]['delivery']['revision']==1 and rows[0]['snapshot']['snapshot_no']=='OLD'
    assert [r['authorization_count'] for r in rows]==[2,0]
    assert all(r['context_consistent'] for r in rows)
    a=authorization_catalog(AuthorizationFilters(),db)['items'][0]
    assert a['delivery']['revision']==1 and a['snapshot']['snapshot_no']=='OLD' and a['context_consistent']
    assert a['registered_batches']==2 and a['remaining_batches']==0 and a['at_or_over_limit'] and a['deployment_count']==1


def test_unlimited_and_over_limit_observations(chain):
    db,_,_,old,_,_,auth,_,_=chain
    unlimited=authorization_catalog(AuthorizationFilters(q='PA-2'),db)['items'][0]
    assert unlimited['registered_batches']==0 and unlimited['remaining_batches'] is None and not unlimited['at_or_over_limit']
    auth[0].batch_limit=1;db.commit()
    row=authorization_catalog(AuthorizationFilters(q='PA-1'),db)['items'][0]
    assert row['registered_batches']==2 and row['remaining_batches']==0 and row['at_or_over_limit']


@pytest.mark.parametrize('catalog,model',[(delivery_catalog,DeliveryFilters),(distribution_catalog,DistributionFilters),(authorization_catalog,AuthorizationFilters)])
def test_stable_paging_counts_and_literal_search(chain,catalog,model):
    db,*_=chain
    first=catalog(model(limit=1),db);second=catalog(model(limit=1,offset=first['next_offset']),db)
    assert first['total']==second['total']==2 and first['status_counts']==second['status_counts']
    assert first['items'][0]['id']!=second['items'][0]['id'] and second['next_offset'] is None
    assert catalog(model(q='%_'),db)['total']==2
    assert catalog(model(q='%missing'),db)['total']==0
    empty=catalog(model(offset=20),db)
    assert empty['total']==2 and empty['items']==[] and empty['next_offset'] is None


@pytest.mark.parametrize('kind,filters,total',[
    ('delivery',{'recipient_code':'CUS-A'},2),('delivery',{'recipient_type':'FACTORY'},0),
    ('distribution',{'status':'ACKNOWLEDGED','purpose':'PRODUCTION'},2),('distribution',{'purpose':'TEST'},0),
    ('authorization',{'site_code':'SITE','line_code':'LINE'},2),('authorization',{'line_code':'OTHER'},0)])
def test_exact_filters(chain,kind,filters,total):
    db,*_=chain
    route,model={'delivery':(delivery_catalog,DeliveryFilters),'distribution':(distribution_catalog,DistributionFilters),'authorization':(authorization_catalog,AuthorizationFilters)}[kind]
    assert route(model(**filters),db)['total']==total


def test_uuid_scope_filters(chain):
    db,release,snapshot,old,packages,records,auth,customer,project=chain
    assert delivery_catalog(DeliveryFilters(snapshot_id=old.id,release_id=release.id),db)['total']==1
    assert distribution_catalog(DistributionFilters(delivery_package_id=packages[1].id),db)['total']==0
    assert authorization_catalog(AuthorizationFilters(customer_id=customer.id,project_id=project.id,distribution_id=records[0].id),db)['total']==2
    assert authorization_catalog(AuthorizationFilters(snapshot_id=snapshot.id),db)['total']==0
    assert authorization_catalog(AuthorizationFilters(release_id=uuid.uuid4()),db)['total']==0


@pytest.mark.parametrize('case',['snapshot_release','snapshot_draft','distribution_recipient','authorization_snapshot','project_customer','legacy_no_distribution'])
def test_inconsistent_history_is_visible_and_flagged(chain,case):
    db,release,snapshot,old,packages,records,auth,customer,project=chain
    if case=='snapshot_release': old.release_id=uuid.uuid4()
    elif case=='snapshot_draft': old.status='DRAFT'
    elif case=='distribution_recipient': records[0].recipient_code='OTHER'
    elif case=='authorization_snapshot': auth[0].snapshot_id=snapshot.id
    elif case=='project_customer': project.customer_id=uuid.uuid4()
    else: auth[0].distribution_id=None
    db.commit()
    rows=authorization_catalog(AuthorizationFilters(),db)
    assert rows['total']==2 and not rows['items'][0]['context_consistent']
    if case in {'snapshot_release','snapshot_draft','distribution_recipient'}:
        assert not distribution_catalog(DistributionFilters(),db)['items'][0]['context_consistent']


def test_missing_joined_record_does_not_hide_catalog_row(chain):
    db,_,_,_,packages,records,*_=chain
    records[0].delivery_package_id=uuid.uuid4();db.commit()
    row=distribution_catalog(DistributionFilters(q='DIST-1'),db)['items'][0]
    assert row['delivery'] is None and row['release'] is None and not row['context_consistent']


def test_batch_metadata_queries_do_not_grow_per_row(chain):
    db,*_=chain
    executed=[]
    def record(*args):executed.append(args[2])
    event.listen(db.bind,'before_cursor_execute',record)
    try:
        authorization_catalog(AuthorizationFilters(limit=1),db);first=len(executed);executed.clear()
        authorization_catalog(AuthorizationFilters(limit=100),db)
        assert first==len(executed)==5
    finally:event.remove(db.bind,'before_cursor_execute',record)


def test_legacy_lists_unchanged(chain):
    db,*_=chain
    assert isinstance(list_deliveries(db),list) and len(list_deliveries(db))==2
    assert isinstance(list_distributions(db),list) and len(list_distributions(db))==2
    assert isinstance(list_authorizations(db),list) and len(list_authorizations(db))==2


@pytest.mark.parametrize('query',['limit=0','limit=101','offset=-1','release_id=bad','q='+('x'*201),'unexpected=yes'])
def test_http_query_model_rejects_invalid_filters(query):
    with TestClient(app) as client:
        response=client.get('/api/v1/distribution/catalog/deliveries?'+query)
    assert response.status_code==422,response.text
