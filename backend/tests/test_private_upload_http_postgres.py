"""Normal CI disposable migrated PostgreSQL; never company/provider databases."""
import asyncio
import time
from dataclasses import replace

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker
from app.models.security import ProjectMembership
from app.models.upload import PrivateUploadSession
from app.services.private_upload_http import UploadHTTP, UploadPolicy
from test_command_concurrency_postgres import pg
from test_application_component_declaration_postgres import component_pg
from test_private_upload_sessions_postgres import upload_pg, prepared
from test_private_upload_sessions import DATA, SCOPE
from test_application_release_creation import request


def make_request(engine,ids,receive):
    with Session(engine) as db: req=request(db,ids)
    req.state.token_expires=time.time()+60
    req.scope['headers'] += [(b'content-type',b'application/octet-stream'),(b'content-length',str(len(DATA)).encode())]
    req._receive=receive
    return req


@pytest.mark.parametrize('revoke',[False,True])
def test_ingress_holds_no_parent_transaction_and_rechecks_revocation(upload_pg,revoke):
    engine,ids,root=upload_pg;command,_=prepared(upload_pg)
    value=UploadHTTP(UploadPolicy(str(root),SCOPE,1024,1,.1,1),sessionmaker(bind=engine,expire_on_commit=False))
    async def receive():
        # Independent connection can take the principal's membership row lock;
        # this would time out if ingress retained preflight's transaction locks.
        with Session(engine) as db:
            db.execute(text("SET LOCAL lock_timeout='500ms'"))
            row=db.scalar(select(ProjectMembership).where(ProjectMembership.id==ids['pm']).with_for_update())
            if revoke: row.status='SUSPENDED'
            db.commit()
        return {'type':'http.request','body':DATA,'more_body':False}
    req=make_request(engine,ids,receive)
    if revoke:
        with pytest.raises(HTTPException): asyncio.run(value.receive(command['request_id'],req))
        assert list(root.iterdir())==[]
    else: assert asyncio.run(value.receive(command['request_id'],req))['state']=='STORED_PRIVATE'
    with Session(engine) as db:
        assert db.get(PrivateUploadSession,command['request_id']).state==('RESERVED' if revoke else 'STORED_PRIVATE')


def test_independent_runtimes_cannot_store_same_reservation_twice(upload_pg):
    engine,ids,root=upload_pg;command,_=prepared(upload_pg)
    policy=UploadPolicy(str(root),SCOPE,1024,2,1,1)
    sessions=sessionmaker(bind=engine,expire_on_commit=False)
    async def run():
        arrived=0; both=asyncio.Event()
        async def receive():
            nonlocal arrived
            arrived+=1
            if arrived==2: both.set()
            await asyncio.wait_for(both.wait(),1)
            return {'type':'http.request','body':DATA,'more_body':False}
        async def attempt():
            try: return await UploadHTTP(policy,sessions).receive(command['request_id'],make_request(engine,ids,receive))
            except HTTPException as error: return error
        result=await asyncio.gather(attempt(),attempt())
        assert sum(isinstance(r,dict) and r['state']=='STORED_PRIVATE' for r in result)==1
        assert sum(isinstance(r,HTTPException) and r.detail=='private_upload_attempt_consumed' for r in result)==1
    asyncio.run(run())
    with Session(engine) as db: assert db.get(PrivateUploadSession,command['request_id']).revision==4
