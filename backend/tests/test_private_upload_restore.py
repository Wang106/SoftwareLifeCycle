"""Synthetic upload media restored into fresh test-owned roots, not an operator tool."""
import hashlib
import io
import os

import pytest
from sqlalchemy import select

from app.models.audit import AuditEvent
from app.models.upload import PrivateUploadSession
from test_private_upload_sessions import upload_db, component_db, creation_db, service, reserve, DATA
from test_application_release_creation import request
from private_upload_restore import verify_restored


def stored_fixture(db, ids, source):
    svc=service(db,source)
    command,reservation=reserve(svc,db,ids)
    stored=svc.receive(command['request_id'],io.BytesIO(DATA),request(db,ids))
    part=source/(stored['object_id']+'.part');blob=source/(stored['object_id']+'.blob')
    assert part.stat().st_ino==blob.stat().st_ino and part.stat().st_nlink==2
    assert part.stat().st_dev==blob.stat().st_dev
    # Retain synthetic bytes after independently reading both aliases. No live input.
    assert part.read_bytes()==blob.read_bytes()==DATA
    assert hashlib.sha256(blob.read_bytes()).hexdigest()==stored['sha256']
    return command,stored,blob.read_bytes(),(blob.stat().st_dev,blob.stat().st_ino)


def restore_pair(root,stored,payload,linked=True):
    root.mkdir(mode=0o700)
    part=root/(stored['object_id']+'.part');blob=root/(stored['object_id']+'.blob')
    with part.open('xb') as file: file.write(payload)
    part.chmod(0o600)
    if linked: os.link(part,blob)
    else:
        with blob.open('xb') as file: file.write(payload)
        blob.chmod(0o600)
    return part,blob


@pytest.mark.parametrize('linked',[True,False])
def test_fresh_root_verified_from_original_record_not_old_location(upload_db,tmp_path,linked):
    db,ids,source=upload_db
    command,stored,payload,old_inode=stored_fixture(db,ids,source)
    source.rename(tmp_path/'original-not-used')
    root=tmp_path/'restored';part,blob=restore_pair(root,stored,payload,linked)
    assert (blob.stat().st_dev,blob.stat().st_ino)!=old_inode
    assert (part.stat().st_ino==blob.stat().st_ino) is linked
    assert part.stat().st_nlink==(2 if linked else 1)
    before=[(r.id,r.event_no) for r in db.scalars(select(AuditEvent)).all()]
    evidence=verify_restored(service(db,root),command['request_id'],request(db,ids),stored,root)
    assert evidence['bytes']==len(DATA) and evidence['sha256']==hashlib.sha256(DATA).hexdigest()
    row=db.get(PrivateUploadSession,command['request_id'])
    assert str(row.object_id)==stored['object_id'] and row.release_component_id==ids['component']
    assert row.state=='STORED_PRIVATE' and row.revision==4
    assert [(r.id,r.event_no) for r in db.scalars(select(AuditEvent)).all()]==before
    assert part.read_bytes()==blob.read_bytes()==payload


@pytest.mark.parametrize('bad',['empty','missing_stage','digest','length','other_object','extra_link'])
def test_historical_stored_receipt_does_not_prove_restored_bytes(upload_db,tmp_path,bad):
    db,ids,source=upload_db
    command,stored,payload,_=stored_fixture(db,ids,source)
    root=tmp_path/'restored'
    if bad=='empty': root.mkdir(mode=0o700)
    else:
        part,blob=restore_pair(root,stored,payload)
        if bad=='missing_stage': part.unlink()
        elif bad=='digest': blob.write_bytes(b'x'*len(payload))
        elif bad=='length': blob.write_bytes(payload+b'x')
        elif bad=='other_object':
            part.rename(root/'unrelated.part');blob.rename(root/'unrelated.blob')
        elif bad=='extra_link': os.link(blob,root/'extra')
    svc=service(db,root)
    assert svc.receipt(command['request_id'],request(db,ids))['stored_receipt']==stored
    from app.services.local_artifact_storage import StorageError
    with pytest.raises((AssertionError,StorageError,OSError)):
        verify_restored(svc,command['request_id'],request(db,ids),stored,root)
    assert svc.receipt(command['request_id'],request(db,ids))['stored_receipt']==stored
    assert source.joinpath(stored['object_id']+'.blob').read_bytes()==DATA
