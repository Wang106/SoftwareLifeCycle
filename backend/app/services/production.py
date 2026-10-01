from datetime import datetime, timezone
import uuid

from sqlalchemy import func, select
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
from app.services.command_retry import atomic_command, retry_result, timestamp_content


class ProductionError(ValueError):
    pass


class ProductionService:
    def __init__(self, db: Session):
        self.db = db

    def _lock(self, model, row_id):
        return self.db.scalar(select(model).where(model.id == row_id)
            .with_for_update().execution_options(populate_existing=True))

    def create_deployment(self, deployment_no, authorization_id, production_line_id,
                          actor_context=None, request_id=None):
        with atomic_command(self.db, ProductionError):
            return self._create_deployment(deployment_no, authorization_id,
                production_line_id, actor_context, request_id)

    def _create_deployment(
        self,
        deployment_no: str,
        authorization_id,
        production_line_id,
        actor_context: ActorContext | None = None,
        request_id=None,
    ):
        actor = actor_context or ActorContext.legacy(None)
        authorization = self._lock(SoftwareAuthorization, authorization_id)
        request_content = {"deployment_no": deployment_no,
            "authorization_id": str(authorization_id), "production_line_id": str(production_line_id)}
        existing = retry_result(self.db, Deployment, request_id, "EVT-DPLOY-",
                                request_content, actor, ProductionError)
        if existing is not None:
            self.db.commit()
            return existing
        if self.db.scalars(
            select(Deployment).where(Deployment.deployment_no == deployment_no)
        ).first():
            raise ProductionError("Deployment number already exists")

        if not authorization or authorization.status != "APPROVED":
            raise ProductionError("Deployment requires an approved production authorization")

        # Parent order: Authorization -> Site -> Line. The join only locks Site.
        site = self.db.scalar(select(ManufacturingSite).join(
            ProductionLine, ProductionLine.site_id == ManufacturingSite.id
        ).where(ProductionLine.id == production_line_id).with_for_update(of=ManufacturingSite)
          .execution_options(populate_existing=True))
        line = self._lock(ProductionLine, production_line_id)
        if not line or not site or line.status != "ACTIVE" or site.status != "ACTIVE":
            raise ProductionError("Deployment requires an active manufacturing site and line")
        if (
            line.site_id != site.id
            or site.customer_id != authorization.customer_id
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
        if request_id is not None:
            row.id = request_id
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
                    "request": request_content if request_id is not None else None,
                },
            },
        )
        self.db.refresh(row)
        return row

    def report_actual(self, deployment_no, actual_release_id, actual_snapshot_id,
                      deployed_at=None, actor_context=None):
        with atomic_command(self.db, ProductionError):
            return self._report_actual(deployment_no, actual_release_id,
                actual_snapshot_id, deployed_at, actor_context)

    def _report_actual(
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
            .with_for_update().execution_options(populate_existing=True)
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

    def create_changeover(self, deployment_no, changeover_no, from_release_id,
                         changed_at=None, note=None, actor_context=None, request_id=None):
        with atomic_command(self.db, ProductionError):
            return self._create_changeover(deployment_no, changeover_no,
                from_release_id, changed_at, note, actor_context, request_id)

    def _create_changeover(
        self,
        deployment_no: str,
        changeover_no: str,
        from_release_id,
        changed_at=None,
        note: str | None = None,
        actor_context: ActorContext | None = None,
        request_id=None,
    ):
        actor = actor_context or ActorContext.legacy(None)
        deployment = self.db.scalars(
            select(Deployment).where(Deployment.deployment_no == deployment_no)
            .with_for_update().execution_options(populate_existing=True)
        ).first()
        if not deployment:
            raise ProductionError("Deployment not found")
        request_content = {"deployment_no": deployment_no, "changeover_no": changeover_no,
            "from_release_id": str(from_release_id), "changed_at": timestamp_content(changed_at),
            "note": note}
        existing = retry_result(self.db, SoftwareChangeover, request_id, "EVT-CO-",
                                request_content, actor, ProductionError)
        if existing is not None:
            self.db.commit()
            return existing
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
            changed_at=(changed_at.replace(tzinfo=changed_at.tzinfo or timezone.utc)
                        if changed_at else datetime.now(timezone.utc)),
            note=note,
        )
        if request_id is not None:
            row.id = request_id
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
                    "request": request_content if request_id is not None else None,
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
        request_id=None,
    ):
        with atomic_command(self.db, ProductionError):
            return self._create_batch(deployment_no, batch_no, changeover_id,
                                      started_at, note, actor_context, request_id)

    def _create_batch(self, deployment_no, batch_no, changeover_id,
                      started_at, note, actor_context, request_id):
        actor = actor_context or ActorContext.legacy(None)
        deployment = self.db.scalars(
            select(Deployment).where(Deployment.deployment_no == deployment_no)
            .with_for_update().execution_options(populate_existing=True)
        ).first()
        if not deployment:
            raise ProductionError("Deployment not found")
        # All deployments sharing this authorization consume one quota. The
        # authorization lock is held through quota evaluation, insert and audit.
        authorization = self.db.scalar(select(SoftwareAuthorization).where(
            SoftwareAuthorization.id == deployment.authorization_id)
            .with_for_update().execution_options(populate_existing=True))
        request_content = {
            "deployment_no": deployment_no, "batch_no": batch_no,
            "changeover_id": str(changeover_id) if changeover_id else None,
            "started_at": timestamp_content(started_at), "note": note,
        }
        existing = retry_result(self.db, ProductionBatch, request_id, "EVT-PB-",
                                request_content, actor, ProductionError)
        if existing is not None:
            self.db.commit()
            return existing
        if deployment.status != "MATCH":
            raise ProductionError("Production batch requires matching actual software")
        if self.db.scalars(
            select(ProductionBatch).where(ProductionBatch.batch_no == batch_no)
        ).first():
            raise ProductionError("Production batch number already exists")

        if not authorization or authorization.status != "APPROVED":
            raise ProductionError("Production batch requires an approved authorization")
        existing_batch_count = self.db.scalar(
            select(func.count()).select_from(ProductionBatch).where(
                ProductionBatch.authorization_id == authorization.id
            )
        )
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
            started_at=(started_at.replace(tzinfo=started_at.tzinfo or timezone.utc)
                        if started_at else datetime.now(timezone.utc)),
            note=note,
        )
        if request_id is not None:
            row.id = request_id
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
                    "request": request_content if request_id is not None else None,
                },
            },
        )
        self.db.refresh(row)
        return row
