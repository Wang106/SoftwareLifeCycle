from sqlalchemy.orm import Session
from test_command_concurrency_postgres import pg
from test_release_demo_evidence import verify, rows
from app.seed_release_evidence import seed_release_evidence, key, VERSIONS
from app.models.core import Release
from app.api.release_demo import evidence


def test_evidence_atomic_repeat_with_real_append_only_triggers(pg):
    engine,_=pg
    with Session(engine) as db:
        old=rows(db)
        seed_release_evidence(db); db.rollback()
        assert db.get(Release,key(VERSIONS[0])) is None
        assert rows(db)==old
        seed_release_evidence(db); db.commit(); verify(db)
        first=rows(db)
        seed_release_evidence(db); db.commit()
        assert first==rows(db)
        for model,records in old.items(): assert all(r in first[model] for r in records)
        assert [x['current_release_confirmed'] for x in evidence(db)['items']]==[True,True,False]
