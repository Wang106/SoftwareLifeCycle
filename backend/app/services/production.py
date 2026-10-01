from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.actor import ActorContext
from app.models.core import Release
from app.models.distribution import SoftwareAuthorization
from app.models.production import (
    Deployment,
    ManufacturingSite,
    ProductionBatch,
    ProductionLine,
    SoftwareChangeover,
)
from app.models.snapshot import ReleaseSnapshot
from app.services.audit import commit_with_audit


class ProductionError(ValueError):
    pass


class ProductionService:
    def __init__(self, db: Session):
        self.db = db

    def create_deployment(
        self,
        deployment_no: str,
        authorization_id,
        production_line_id,
        actor_context: ActorContext | None = None,
    ):
        actor = actor_context or ActorContext.legacy(None)
        if self.db.scalars(
            select(Deployment).where(Deployment.deployment_no == deployment_no)
        ).first():
            raise ProductionError("Deployment number already exists")

        authorization = self.db.get(SoftwareAuthorization, authorization_id)
        if not authorization or authorization.status != "APPROVED":
            raise ProductionError("Deployment requires an approved production authorization")

        line = self.db.get(ProductionLine, production_line_id)
        site = self.db.get(ManufacturingSite, line.site_id) if line else None
        if not line or not site or line.status != "ACTIVE" or site.status != "ACTIVE":
            raise ProductionError("Deployment requires an active manufacturing site and line")
        if (
            site.customer_id != authorization.customer_id
            or site.project_id != authorization.project_id
            or site.site_code != authorization.site_code
            or line.line_code != authorization.line_code
        ):
            raise ProductionError("Manufacturing site/line does not match authorization scope")

        row = Deployment(
            deployment_no=deployment_no,
            authorization_id=authorization.id,
            production_line_id=line.id,
            expected_release_id=authorization.release_id,
            expected_snapshot_id=authorization.snapshot_id,
            status="PENDING",
        )
        self.db.add(row)
        commit_with_audit(
            self.db,
            lambda: {
                "event_no": f"EVT-DPLOY-{row.id.hex}",
                "event_type": "DEPLOYMENT",
                "action": "CREATED",
                "entity_type": "DEPLOYMENT",
                "entity_id": row.id,
                "entity_ref": row.deployment_no,
                **actor.audit_fields(),
                "summary": "Deployment expectation created",
                "payload": {
                    "authorization_id": str(authorization.id),
                    "production_line_id": str(line.id),
                    "expected_release_id": str(row.expected_release_id),
                    "expected_snapshot_id": str(row.expected_snapshot_id),
                    "status": row.status,
                    "actor_source": actor.source,
                },
            },
        )
        self.db.refresh(row)
        return row

    def report_actual(
        self,
        deployment_no: str,
        actual_release_id,
        actual_snapshot_id,
        deployed_at=None,
        actor_context: ActorContext | None = None,
    ):
        actor = actor_context or ActorContext.legacy(None)
        deployment = self.db.scalars(
            select(Deployment).where(Deployment.deployment_no == deployment_no)
        ).first()
        if not deployment:
            raise ProductionError("Deployment not found")

        release = self.db.get(Release, actual_release_id)
        snapshot = self.db.get(ReleaseSnapshot, actual_snapshot_id)
        if not release or not snapshot or snapshot.release_id != release.id:
            raise ProductionError("Actual snapshot does not belong to actual release")

        before = {
            "actual_release_id": str(deployment.actual_release_id)
            if deployment.actual_release_id
            else None,
            "actual_snapshot_id": str(deployment.actual_snapshot_id)
            if deployment.actual_snapshot_id
            else None,
            "status": deployment.status,
        }
        deployment.actual_release_id = release.id
        deployment.actual_snapshot_id = snapshot.id
        deployment.deployed_at = deployed_at or datetime.now(timezone.utc)
        deployment.status = (
            "MATCH"
            if release.id == deployment.expected_release_id
            and snapshot.id == deployment.expected_snapshot_id
            else "MISMATCH"
        )
        commit_with_audit(
            self.db,
            lambda: {
                "event_no": f"EVT-DA-{uuid.uuid4().hex}",
                "event_type": "DEPLOYMENT",
                "action": "ACTUAL_REPORTED",
                "entity_type": "DEPLOYMENT",
                "entity_id": deployment.id,
                "entity_ref": deployment.deployment_no,
                **actor.audit_fields(),
                "summary": "Actual deployed software reported",
                "occurred_at": deployment.deployed_at,
                "payload": {
                    "before": before,
                    "after": {
                        "actual_release_id": str(deployment.actual_release_id),
                        "actual_snapshot_id": str(deployment.actual_snapshot_id),
                        "status": deployment.status,
                    },
                    "actor_source": actor.source,
                },
            },
        )
        self.db.refresh(deployment)
        return deployment

    def create_changeover(
        self,
        deployment_no: str,
        changeover_no: str,
        from_release_id,
        changed_at=None,
        note: str | None = None,
        actor_context: ActorContext | None = None,
    ):
        actor = actor_context or ActorContext.legacy(None)
        deployment = self.db.scalars(
            select(Deployment).where(Deployment.deployment_no == deployment_no)
        ).first()
        if not deployment:
            raise ProductionError("Deployment not found")
        if self.db.scalars(
            select(SoftwareChangeover).where(
                SoftwareChangeover.changeover_no == changeover_no
            )
        ).first():
            raise ProductionError("Changeover number already exists")
        if not self.db.get(Release, from_release_id):
            raise ProductionError("Previous release not found")
        if from_release_id == deployment.expected_release_id:
            raise ProductionError("Changeover source and target release must differ")

        row = SoftwareChangeover(
            changeover_no=changeover_no,
            deployment_id=deployment.id,
            authorization_id=deployment.authorization_id,
            from_release_id=from_release_id,
            to_release_id=deployment.expected_release_id,
            status="COMPLETED",
            changed_at=changed_at or datetime.now(timezone.utc),
            note=note,
        )
        self.db.add(row)
        commit_with_audit(
            self.db,
            lambda: {
                "event_no": f"EVT-CO-{row.id.hex}",
                "event_type": "CHANGEOVER",
                "action": "COMPLETED",
                "entity_type": "SOFTWARE_CHANGEOVER",
                "entity_id": row.id,
                "entity_ref": row.changeover_no,
                **actor.audit_fields(),
                "summary": "Software changeover completed",
                "occurred_at": row.changed_at,
                "payload": {
                    "deployment_id": str(deployment.id),
                    "deployment_no": deployment.deployment_no,
                    "authorization_id": str(deployment.authorization_id),
                    "from_release_id": str(row.from_release_id),
                    "to_release_id": str(row.to_release_id),
                    "status": row.status,
                    "actor_source": actor.source,
                },
            },
        )
        self.db.refresh(row)
        return row

    def create_batch(
        self,
        deployment_no: str,
        batch_no: str,
        changeover_id=None,
        started_at=None,
        note: str | None = None,
        actor_context: ActorContext | None = None,
    ):
        actor = actor_context or ActorContext.legacy(None)
        deployment = self.db.scalars(
            select(Deployment).where(Deployment.deployment_no == deployment_no)
        ).first()
        if not deployment:
            raise ProductionError("Deployment not found")
        if deployment.status != "MATCH":
            raise ProductionError("Production batch requires matching actual software")
        if self.db.scalars(
            select(ProductionBatch).where(ProductionBatch.batch_no == batch_no)
        ).first():
            raise ProductionError("Production batch number already exists")

        authorization = self.db.get(SoftwareAuthorization, deployment.authorization_id)
        if not authorization or authorization.status != "APPROVED":
            raise ProductionError("Production batch requires an approved authorization")
        existing_batch_count = len(self.db.scalars(
            select(ProductionBatch).where(
                ProductionBatch.authorization_id == authorization.id
            )
        ).all())
        if authorization.batch_limit is not None and existing_batch_count >= authorization.batch_limit:
            raise ProductionError("Production authorization batch limit has been reached")
        changeover = self.db.get(SoftwareChangeover, changeover_id) if changeover_id else None
        if changeover_id and (
            not changeover
            or changeover.deployment_id != deployment.id
            or changeover.to_release_id != deployment.expected_release_id
            or changeover.status != "COMPLETED"
        ):
            raise ProductionError("Production batch changeover does not match deployment")

        row = ProductionBatch(
            batch_no=batch_no,
            deployment_id=deployment.id,
            changeover_id=changeover.id if changeover else None,
            authorization_id=authorization.id,
            release_id=deployment.expected_release_id,
            snapshot_id=deployment.expected_snapshot_id,
            status="ACTIVE",
            started_at=started_at or datetime.now(timezone.utc),
            note=note,
        )
        self.db.add(row)
        commit_with_audit(
            self.db,
            lambda: {
                "event_no": f"EVT-PB-{row.id.hex}",
                "event_type": "PRODUCTION_BATCH",
                "action": "STARTED",
                "entity_type": "PRODUCTION_BATCH",
                "entity_id": row.id,
                "entity_ref": row.batch_no,
                **actor.audit_fields(),
                "summary": "Production batch started",
                "occurred_at": row.started_at,
                "payload": {
                    "deployment_id": str(deployment.id),
                    "deployment_no": deployment.deployment_no,
                    "authorization_id": str(authorization.id),
                    "changeover_id": str(changeover.id) if changeover else None,
                    "release_id": str(row.release_id),
                    "snapshot_id": str(row.snapshot_id),
                    "status": row.status,
                    "actor_source": actor.source,
                },
            },
        )
        self.db.refresh(row)
        return row
