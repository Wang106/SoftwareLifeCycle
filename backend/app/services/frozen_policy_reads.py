"""SQL projections shared by exact and application Snapshot read pages."""
from sqlalchemy import func, select
from app.models.snapshot import SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule

def rule_exists():
    return select(SnapshotArtifactDistributionRule.id).where(
        SnapshotArtifactDistributionRule.snapshot_artifact_id == SnapshotArtifact.id).exists()


def artifacts(snapshot_id):
    a = SnapshotArtifact
    rule_count = select(func.count()).select_from(SnapshotArtifactDistributionRule).where(
        SnapshotArtifactDistributionRule.snapshot_artifact_id == a.id).scalar_subquery()
    return select(a.id, a.component_code, a.component_version, a.filename, a.artifact_type,
        a.sha256, a.classification, a.distribution_level, a.ai_access_policy,
        rule_count.label('rule_count')).where(a.snapshot_id == snapshot_id)


def rules(snapshot_id, artifact_id=None):
    a, r = SnapshotArtifact, SnapshotArtifactDistributionRule
    stmt = select(r.id, r.snapshot_artifact_id, a.filename, a.component_code,
        a.distribution_level, r.recipient_type, r.purpose, r.recipient_code, r.decision)\
        .select_from(r).join(a, a.id == r.snapshot_artifact_id).where(a.snapshot_id == snapshot_id)
    return stmt.where(a.id == artifact_id) if artifact_id is not None else stmt


def count(db, stmt):
    return db.scalar(select(func.count()).select_from(stmt.subquery()))


