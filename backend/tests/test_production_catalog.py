import uuid
import pytest
from sqlalchemy import select,event
from fastapi.testclient import TestClient
from test_impact_assessments import context
from test_distribution_catalog import chain
from app.main import app
from app.models.production import Deployment,SoftwareChangeover,ManufacturingSite,ProductionLine,ProductionBatch
from app.api.production_catalog import ProductionFilters,production_catalog

@pytest.fixture
def production(chain):
    db,release,snapshot,old,packages,records,auth,customer,project=chain
    site=ManufacturingSite(site_code='SITE',customer_id=customer.id,project_id=project.id,name='Factory');db.add(site);db.flush()
    line=ProductionLine(site_id=site.id,line_code='LINE',name='Line');db.add(line);db.flush()
    dep=db.scalars(select(Deployment)).one();dep.production_line_id=line.id;dep.actual_release_id=release.id;dep.actual_snapshot_id=old.id
    co=SoftwareChangeover(changeover_no='CO-1',deployment_id=dep.id,authorization_id=auth[0].id,from_release_id=release.id,to_release_id=release.id,status='COMPLETED');db.add(co);db.flush()
    batches=db.scalars(select(ProductionBatch).order_by(ProductionBatch.batch_no)).all();batches[0].changeover_id=co.id
    pending=Deployment(deployment_no='DEP-2',authorization_id=auth[1].id,production_line_id=line.id,expected_release_id=release.id,expected_snapshot_id=old.id,status='PENDING');db.add(pending);db.commit()
    return db,release,snapshot,old,auth,dep,pending,co,batches,site,line

def catalog(db,kind,**kwargs):return production_catalog(kind,ProductionFilters(**kwargs),db)

def test_exact_history_and_optional_changeover(production):
    db,release,snapshot,old,auth,dep,pending,co,batches,site,line=production
    rows=catalog(db,'deployments');assert rows['total']==2
    first=rows['items'][0];assert first['software_observation']=='MATCH' and first['batch_count']==2 and first['changeover_count']==1 and first['context_consistent']
    assert rows['items'][1]['actual'] is None and rows['items'][1]['software_observation']=='NOT_RECORDED' and rows['items'][1]['context_consistent']
    batch=catalog(db,'batches')['items'][0]
    assert batch['recorded']['snapshot_no']==batch['actual']['snapshot_no']=='OLD' and batch['deployment']['id']==str(dep.id) and batch['context_consistent']
    assert batch['changeover']['changeover_no']=='CO-1' and not catalog(db,'batches')['items'][1]['changeover_linked']
    change=catalog(db,'changeovers')['items'][0]
    assert change['recorded']['release_id']==str(release.id) and change['recorded']['snapshot_id'] is None and change['context_consistent']

@pytest.mark.parametrize('kind,total',[('deployments',2),('changeovers',1),('batches',2)])
def test_filters_counts_and_paging(production,kind,total):
    db,release,_,old,auth,dep,*_=production
    page=catalog(db,kind,limit=1);assert page['total']==total and sum(page['status_counts'].values())==total
    if total>1:
        following=catalog(db,kind,limit=1,offset=page['next_offset']);assert following['items'][0]['id']!=page['items'][0]['id'] and following['next_offset'] is None
    assert catalog(db,kind,release_id=release.id,snapshot_id=old.id,site_code='SITE',line_code='LINE')['total']==total
    assert catalog(db,kind,line_code='OTHER')['total']==0 and catalog(db,kind,offset=100)['items']==[] and catalog(db,kind,q='%_')['total']==0

def test_uuid_scope_and_literal_search(production):
    db,release,_,old,auth,dep,pending,co,batches,site,line=production
    assert catalog(db,'batches',deployment_id=dep.id)['total']==2 and catalog(db,'deployments',authorization_id=auth[0].id)['total']==1
    assert catalog(db,'changeovers',customer_id=site.customer_id,project_id=site.project_id)['total']==1 and catalog(db,'batches',deployment_id=pending.id)['total']==0
    dep.deployment_no='DEP-%_';db.commit();assert catalog(db,'deployments',q='%_')['total']==1 and catalog(db,'deployments',q='%missing')['total']==0

@pytest.mark.parametrize('case,observation',[('partial','PARTIAL'),('different','MISMATCH'),('empty','NOT_RECORDED')])
def test_observations_do_not_trust_domain_status(production,case,observation):
    db,release,snapshot,old,auth,dep,*_=production
    if case=='partial':dep.actual_snapshot_id=None
    elif case=='different':dep.actual_snapshot_id=snapshot.id
    else:dep.actual_release_id=None;dep.actual_snapshot_id=None
    db.commit();row=catalog(db,'deployments',deployment_id=dep.id)['items'][0]
    assert row['status']=='MATCH' and row['software_observation']==observation and not catalog(db,'batches')['items'][0]['context_consistent']

@pytest.mark.parametrize('case,flag',[('wrong_authorization','authorization_binding'),('wrong_batch_snapshot','batch_authorization_binding'),('missing_changeover','changeover_missing'),('wrong_changeover','changeover_binding'),('wrong_location','authorized_location_binding'),('draft_snapshot','expected_snapshot_binding')])
def test_inconsistent_bindings_stay_visible(production,case,flag):
    db,release,snapshot,old,auth,dep,pending,co,batches,site,line=production
    if case=='wrong_authorization':batches[0].authorization_id=auth[1].id
    elif case=='wrong_batch_snapshot':batches[0].snapshot_id=snapshot.id
    elif case=='missing_changeover':batches[0].changeover_id=uuid.uuid4()
    elif case=='wrong_changeover':co.deployment_id=pending.id
    elif case=='wrong_location':line.line_code='OTHER'
    else:old.status='DRAFT'
    db.commit();row=catalog(db,'batches')['items'][0];assert not row['context_consistent'] and flag in row['binding_flags']

def test_missing_deployment_visible(production):
    db,*_,batches,site,line=production;batches[0].deployment_id=uuid.uuid4();db.commit()
    rows=catalog(db,'batches');assert rows['total']==2 and rows['items'][0]['deployment'] is None and 'deployment_missing' in rows['items'][0]['binding_flags']

def test_metadata_queries_remain_batched(production):
    db,*_=production;calls=[]
    def record(*args):calls.append(args[2])
    event.listen(db.bind,'before_cursor_execute',record)
    try:
        catalog(db,'deployments',limit=1);first=len(calls);calls.clear();catalog(db,'deployments',limit=100);assert len(calls)==first and first<15
    finally:event.remove(db.bind,'before_cursor_execute',record)

@pytest.mark.parametrize('path',['deployments?limit=0','batches?release_id=bad','changeovers?unknown=yes','invalid','deployments?offset=-1','batches?limit=101'])
def test_http_validation(path):
    with TestClient(app) as client:response=client.get('/api/v1/production/catalog/'+path)
    assert response.status_code==422,response.text
