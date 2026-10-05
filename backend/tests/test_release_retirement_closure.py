"""Retained scalar release APIs and the fixed 53-candidate closure boundary."""
import json,uuid
from pathlib import Path
import pytest
from sqlalchemy import create_engine,event,func,select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.core.db import get_db
from app.models.core import Release
from app.models.snapshot import ReleaseSnapshot
from app.models.change import ChangePoint,SoftwareChangeRequest
from app.models.testing import DvpExecution
from app.models.audit import AuditEvent
from app.api.dashboard import application_release_profile,application_release_downstream_summary,release_coverage
from app.api.compatibility_reads import RETIRED_READS
from test_impact_assessments import context
from test_coverage_aggregates import seed
from test_command_concurrency_postgres import pg


def bounded_reads(db,rid):
    result=[application_release_profile(rid,db),application_release_downstream_summary(rid,db),release_coverage(rid,db)]
    assert not any(isinstance(row,(ChangePoint,DvpExecution,SoftwareChangeRequest)) for row in db.identity_map.values())
    return result


def test_retained_scalar_reads_grow_without_child_loading(context):
    db,_,r,s,scr=context;r.release_type='APPLICATION';db.commit();rid,sid,scrid=r.id,s.id,scr.id
    queries=[]
    def record(conn,cursor,statement,parameters,context,many):queries.append(statement.lower())
    def read():
        db.expunge_all();queries.clear();result=bounded_reads(db,rid);return result,list(queries)
    event.listen(db.bind,'before_cursor_execute',record)
    try:
        small=read();seed(db,db.get(Release,rid),db.get(ReleaseSnapshot,sid),db.get(SoftwareChangeRequest,scrid),size=120);grown=read()
    finally:event.remove(db.bind,'before_cursor_execute',record)
    assert len(small[1])==len(grown[1])
    assert grown[0][0]['coverage']['required_dvp_total']==grown[0][2]['required_dvp_total']==120
    assert 'private' not in str(grown[0])
    assert not any('actual_result' in q or 'description' in q or 'requirement' in q for q in grown[1])


def test_retained_http_routes_and_read_only_guards(context,monkeypatch):
    from app import main
    db,_,r,*_=context;r.release_type='APPLICATION';db.commit();rid=str(r.id)
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    with engine.connect() as c:db.connection().connection.driver_connection.backup(c.connection.driver_connection)
    def sessions():
        with Session(engine) as s:yield s
    old=dict(app.dependency_overrides);app.dependency_overrides[get_db]=sessions;monkeypatch.setattr(main.settings,'read_only_mode',True)
    try:
        client=TestClient(app)
        for path in [f'/api/v1/releases/application/id/{rid}',f'/api/v1/releases/application/id/{rid}/downstream-summary',f'/api/v1/releases/{rid}/coverage']:
            response=client.get(path);assert response.status_code==200 and isinstance(response.json(),dict)
            assert client.get(path.replace(rid,str(uuid.uuid4()))).status_code==404
            assert client.get(path.replace(rid,'bad')).status_code==422
        assert client.post(f'/api/v1/releases/{rid}/create-snapshot',json={}).json()=={'detail':'read_only_mode'}
    finally:app.dependency_overrides.clear();app.dependency_overrides.update(old);engine.dispose()


def test_real_postgresql_retained_application_profile_and_coverage(pg):
    engine,ids=pg
    with Session(engine) as db:
        base=db.get(Release,ids['release'])
        r=Release(software_id=base.software_id,release_type='APPLICATION',version='GROW');db.add(r);db.flush()
        s=ReleaseSnapshot(release_id=r.id,snapshot_no='RETAIN-GROW',snapshot_number=1,content_hash='a'*64);db.add(s)
        scr=SoftwareChangeRequest(request_no='RETAIN-GROW',title='Growth',source='INTERNAL',scope='STANDARD',change_type='FIX',software_id=r.software_id);db.add(scr);db.flush()
        seed(db,r,s,scr,size=120);rid=r.id;before=db.scalar(select(func.count()).select_from(AuditEvent));db.expunge_all()
        result=bounded_reads(db,rid)
        assert result[0]['coverage']['required_dvp_total']==result[2]['required_dvp_total']==120
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before


def test_full_candidate_closure_is_disjoint_exact_and_commands_are_preserved():
    ledger=json.loads((Path(__file__).resolve().parents[2]/'docs/development-plan-progress.json').read_text())
    families=ledger['groups'][0]['milestones'];retired={p for p,_,_ in RETIRED_READS}
    candidates={p for f in families for p in f.get('routes',[])}
    bounded={p for f in families for p in f.get('bounded_evidence',{})}
    assert all(f['complete'] for f in families)
    assert len(candidates)==53 and len(retired)==50 and len(bounded)==3
    assert retired.isdisjoint(bounded) and candidates==retired|bounded
    for path in bounded:
        routes=[r for r in app.routes if r.path==path and 'GET' in (getattr(r,'methods',None) or set())]
        assert len(routes)==1 and not routes[0].deprecated
    from app.write_contracts import WRITE_CONTRACTS, SESSION_CONTROL_CONTRACTS, ADMIN_CONTROL_CONTRACTS
    writes = {('POST', r.path) for r in app.routes if 'POST' in (getattr(r,'methods',None) or set())}
    assert len(WRITE_CONTRACTS) == 14
    assert writes == set(WRITE_CONTRACTS) | set(SESSION_CONTROL_CONTRACTS) | set(ADMIN_CONTROL_CONTRACTS)
