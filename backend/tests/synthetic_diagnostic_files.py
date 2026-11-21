"""Test-only adapter for exclusively owned tmp_path fixtures, not a public API.

No concurrent or hostile path substitution is modeled. No production caller,
archive format, retry, overwrite, cleanup or operational retention policy.
"""
import os

from tests.synthetic_diagnostic_copy import verify_copy

NAMES = ('observation', 'observed_bytes')


def _members(root):
    result = {}
    for name in NAMES:
        with (root/name).open('rb') as member:
            result[name] = member.read(4097)
    return result


def readback(root, expected):
    if {p.name for p in root.iterdir()} not in (set(NAMES), set(NAMES)|{'COMPLETE'}):
        raise ValueError('unexpected synthetic members')
    verify_copy(expected, _members(root), closed=True)
    return {'members_match_now':True, 'attachment_committed':False,
            'durability_verified':False}


def _sync(stage, fd):
    os.fsync(fd)


def copy_once(source, destination, expected, *, sync=_sync):
    payloads = _members(source)
    verify_copy(expected, payloads, closed=True)
    # The fixture owns both parents; destination must be absent. Never retry it.
    parent = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        destination.mkdir(mode=0o700)
        root = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for name in NAMES:
                with (destination/name).open('xb') as member:
                    member.write(payloads[name])
                    member.flush()
                    os.fsync(member.fileno())
            readback(destination,expected)
            sync('before_marker',root)
            with (destination/'COMPLETE').open('xb') as marker:
                marker.flush()
                os.fsync(marker.fileno())
            sync('marked_root',root)
            sync('final_parent',parent)
        finally:
            os.close(root)
    finally:
        os.close(parent)
    # Any earlier error propagates; visible marker alone never reaches this return.
    return {'copy_call_completed':True, 'durability_verified':False}
