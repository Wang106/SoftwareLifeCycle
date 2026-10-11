from sqlalchemy.orm import Session
from test_command_concurrency_postgres import pg
from test_release_demo_seed import verify, rows
from app.seed_release_demo import seed_release_demo


def test_sample_repeat_with_real_append_only_triggers(pg):
    engine,_=pg
    with Session(engine) as db:
        old=rows(db); seed_release_demo(db); db.commit(); verify(db)
        first=rows(db); seed_release_demo(db); db.commit()
        assert first==rows(db)
        for model,records in old.items():
            assert all(record in first[model] for record in records)
