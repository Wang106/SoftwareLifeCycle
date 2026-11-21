"""Existing normal CI migrated disposable schema only; no database restore claim."""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.upload import PrivateUploadSession
from test_private_upload_sessions_postgres import upload_pg, component_pg, pg
from test_private_upload_sessions import service, DATA
from test_application_release_creation import request
from test_private_upload_restore import stored_fixture, restore_pair
from private_upload_restore import verify_restored


def test_new_root_bytes_and_original_postgresql_links(upload_pg,tmp_path):
    engine,ids,source=upload_pg
    with Session(engine) as db:
        command,stored,payload,old_inode=stored_fixture(db,ids,source)
        before=[(r.id,r.event_no) for r in db.scalars(select(AuditEvent)).all()]
    # Original bytes unavailable at the configured new location; receipts survive.
    source.rename(tmp_path/'source-not-used')
    root=tmp_path/'restored';root.mkdir(mode=0o700)
    with Session(engine) as db:
        svc=service(db,root)
        assert svc.receipt(command['request_id'],request(db,ids))['stored_receipt']==stored
        with pytest.raises(AssertionError):
            verify_restored(svc,command['request_id'],request(db,ids),stored,root)
    root.rmdir()  # exact empty fixture root only
    part,blob=restore_pair(root,stored,payload)
    assert (blob.stat().st_dev,blob.stat().st_ino)!=old_inode
    assert part.stat().st_ino==blob.stat().st_ino and blob.stat().st_nlink==2
    with Session(engine) as db:
        result=verify_restored(service(db,root),command['request_id'],request(db,ids),stored,root)
        row=db.get(PrivateUploadSession,command['request_id'])
        assert row.release_component_id==ids['component']
        assert str(row.object_id)==stored['object_id']
        assert str(row.actor_principal_id)==stored['actor_principal_id']
        assert str(row.storage_scope_id)==stored['storage_scope_id']
        assert row.expected_bytes==result['bytes']==len(DATA)
        assert row.sha256==result['sha256']==stored['sha256']
        assert row.state=='STORED_PRIVATE' and row.revision==4
        assert [(r.id,r.event_no) for r in db.scalars(select(AuditEvent)).all()]==before
    assert part.read_bytes()==blob.read_bytes()==DATA
