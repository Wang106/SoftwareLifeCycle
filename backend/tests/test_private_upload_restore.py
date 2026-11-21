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


@pytest.mark.parametrize('uncertain',[False,True])
def test_finished_worker_bytes_do_not_override_committed_restore_contract(upload_db,monkeypatch,uncertain):
    import asyncio
    import copy
    import threading
    from sqlalchemy.orm import sessionmaker
    from app.services.local_artifact_storage import LocalArtifactStorage, StorageError
    from app.services.private_upload_http import owned_worker
    from private_upload_loopback import inspect_disk
    db,ids,root=upload_db
    command,reservation=reserve(service(db,root),db,ids)
    db.rollback()
    sessions=sessionmaker(bind=db.get_bind(),expire_on_commit=False)
    original_commit=LocalArtifactStorage.commit
    commits=[];finished=threading.Event();main_thread=threading.get_ident()
    def commit(storage,descriptor):
        assert descriptor.object_id==reservation['object_id']
        original_commit(storage,descriptor)
        commits.append(descriptor.object_id)
        if uncertain: raise StorageError('synthetic lost acknowledgement')
    monkeypatch.setattr(LocalArtifactStorage,'commit',commit)
    def worker():
        assert threading.get_ident()!=main_thread
        try:
            with sessions() as worker_db:
                return service(worker_db,root).receive(command['request_id'],io.BytesIO(DATA),request(worker_db,ids))
        finally: finished.set()
    async def run():
        if uncertain:
            with pytest.raises(StorageError,match='synthetic lost acknowledgement'):
                await owned_worker(worker)
            return None
        return await owned_worker(worker)
    stored=asyncio.run(run())
    assert finished.is_set() and commits==[reservation['object_id']]
    def files():
        result={}
        for suffix in ('.part','.blob'):
            path=root/(reservation['object_id']+suffix)
            payload=path.read_bytes();info=path.stat()
            assert payload==DATA and hashlib.sha256(payload).hexdigest()==command['sha256']
            result[path.name]=(payload,info.st_dev,info.st_ino,info.st_nlink,info.st_mode,info.st_size,info.st_mtime_ns)
        assert {p.name for p in root.iterdir()}==set(result)
        assert len({value[1:3] for value in result.values()})==1
        assert all(value[3]==2 for value in result.values())
        return result
    before_files=files()
    disk=inspect_disk(root,reservation['object_id'],len(DATA),command['sha256'])
    assert disk['bytes']==len(DATA) and disk['sha256']==command['sha256']
    def snapshot():
        with sessions() as fresh:
            row=fresh.get(PrivateUploadSession,command['request_id'])
            values=copy.deepcopy({column.name:getattr(row,column.name) for column in row.__table__.columns})
            audits=sorted((str(a.id),a.event_no) for a in fresh.scalars(select(AuditEvent)).all())
            receipt=service(fresh,root).receipt(command['request_id'],request(fresh,ids))
            return values,audits,copy.deepcopy(receipt)
    before=snapshot();row,_,receipt=before
    assert row['release_component_id']==ids['component'] and str(row['object_id'])==reservation['object_id']
    assert row['state']==('RECONCILIATION_REQUIRED' if uncertain else 'STORED_PRIVATE')
    assert row['stored_receipt_json']==stored and receipt['stored_receipt']==stored
    assert receipt['reservation']==reservation
    with sessions() as fresh:
        svc=service(fresh,root)
        observed=svc.inspect(command['request_id'],request(fresh,ids))
        assert observed['bytes']=={'stage':'verified','object':'verified'}
        assert observed['status']==receipt
        if uncertain:
            with pytest.raises(AssertionError):
                verify_restored(svc,command['request_id'],request(fresh,ids),stored,root)
        else:
            evidence=verify_restored(svc,command['request_id'],request(fresh,ids),stored,root)
            assert evidence['sha256']==command['sha256']
    assert snapshot()==before and files()==before_files
