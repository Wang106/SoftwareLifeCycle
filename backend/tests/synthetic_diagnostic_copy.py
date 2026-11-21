"""Test-only closed two-member model; not a production retention format."""
import hashlib
import json
import re


def verify_copy(expected, retained, *, closed):
    """Compare independent fixture expectations with retained in-memory bytes.

    The caller is the trusted synthetic fixture, not an arbitrary evidence writer.
    `closed` models writer completion, not durability or authenticity.
    """
    def refuse():
        raise ValueError('incomplete diagnostic copy')

    names = {'observation', 'observed_bytes'}
    if closed is not True or type(expected) is not tuple or len(expected) != 2:
        refuse()
    if type(retained) is not dict or set(retained) != names:
        refuse()
    seen = set()
    for entry in expected:
        if type(entry) is not tuple or len(entry) != 3:
            refuse()
        name, size, digest = entry
        if type(name) is not str or name not in names or name in seen:
            refuse()
        seen.add(name)
        if type(size) is not int or not 0 < size <= 4096:
            refuse()
        if type(digest) is not str or re.fullmatch('[0-9a-f]{64}', digest) is None:
            refuse()
        data = retained[name]
        if type(data) is not bytes or len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            refuse()
    # Exact fixture bytes prevent duplicate/extra JSON fields and state promotion.
    original = json.dumps({'state': 'RECONCILIATION_REQUIRED', 'stored_receipt': None},
                          sort_keys=True).encode()
    if retained['observation'] != original:
        refuse()
    return {'synthetic_copy_complete': True, 'attachment_committed': False,
            'distributable': False, 'bootable_backup': False, 'durability_verified': False}
