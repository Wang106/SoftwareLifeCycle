"""Closed synthetic media scope; no backup or restoration commands."""
import hashlib
import io
import uuid
import pytest
from sqlalchemy import select
from app.models.audit import AuditEvent
from app.services.local_artifact_storage import LocalArtifactStorage
from private_upload_restore import verify_closed_scope_restored, verify_restored
from test_private_upload_time_skew import add, copy_synthetic, digest, media, records
from test_private_upload_sessions import upload_db, component_db, creation_db, service, reserve, DATA, SCOPE
from test_application_release_creation import request


def target_a(upload_db, tmp_path):
    db, ids, source = upload_db
    a, receipt = add(db, ids, source, DATA)
    target = tmp_path / 'closed-media'; target.mkdir(mode=0o700)
    copy_synthetic(target, receipt, DATA)
    return db, ids, target, a, receipt


def test_old_A_database_new_AB_media_rejects_without_mutation(upload_db, tmp_path):
    db, ids, target, a, receipt = target_a(upload_db, tmp_path)
    # Independently generated synthetic B, not an actual time snapshot/dump.
    payload = b'synthetic later B absent from old target database'
    storage = LocalArtifactStorage(str(target), enabled=True, max_bytes=1024)
    b = storage.reserve(expected_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    storage.stage(b, io.BytesIO(payload)); storage.commit(b)
    dh, mh = digest(records(db)), digest(media(target))
    events = list(db.scalars(select(AuditEvent.id).order_by(AuditEvent.id)))
    assert len(records(db)) == 1 and len(media(target)) == 4
    assert verify_restored(service(db,target), a['request_id'], request(db,ids), receipt,target)
    assert digest(records(db)) == dh and digest(media(target)) == mh
    with pytest.raises(AssertionError, match='closed synthetic media set'):
        verify_closed_scope_restored(db,service(db,target),request(db,ids),SCOPE,target)
    assert digest(records(db)) == dh and digest(media(target)) == mh
    assert list(db.scalars(select(AuditEvent.id).order_by(AuditEvent.id))) == events


def test_exact_A_pair_accepts(upload_db,tmp_path):
    db,ids,target,a,receipt=target_a(upload_db,tmp_path)
    result=verify_closed_scope_restored(db,service(db,target),request(db,ids),SCOPE,target)
    assert set(result)=={a['request_id']}
    assert result[a['request_id']]['sha256']==receipt['sha256']


@pytest.mark.parametrize('kind',['part','blob','unrelated','directory','symlink'])
def test_extra_entries_reject_without_cleanup(upload_db,tmp_path,kind):
    db,ids,target,a,receipt=target_a(upload_db,tmp_path)
    extra=target/(str(uuid.uuid4())+'.'+kind)
    if kind=='directory': extra.mkdir()
    elif kind=='symlink': extra.symlink_to(tmp_path/'never-read')
    else: extra.write_bytes(b'synthetic retained bytes')
    before={p.name for p in target.iterdir()}
    with pytest.raises(AssertionError,match='closed synthetic media set'):
        verify_closed_scope_restored(db,service(db,target),request(db,ids),SCOPE,target)
    assert {p.name for p in target.iterdir()}==before


def test_reserved_record_is_unsupported_not_declared_orphaned(upload_db,tmp_path):
    db,ids,target,a,receipt=target_a(upload_db,tmp_path)
    reserve(service(db,target),db,ids)
    with pytest.raises(AssertionError,match='committed-only fixture'):
        verify_closed_scope_restored(db,service(db,target),request(db,ids),SCOPE,target)
    assert len(records(db))==2 and len(media(target))==2
