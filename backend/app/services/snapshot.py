import hashlib
import json
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.actor import ActorContext
from app.models.core import Artifact, ComponentDefinition, Release, ReleaseComponent
from app.models.policy import ArtifactDistributionRule
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule
from app.services.audit import commit_with_audit

class SnapshotError(ValueError):
    pass

class SnapshotService:
    def create(
        self,
        db: Session,
        release_id,
        actor_context: ActorContext | None = None,
    ):
        actor = actor_context or ActorContext.legacy(None)
        release = db.get(Release, release_id)
        if not release:
            raise SnapshotError("Release not found")

        rows = db.execute(
            select(Artifact, ReleaseComponent, ComponentDefinition)
            .join(ReleaseComponent, Artifact.release_component_id == ReleaseComponent.id)
            .join(ComponentDefinition, ReleaseComponent.component_definition_id == ComponentDefinition.id)
            .where(ReleaseComponent.release_id == release_id)
        ).all()
        if not rows:
            raise SnapshotError("Release has no artifacts")

        artifact_ids = [artifact.id for artifact, _, _ in rows]
        policy_rules = db.scalars(
            select(ArtifactDistributionRule)
            .where(ArtifactDistributionRule.artifact_id.in_(artifact_ids))
        ).all() if artifact_ids else []

        rules_by_artifact = {}
        for rule in policy_rules:
            rules_by_artifact.setdefault(rule.artifact_id, []).append(rule)

        payload = []
        for artifact, component, definition in rows:
            if artifact.controlled and (not artifact.sha256 or not artifact.distribution_level):
                raise SnapshotError(
                    f"Controlled artifact {artifact.filename} is missing SHA-256 or distribution policy"
                )

            artifact_rules = sorted(
                [
                    {
                        "recipient_type": rule.recipient_type,
                        "purpose": rule.purpose,
                        "decision": rule.decision,
                        "recipient_code": rule.recipient_code,
                    }
                    for rule in rules_by_artifact.get(artifact.id, [])
                ],
                key=lambda x: (
                    x["recipient_type"],
                    x["purpose"],
                    x["recipient_code"] or "",
                    x["decision"],
                ),
            )

            if artifact.distribution_level != "INTERNAL_ONLY" and not artifact_rules:
                raise SnapshotError(
                    f"Artifact {artifact.filename} has no external distribution rule"
                )

            payload.append({
                "component": definition.code,
                "component_version": component.version,
                "filename": artifact.filename,
                "sha256": artifact.sha256,
                "classification": artifact.classification,
                "distribution_level": artifact.distribution_level,
                "ai_access_policy": artifact.ai_access_policy,
                "distribution_rules": artifact_rules,
            })

        payload.sort(key=lambda x: (x["component"], x["filename"]))
        digest = hashlib.sha256(
            json.dumps(
                {"release": release.version, "artifacts": payload},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

        latest = db.scalar(
            select(ReleaseSnapshot)
            .where(ReleaseSnapshot.release_id == release_id)
            .order_by(ReleaseSnapshot.snapshot_number.desc())
            .limit(1)
        )
        number = 1 if latest is None else latest.snapshot_number + 1
        snapshot = ReleaseSnapshot(
            snapshot_no=f"SNAP-{str(number).zfill(4)}-{str(release.id)[:8]}",
            release_id=release.id,
            snapshot_number=number,
            content_hash=digest,
            release_metadata_json={
                "version": release.version,
                "release_type": release.release_type,
            },
        )
        db.add(snapshot)
        db.flush()

        for artifact, component, definition in rows:
            snapshot_artifact = SnapshotArtifact(
                snapshot_id=snapshot.id,
                source_artifact_id=artifact.id,
                component_code=definition.code,
                component_version=component.version,
                filename=artifact.filename,
                artifact_type=artifact.artifact_type,
                sha256=artifact.sha256,
                classification=artifact.classification,
                distribution_level=artifact.distribution_level,
                ai_access_policy=artifact.ai_access_policy,
                storage_reference=artifact.storage_reference,
            )
            db.add(snapshot_artifact)
            db.flush()

            for rule in rules_by_artifact.get(artifact.id, []):
                db.add(
                    SnapshotArtifactDistributionRule(
                        snapshot_artifact_id=snapshot_artifact.id,
                        recipient_type=rule.recipient_type,
                        purpose=rule.purpose,
                        decision=rule.decision,
                        recipient_code=rule.recipient_code,
                    )
                )

        commit_with_audit(
            db,
            lambda: {
                "event_no": f"EVT-SN-{snapshot.id.hex}",
                "event_type": "SNAPSHOT",
                "action": "FROZEN",
                "entity_type": "RELEASE_SNAPSHOT",
                "entity_id": snapshot.id,
                "entity_ref": snapshot.snapshot_no,
                **actor.audit_fields(),
                "summary": "Release snapshot frozen",
                "payload": {
                    "release_id": str(release.id),
                    "release_version": release.version,
                    "release_type": release.release_type,
                    "snapshot_number": snapshot.snapshot_number,
                    "content_hash": snapshot.content_hash,
                    "artifact_count": len(rows),
                    "actor_source": actor.source,
                },
            },
        )
        db.refresh(snapshot)
        return snapshot
