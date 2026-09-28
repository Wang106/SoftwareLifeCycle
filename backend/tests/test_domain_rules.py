from pathlib import Path

def test_snapshot_service_checks_controlled_artifact_integrity():
    text=Path('app/services/snapshot.py').read_text()
    assert 'missing SHA-256 or distribution policy' in text

def test_application_release_requires_one_standard_base():
    text=Path('app/models/core.py').read_text()
    assert 'standard_base_release_id' in text and 'nullable=False' in text

def test_snapshot_hash_includes_distribution_policy():
    text=Path('app/services/snapshot.py').read_text()
    assert 'distribution_level' in text and 'classification' in text and 'ai_access_policy' in text
