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
