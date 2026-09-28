import hashlib, json
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.core import Artifact, ComponentDefinition, Release, ReleaseComponent
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact

class SnapshotError(ValueError): pass

class SnapshotService:
    def create(self, db: Session, release_id):
        release = db.get(Release, release_id)
        if not release: raise SnapshotError("Release not found")
        rows = db.execute(select(Artifact, ReleaseComponent, ComponentDefinition).join(ReleaseComponent, Artifact.release_component_id == ReleaseComponent.id).join(ComponentDefinition, ReleaseComponent.component_definition_id == ComponentDefinition.id).where(ReleaseComponent.release_id == release_id)).all()
        if not rows: raise SnapshotError("Release has no artifacts")
        payload = []
        for artifact, component, definition in rows:
            if artifact.controlled and (not artifact.sha256 or not artifact.distribution_level):
                raise SnapshotError(f"Controlled artifact {artifact.filename} is missing SHA-256 or distribution policy")
            payload.append({"component": definition.code, "component_version": component.version, "filename": artifact.filename, "sha256": artifact.sha256, "classification": artifact.classification, "distribution_level": artifact.distribution_level, "ai_access_policy": artifact.ai_access_policy})
        payload.sort(key=lambda x: (x["component"], x["filename"]))
        digest = hashlib.sha256(json.dumps({"release": release.version, "artifacts": payload}, sort_keys=True).encode()).hexdigest()
        latest = db.scalar(select(ReleaseSnapshot).where(ReleaseSnapshot.release_id == release_id).order_by(ReleaseSnapshot.snapshot_number.desc()).limit(1))
        number = 1 if latest is None else latest.snapshot_number + 1
        snapshot = ReleaseSnapshot(snapshot_no=f"SNAP-{str(number).zfill(4)}-{str(release.id)[:8]}", release_id=release.id, snapshot_number=number, content_hash=digest, release_metadata_json={"version": release.version, "release_type": release.release_type})
        db.add(snapshot); db.flush()
        for artifact, component, definition in rows:
            db.add(SnapshotArtifact(snapshot_id=snapshot.id, source_artifact_id=artifact.id, component_code=definition.code, component_version=component.version, filename=artifact.filename, artifact_type=artifact.artifact_type, sha256=artifact.sha256, classification=artifact.classification, distribution_level=artifact.distribution_level, ai_access_policy=artifact.ai_access_policy, storage_reference=artifact.storage_reference))
        db.commit(); db.refresh(snapshot)
        return snapshot
