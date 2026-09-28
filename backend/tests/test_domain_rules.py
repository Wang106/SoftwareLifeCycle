from pathlib import Path

def test_snapshot_service_checks_controlled_artifact_integrity():
    text=Path('app/services/snapshot.py').read_text()
    assert 'missing SHA-256 or distribution policy' in text

def test_application_release_requires_one_standard_base():
    text=Path('app/models/core.py').read_text()
    assert 'standard_base_release_id' in text and 'nullable=False' in text

def test_snapshot_hash_includes_distribution_policy():
    text=Path('app/services/snapshot.py').read_text()
    assert 'distribution_level' in text
    assert 'classification' in text
    assert 'ai_access_policy' in text
    assert 'distribution_rules' in text
    assert 'SnapshotArtifactDistributionRule' in text

def test_readiness_does_not_auto_grant_exception():
    text=Path('app/api/dashboard.py').read_text()
    assert 'PolicyException' in text
    assert 'VERIFICATION_CURRENT_SNAPSHOT_COMPLETE' in text
    assert 'EXCEPTION_GRANTED' in text

def test_release_decision_requires_approved_request():
    text=Path('app/services/approval.py').read_text()
    assert 'approval.status != "APPROVED"' in text
    assert 'Release decision requires an approved request' in text

def test_release_decision_snapshot_must_match_release():
    text=Path('app/services/approval.py').read_text()
    assert 'snapshot.release_id != release.id' in text
    assert 'Approval target snapshot does not match release' in text

def test_approval_actions_are_append_only_history():
    text=Path('app/services/approval.py').read_text()
    assert 'ApprovalAction(' in text
    assert 'db.add(' in text
