"""Synthetic time-skew targets; no dump, backup, restore commands or live services."""
import hashlib
import io
import json

import pytest
from sqlalchemy import select

from app.models.audit import AuditEvent
from app.models.upload import PrivateUploadSession
from private_upload_restore import verify_restored, verify_scope_restored
from test_private_upload_sessions import upload_db, component_db, creation_db, service, reserve, DATA, SCOPE
from test_application_release_creation import request


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def records(db):
    # Complete synthetic target scope, never derived from a media manifest.
    return [{'id':str(r.id),'object':str(r.object_id),'scope':str(r.storage_scope_id),
             'component':str(r.release_component_id),'state':r.state,
             'bytes':r.expected_bytes,'sha256':r.sha256}
            for r in db.scalars(select(PrivateUploadSession).where(
                PrivateUploadSession.storage_scope_id==SCOPE).order_by(PrivateUploadSession.id)).all()]


def add(db,ids,source,payload):
    svc=service(db,source);command,_=reserve(svc,db,ids,payload)
    stored=svc.receive(command['request_id'],io.BytesIO(payload),request(db,ids))
    return command,stored


def copy_synthetic(root,stored,payload):
    # Only bytes created in this test, not an arbitrary restoration interface.
    part=root/(stored['object_id']+'.part');blob=root/(stored['object_id']+'.blob')
    with part.open('xb') as stream: stream.write(payload)
    part.chmod(0o600);blob.hardlink_to(part)


def media(root):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.iterdir())}


def scenario(upload_db,tmp_path):
    db,ids,source=upload_db
    a,sa=add(db,ids,source,DATA)
    target=tmp_path/'old-media';target.mkdir(mode=0o700)
    copy_synthetic(target,sa,DATA)
    old_media=media(target);trusted_media_hash=digest(old_media)
    b,sb=add(db,ids,source,b'synthetic B committed after media A')
    target_records=records(db);trusted_db_hash=digest(target_records)
    assert a['request_id']!=b['request_id'] and sa['object_id']!=sb['object_id']
    return db,ids,target,a,sa,b,sb,old_media,trusted_media_hash,target_records,trusted_db_hash


def test_individually_intact_old_A_media_new_AB_database_rejects(upload_db,tmp_path):
    db,ids,target,a,sa,b,sb,old,mh,new,dh=scenario(upload_db,tmp_path)
    assert digest(media(target))==mh and digest(records(db))==dh
    assert len(old)==2 and len(new)==2 and all(r['state']=='STORED_PRIVATE' for r in new)
    svc=service(db,target)
    assert verify_restored(svc,a['request_id'],request(db,ids),sa,target)['sha256']==sa['sha256']
    assert svc.receipt(b['request_id'],request(db,ids))['stored_receipt']==sb
    before_events=list(db.scalars(select(AuditEvent.id).order_by(AuditEvent.id)).all())
    with pytest.raises(AssertionError): verify_scope_restored(db,svc,request(db,ids),SCOPE,target)
    assert digest(media(target))==mh and digest(records(db))==dh
    assert list(db.scalars(select(AuditEvent.id).order_by(AuditEvent.id)).all())==before_events
    assert not (target/(sb['object_id']+'.blob')).exists()


def test_aligned_AB_media_accepts_all_database_requests(upload_db,tmp_path):
    db,ids,old,a,sa,b,sb,*_=scenario(upload_db,tmp_path)
    target=tmp_path/'aligned';target.mkdir(mode=0o700)
    copy_synthetic(target,sa,DATA)
    copy_synthetic(target,sb,b'synthetic B committed after media A')
    result=verify_scope_restored(db,service(db,target),request(db,ids),SCOPE,target)
    assert set(result)=={a['request_id'],b['request_id']}
    assert result[a['request_id']]['sha256']==sa['sha256']
    assert result[b['request_id']]['sha256']==sb['sha256']


def test_empty_media_never_reduces_expected_database_set(upload_db,tmp_path):
    db,ids,_,a,sa,b,sb,*_=scenario(upload_db,tmp_path)
    target=tmp_path/'empty';target.mkdir(mode=0o700)
    assert len(records(db))==2
    with pytest.raises(AssertionError):
        verify_scope_restored(db,service(db,target),request(db,ids),SCOPE,target)
    assert list(target.iterdir())==[] and len(records(db))==2


def test_no_committed_entries_is_not_a_vacuous_restore_pass(upload_db,tmp_path):
    db,ids,root=upload_db
    with pytest.raises(AssertionError):
        verify_scope_restored(db,service(db,root),request(db,ids),SCOPE,root)
