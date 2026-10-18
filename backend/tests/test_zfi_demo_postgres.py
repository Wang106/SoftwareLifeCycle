from concurrent.futures import ThreadPoolExecutor
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from test_command_concurrency_postgres import pg
from test_zfi_demo import verify, rows
from app.seed_zfi_demo import seed_zfi_demo,key
from app.models.core import Release,ApplicationReleaseDetail


def test_real_atomic_repeat(pg):
    engine,_=pg
    with Session(engine) as db:
        before=rows(db);seed_zfi_demo(db);db.rollback();assert rows(db)==before
        seed_zfi_demo(db);db.commit();verify(db);first=rows(db)
        seed_zfi_demo(db);db.commit();assert rows(db)==first


def test_concurrent_import_one_family(pg):
    engine,_=pg
    def run(_):
        with Session(engine) as db:result=seed_zfi_demo(db);db.commit();return result
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
    assert sorted(r['already_present'] for r in results)==[False,True]
    with Session(engine) as db:verify(db)


def test_customer_project_binding(pg):
    engine,_=pg
    with Session(engine) as db:
        seed_zfi_demo(db);db.commit()
        db.get(ApplicationReleaseDetail,key('ASR01')).project_id=key('project-11')
        with pytest.raises(IntegrityError,match='matching customer'):db.commit()
        db.rollback();verify(db)


def test_duplicate_and_immutable_identity(pg):
    engine,_=pg
    with Session(engine) as db:
        seed_zfi_demo(db);db.commit();r=db.get(Release,key('ASR01'))
        db.add(Release(software_id=r.software_id,release_type='APPLICATION',version=r.version,customer_scope_id=r.customer_scope_id))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback();db.get(Release,key('ASR01')).customer_scope_id=None
        with pytest.raises(IntegrityError,match='immutable'):db.commit()
        db.rollback();verify(db)


def test_refuse_downgrade_identity_loss(pg):
    engine,_=pg
    with Session(engine) as db:seed_zfi_demo(db);db.commit()
    with pytest.raises(Exception,match='customer-scoped release identities'):
        command.downgrade(Config('alembic.ini'),'0023_impact_withdrawal_history')
    with Session(engine) as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version'))=='0026_release_chain_revocation'
        verify(db)


def test_legacy_upgrade_downgrade_retains_history(pg):
    engine,_=pg
    query=text('SELECT id,software_id,release_type,version,status,release_notes,created_at FROM releases ORDER BY id')
    with engine.connect() as db:before=db.execute(query).all();audit=db.execute(text('SELECT * FROM audit_events ORDER BY id')).all()
    for _ in range(2):
        command.downgrade(Config('alembic.ini'),'0023_impact_withdrawal_history')
        command.upgrade(Config('alembic.ini'),'head')
        with engine.connect() as db:
            assert db.execute(query).all()==before
            assert db.execute(text('SELECT * FROM audit_events ORDER BY id')).all()==audit
