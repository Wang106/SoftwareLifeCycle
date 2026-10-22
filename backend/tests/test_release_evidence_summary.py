from fastapi import HTTPException

from app.main import app
from app.api.release_evidence import evidence_summary
from app.models.core import Release
from app.seed_release_evidence import seed_release_evidence, key, VERSIONS
from test_impact_assessments import context
from test_release_demo_evidence import verify


def test_summary_matches_demo_evidence_for_installed_family(context):
    db = context[0]
    seed_release_evidence(db); db.commit()
    for i, version in enumerate(VERSIONS):
        release = db.get(Release, key(version))
        result = evidence_summary(release.id, db)
        assert result['release']['id'] == str(release.id)
        assert result['release']['version'] == version
        assert result['release']['release_type'] == release.release_type
        assert result['snapshot'] is not None and result['snapshot']['status'] == 'FROZEN'
        assert result['readiness']['overall'] in ('READY', 'NOT_READY')
        assert result['approval'] is not None and result['approval']['status'] == 'APPROVED'
        assert result['decision'] is not None
        assert result['current_release_confirmed'] == (i != 2)
        # The approval and decision both remain bound to the current snapshot for
        # every family member; the third one is simply a HOLD on a NOT_READY gate.
        assert result['approval']['current_snapshot_bound'] is True
        assert result['decision']['current_evidence_bound'] is True
        if i == 2:
            assert result['decision']['decision'] == 'HOLD'
            assert result['readiness']['overall'] == 'NOT_READY'
        else:
            assert result['decision']['decision'] == 'RELEASE'
            assert result['readiness']['overall'] == 'READY'
    verify(db)


def test_summary_empty_when_release_has_no_snapshot_or_governance(context):
    db = context[0]
    release = context[2]  # STANDARD release with a frozen snapshot, no approval/decision
    result = evidence_summary(release.id, db)
    assert result['release']['id'] == str(release.id)
    assert result['snapshot'] is not None and result['snapshot']['status'] == 'FROZEN'
    assert result['approval'] is None
    assert result['decision'] is None
    assert result['current_release_confirmed'] is False


def test_summary_handles_release_without_any_snapshot(context):
    from app.models.core import Release as ReleaseModel
    db = context[0]
    # A brand-new release with no snapshot, approval or decision.
    release = ReleaseModel(software_id=context[2].software_id, release_type='STANDARD',
        version='no-snapshot', status='DRAFT')
    db.add(release); db.commit()
    result = evidence_summary(release.id, db)
    assert result['snapshot'] is None
    assert result['approval'] is None
    assert result['decision'] is None
    assert result['current_release_confirmed'] is False


def test_summary_404_for_unknown_release(context):
    import uuid
    db = context[0]
    try:
        evidence_summary(uuid.uuid4(), db)
        assert False, 'expected HTTPException'
    except HTTPException as exc:
        assert exc.status_code == 404


def test_new_snapshot_breaks_binding_but_keeps_decision(context):
    from app.models.snapshot import ReleaseSnapshot
    db = context[0]
    seed_release_evidence(db); db.commit()
    db.add(ReleaseSnapshot(id=key('later'), snapshot_no='SNAP-DEMO-LATER', release_id=key(VERSIONS[0]),
        snapshot_number=2, status='FROZEN', content_hash='a' * 64))
    db.commit()
    result = evidence_summary(key(VERSIONS[0]), db)
    assert not result['current_release_confirmed']
    assert not result['decision']['current_evidence_bound']
    assert not result['approval']['current_snapshot_bound']
    assert result['decision']['decision'] == 'RELEASE'


def test_route_is_read_only():
    methods = {method for route in app.routes for method in getattr(route, 'methods', set())
               if getattr(route, 'path', None) == '/api/v1/releases/{release_id}/evidence-summary'}
    assert methods == {'GET'}
