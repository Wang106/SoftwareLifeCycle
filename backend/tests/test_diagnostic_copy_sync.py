"""Only pytest-owned synthetic files; no operational retention policy."""
import errno
import hashlib
import json
import os

import pytest

from tests.synthetic_diagnostic_files import copy_once, readback


def snapshot(root):
    return {p.name: (p.read_bytes(), p.stat().st_ino, p.stat().st_size,
                     p.stat().st_mode, p.stat().st_mtime_ns)
            for p in root.iterdir()}


@pytest.mark.parametrize('failure', [None, 'before_marker', 'final_parent'])
def test_one_shot_copy_preserves_first_failure_and_visible_evidence(tmp_path, failure):
    source = tmp_path / 'source'
    source.mkdir(mode=0o700)
    data = {'observation': json.dumps({'state':'RECONCILIATION_REQUIRED',
        'stored_receipt':None}, sort_keys=True).encode(), 'observed_bytes':b'owned\x00synthetic\xff'}
    expected = tuple((n,len(b),hashlib.sha256(b).hexdigest()) for n,b in data.items())
    for name, payload in data.items():
        (source/name).write_bytes(payload)
    original = snapshot(source)
    destination = tmp_path / 'copy'
    parent_identity = (tmp_path.stat().st_dev, tmp_path.stat().st_ino)
    events = []
    injected = False
    first_error = OSError(errno.EIO, 'synthetic sync failure')
    def sync(stage, fd):
        nonlocal injected
        st = os.fstat(fd)
        identity = (st.st_dev, st.st_ino)
        events.append((stage, identity))
        if stage == 'final_parent':
            assert identity == parent_identity
            assert set(p.name for p in destination.iterdir()) == set(data) | {'COMPLETE'}
        if stage == 'before_marker':
            assert identity == (destination.stat().st_dev,destination.stat().st_ino)
            assert not (destination/'COMPLETE').exists()
        if stage == failure and not injected:
            injected = True
            raise first_error
        # A mistaken retry succeeds: the first failure must not be hidden by it.
        os.fsync(fd)
    receipts = []
    if failure:
        with pytest.raises(OSError) as caught:
            receipts.append(copy_once(source,destination,expected,sync=sync))
        assert caught.value is first_error
        assert injected and receipts == []
    else:
        receipts.append(copy_once(source,destination,expected,sync=sync))
        assert receipts == [{'copy_call_completed':True,'durability_verified':False}]
    assert sum(stage=='final_parent' for stage,_ in events) == (failure!='before_marker')
    assert sum(stage=='before_marker' for stage,_ in events) == 1
    assert snapshot(source) == original
    target_before = snapshot(destination)
    assert {n:v[0] for n,v in target_before.items() if n!='COMPLETE'} == data
    assert ('COMPLETE' in target_before) == (failure!='before_marker')
    # New readback proves current bytes only; it cannot issue a copy-call receipt.
    observed = readback(destination,expected)
    assert observed == {'members_match_now':True,'attachment_committed':False,
                        'durability_verified':False}
    assert receipts == ([] if failure else [{'copy_call_completed':True,'durability_verified':False}])
    assert snapshot(destination) == target_before and snapshot(source) == original
    assert json.loads((destination/'observation').read_bytes()) == {
        'state':'RECONCILIATION_REQUIRED','stored_receipt':None}
    assert len(events) == (1 if failure=='before_marker' else 3)
