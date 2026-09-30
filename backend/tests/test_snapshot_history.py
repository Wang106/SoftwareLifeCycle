import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.api.releases import list_snapshots
from app.models.core import Release


@pytest.fixture
def history_db():
    # Execute the actual list SQL against an isolated table; no production writes.
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('''CREATE TABLE release_snapshots (
            id VARCHAR(32) PRIMARY KEY, snapshot_no TEXT, release_id VARCHAR(32),
            snapshot_number INTEGER, status TEXT, release_metadata_json TEXT,
            content_hash TEXT, created_at DATETIME)'''))
    with Session(engine) as session:
        yield session
    engine.dispose()


def add_snapshot(db, release_id, number):
    db.execute(text('''INSERT INTO release_snapshots VALUES
        (:id, :snapshot_no, :release_id, :number, 'FROZEN', '{}', :hash, '2026-09-29 07:11:00')'''),
        {'id': uuid.uuid4().hex, 'snapshot_no': f'{release_id}-{number}',
         'release_id': release_id.hex, 'number': number, 'hash': 'a' * 64})


class HistorySession:
    def __init__(self, session, release):
        self.session, self.release = session, release

    def get(self, model, identifier):
        assert model is Release
        return self.release if self.release and identifier == self.release.id else None

    def execute(self, statement):
        return self.session.execute(statement)

    def scalars(self, statement):
        return self.session.scalars(statement)


@pytest.mark.parametrize('release_type', ['STANDARD', 'APPLICATION'])
def test_history_orders_and_paginates_with_release_isolation(history_db, release_type):
    release = Release(id=uuid.uuid4(), release_type=release_type, version='1.0')
    for number in [1, 7, 3]:
        add_snapshot(history_db, release.id, number)
    add_snapshot(history_db, uuid.uuid4(), 99)
    db = HistorySession(history_db, release)
    first = list_snapshots(release.id, limit=2, before_number=None, db=db)
    assert first['release']['type'] == release_type
    assert first['total'] == 3
    assert [row['snapshot_number'] for row in first['items']] == [7, 3]
    assert [row['is_current_snapshot'] for row in first['items']] == [True, False]
    assert first['next_before_number'] == 3
    second = list_snapshots(release.id, limit=2, before_number=3, db=db)
    assert second['total'] == 3
    assert [row['snapshot_number'] for row in second['items']] == [1]
    assert second['items'][0]['is_current_snapshot'] is False
    assert second['next_before_number'] is None
    assert len(second['items'][0]['content_hash']) == 64


def test_release_without_snapshots_has_empty_history(history_db):
    release = Release(id=uuid.uuid4(), release_type='STANDARD', version='1.0')
    result = list_snapshots(release.id, limit=20, before_number=None,
        db=HistorySession(history_db, release))
    assert result['items'] == []
    assert result['total'] == 0
    assert result['next_before_number'] is None


def test_history_cursor_beyond_oldest_is_empty(history_db):
    release = Release(id=uuid.uuid4(), release_type='APPLICATION', version='1.0')
    add_snapshot(history_db, release.id, 1)
    result = list_snapshots(release.id, limit=20, before_number=1,
        db=HistorySession(history_db, release))
    assert result['total'] == 1
    assert result['items'] == []
    assert result['next_before_number'] is None


def test_unknown_release_returns_404(history_db):
    with pytest.raises(HTTPException) as error:
        list_snapshots(uuid.uuid4(), limit=20, before_number=None,
            db=HistorySession(history_db, None))
    assert error.value.status_code == 404
