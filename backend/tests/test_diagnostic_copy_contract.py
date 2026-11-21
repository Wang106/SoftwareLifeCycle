"""Synthetic, in-memory copy contract; no archive or production storage API."""
import copy
import hashlib
import json

import pytest

from tests.synthetic_diagnostic_copy import verify_copy


@pytest.fixture
def evidence():
    # Obtained before the writer operates; never derived from its destination.
    state = {'state': 'RECONCILIATION_REQUIRED', 'stored_receipt': None}
    source = {'observation': json.dumps(state, sort_keys=True).encode(),
              'observed_bytes': b'owned synthetic bytes\x00\xff'}
    expected = tuple((name, len(data), hashlib.sha256(data).hexdigest())
                     for name, data in source.items())
    return source, expected


def test_independent_readback_is_complete_but_not_committed(evidence):
    source, expected = evidence
    retained = copy.deepcopy(source)
    before = copy.deepcopy((source, retained))
    result = verify_copy(expected, retained, closed=True)
    assert result == {'synthetic_copy_complete': True, 'attachment_committed': False,
                      'distributable': False, 'bootable_backup': False,
                      'durability_verified': False}
    assert (source, retained) == before


@pytest.mark.parametrize('fault', ['missing', 'digest', 'size', 'metadata_only',
    'hashes_only', 'incomplete', 'promoted', 'receipt', 'extra', 'bad_manifest'])
def test_no_completion_for_incomplete_or_conflicting_copy(evidence, fault):
    source, expected = evidence
    retained = copy.deepcopy(source)
    closed = True
    if fault in ('missing', 'metadata_only'):
        retained.pop('observed_bytes')
    elif fault == 'digest':
        retained['observed_bytes'] = b'x' * len(source['observed_bytes'])
    elif fault == 'size':
        retained['observed_bytes'] += b'x'
    elif fault == 'hashes_only':
        retained = {name: digest.encode() for name, _, digest in expected}
    elif fault == 'incomplete':
        closed = False
    elif fault in ('promoted', 'receipt'):
        retained['observation'] = json.dumps({'state': 'STORED_PRIVATE' if fault == 'promoted'
            else 'RECONCILIATION_REQUIRED', 'stored_receipt': {} if fault == 'receipt' else None}).encode()
        # Even a matching independently declared digest cannot permit promotion.
        expected = tuple((n, len(b), hashlib.sha256(b).hexdigest()) for n,b in retained.items())
    elif fault == 'extra':
        retained['undeclared'] = b'x'
    elif fault == 'bad_manifest':
        expected = expected[:1]
    before = copy.deepcopy(retained)
    with pytest.raises(ValueError, match='incomplete diagnostic copy'):
        verify_copy(expected, retained, closed=closed)
    assert retained == before


def test_writer_claim_does_not_supply_missing_members(evidence):
    _, expected = evidence
    with pytest.raises(ValueError):
        verify_copy(expected, {}, closed=True)
