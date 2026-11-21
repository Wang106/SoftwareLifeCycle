"""Test-only read-only consistency witness, not a backup/restore application."""
from private_upload_loopback import inspect_disk


def verify_restored(service, request_id, request, expected, root):
    # The caller supplies an independently retained synthetic expected receipt.
    # A historical STORED_PRIVATE row alone is insufficient for current bytes.
    observed = service.inspect(request_id, request)
    status = observed['status']
    assert status['state'] == 'STORED_PRIVATE' and status['revision'] == 4
    assert status['stored_receipt'] == expected
    assert expected['request_id'] == str(request_id)
    assert observed['observed_for_revision'] == status['revision']
    assert observed['bytes'] == {'stage':'verified', 'object':'verified'}
    # Independent closed-file reread, including length/hash and valid link pair.
    # LocalArtifactStorage allows either a linked pair or two independent files;
    # do not invent an inode-preservation guarantee for a byte-copy restore.
    return inspect_disk(root, expected['object_id'], expected['expected_bytes'], expected['sha256'])


def verify_scope_restored(db, service, request, scope, root):
    """Complete committed set in a quiescent synthetic target scope only.

    No media manifest selects records. Not a scalable production catalogue or
    atomic backup proof: the fixture owns the DB and forbids concurrent writes.
    """
    import copy
    from sqlalchemy import select
    from app.models.upload import PrivateUploadSession

    def expected_records():
        rows = db.scalars(select(PrivateUploadSession).where(
            PrivateUploadSession.storage_scope_id == scope,
            PrivateUploadSession.state == 'STORED_PRIVATE',
        ).order_by(PrivateUploadSession.id).execution_options(populate_existing=True)).all()
        return [(row.id, copy.deepcopy(row.stored_receipt_json)) for row in rows]

    assert scope == service.storage_scope_id
    expected = expected_records()
    assert expected, 'no committed synthetic target records'
    db.rollback()
    evidence = {}
    for request_id, receipt in expected:
        evidence[request_id] = verify_restored(service, request_id, request, receipt, root)
    # Detect observed changes, without claiming sequential reads are atomic.
    assert expected_records() == expected
    db.rollback()
    return evidence  # no partial evidence escapes when any required object fails
