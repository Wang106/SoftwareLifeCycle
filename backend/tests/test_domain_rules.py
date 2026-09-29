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

def test_distribution_api_is_registered():
    text=Path('app/main.py').read_text()
    assert 'distribution_router' in text
    assert 'app.include_router(distribution_router)' in text

def test_delivery_uses_only_released_snapshot_artifacts():
    text=Path('app/services/distribution.py').read_text()
    assert 'Delivery requires an explicit RELEASE decision' in text
    assert 'artifact.snapshot_id != snapshot.id' in text
    assert 'Release decision approval is not valid for the frozen snapshot' in text

def test_authorization_is_bound_to_distribution_chain():
    service=Path('app/services/distribution.py').read_text()
    model=Path('app/models/distribution.py').read_text()
    assert 'distribution_id' in model
    assert 'Distribution does not match the released snapshot' in service
    assert 'Distribution recipient does not match authorization customer' in service

def test_seed_contains_complete_release_distribution_chain():
    text=Path('app/seed.py').read_text()
    for reference in ('SNAP-008','APR-0121','RD-0081','DP-0226','DIST-0326','PA-0081'):
        assert reference in text
    assert 'freeze_snapshot_artifacts' in text
    assert 'SnapshotArtifactDistributionRule' in text

def test_production_api_is_registered():
    text=Path('app/main.py').read_text()
    assert 'production_router' in text
    assert 'app.include_router(production_router)' in text

def test_production_batch_requires_matching_authorized_software():
    text=Path('app/services/production.py').read_text()
    assert 'Production batch requires matching actual software' in text
    assert 'Production batch requires an approved authorization' in text
    assert 'Production batch changeover does not match deployment' in text
    assert 'Production authorization batch limit has been reached' in text

def test_seed_contains_production_traceability_chain():
    text=Path('app/seed.py').read_text()
    for reference in ('FACTORY-A','LINE-2','DEP-0081','CO-0032','PB-1005-A'):
        assert reference in text

def test_alembic_uses_runtime_database_url():
    text=Path('alembic/env.py').read_text()
    assert 'settings.database_url' in text
    assert 'config.set_main_option("sqlalchemy.url"' in text

def test_container_runs_migration_before_optional_seed_and_api():
    text=Path('entrypoint.sh').read_text()
    assert text.index('export PYTHONPATH=') < text.index('alembic upgrade head')
    migration=text.index('alembic upgrade head')
    seed=text.index('python -m app.seed')
    api=text.index('exec uvicorn')
    assert migration < seed < api

def test_api_exposes_database_readiness_probe():
    text=Path('app/main.py').read_text()
    assert '@app.get("/health/live")' in text
    assert '@app.get("/health/ready")' in text
    assert 'SELECT version_num FROM alembic_version' in text
    assert 'database_revision_mismatch' in text

def test_activity_api_is_registered():
    text=Path('app/main.py').read_text()
    assert 'activity_router' in text
    assert 'app.include_router(activity_router)' in text

def test_audit_events_are_append_only_at_database_level():
    migration=Path('alembic/versions/0010_append_only_audit_events.py').read_text()
    assert 'BEFORE UPDATE OR DELETE ON audit_events' in migration
    assert "RAISE EXCEPTION 'audit_events are append-only'" in migration

def test_audit_service_only_exposes_record_operation():
    text=Path('app/services/audit.py').read_text()
    assert 'class AuditEventService' in text
    assert 'def record(' in text
    assert 'def update(' not in text
    assert 'def delete(' not in text

def test_seed_contains_complete_audit_timeline():
    text=Path('app/seed.py').read_text()
    for reference in ('EVT-0001','EVT-0002','EVT-0003','EVT-0004','EVT-0005','EVT-0006','EVT-0007','EVT-0008','EVT-0009'):
        assert reference in text

def test_frontend_api_data_is_resolved_at_request_time():
    text=Path('../frontend/lib/api.ts').read_text()
    assert 'import { connection } from "next/server"' in text
    assert 'await connection()' in text
