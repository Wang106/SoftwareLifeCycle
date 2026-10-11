"""Numeric-looking UUIDs round-trip through actual copied SQLite test schemas."""
import uuid
import pytest
from sqlalchemy import text, select, UUID, Uuid
from sqlalchemy.dialects import postgresql, sqlite
from app.models.snapshot import ReleaseSnapshot
from test_impact_assessments import context


@pytest.mark.parametrize('hex_value', [
    '12345678123442348234123456781234',
    '00000000000040008000000000000001',
    '123456781234423482341234567812e4',
    'abcdefabcdef4abc8abcabcdefabcdef',
])
def test_expired_snapshot_uuid_round_trip_without_numeric_conversion(context, hex_value):
    db, _, release, _, _ = context
    identity = uuid.UUID(hex_value)
    release_id = release.id
    row = ReleaseSnapshot(id=identity, snapshot_no='UUID-' + hex_value,
        release_id=release_id, snapshot_number=2, status='FROZEN', content_hash='a'*64)
    db.add(row); db.commit()
    assert row.id == identity and row.release_id == release_id
    stored, kind = db.execute(text('SELECT id, typeof(id) FROM release_snapshots WHERE snapshot_no=:no'),
        {'no': 'UUID-' + hex_value}).one()
    assert kind == 'text' and stored == identity.hex
    db.expunge_all()
    assert db.get(ReleaseSnapshot, identity).id == identity
    assert db.scalar(select(ReleaseSnapshot.id).where(ReleaseSnapshot.id == identity)) == identity


@pytest.mark.parametrize('type_', [UUID(as_uuid=True), Uuid(as_uuid=True)])
def test_test_compiler_is_sqlite_only(type_):
    assert type_.compile(dialect=sqlite.dialect()) == 'CHAR(32)'
    assert type_.compile(dialect=postgresql.dialect()) == 'UUID'
    assert isinstance(ReleaseSnapshot.__table__.c.id.type, UUID)
