from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.actor import ActorContext, audit_actor_matches
from app.models.audit import AuditEvent
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
from app.models.production_history import (
    DeploymentActualBaseline,
    DeploymentActualCorrection,
)
from app.services.audit import AuditEventError, commit_with_audit
from app.services.command_retry import atomic_command, retry_result, timestamp_content
from app.services.revocation import ensure_chain_active, lock_chain
from app.services.production_history import effective_actual


class ProductionError(ValueError):
    pass


@dataclass(frozen=True)
class ActualReportResult:
    """Original committed report outcome, independent of later deployment writes."""
    id: uuid.UUID
    deployment_no: str
    status: str
    actual_version: int
    actual_release_id: uuid.UUID
    actual_snapshot_id: uuid.UUID
    deployed_at: datetime


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
        authorization = lock_chain(self.db, "AUTHORIZATION", authorization_id, ProductionError).authorization
        request_content = {"deployment_no": deployment_no,
            "authorization_id": str(authorization_id), "production_line_id": str(production_line_id)}
        existing = retry_result(self.db, Deployment, request_id, "EVT-DPLOY-",
                                request_content, actor, ProductionError)
        if existing is not None:
            self.db.commit()
            return existing
        if not authorization:
            raise ProductionError("Production authorization not found")
        ensure_chain_active(self.db, "AUTHORIZATION", authorization.id, ProductionError)
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
                      deployed_at=None, actor_context=None, request_id=None,
                      expected_version=None, correction_reason=None):
        with atomic_command(self.db, ProductionError):
            return self._report_actual(deployment_no, actual_release_id,
                actual_snapshot_id, deployed_at, actor_context, request_id,
                expected_version, correction_reason)

    @staticmethod
    def _actual_result(deployment, state):
        return ActualReportResult(
            id=deployment.id, deployment_no=deployment.deployment_no,
            status=state["status"], actual_version=state["actual_version"],
            actual_release_id=uuid.UUID(state["actual_release_id"]),
            actual_snapshot_id=uuid.UUID(state["actual_snapshot_id"]),
            deployed_at=datetime.fromisoformat(state["deployed_at"]),
        )

    def _report_actual(self, deployment_no, actual_release_id, actual_snapshot_id,
                       deployed_at, actor_context, request_id, expected_version,
                       correction_reason):
        actor = actor_context or ActorContext.legacy(None)
        if request_id is not None and expected_version is None:
            raise ProductionError("request_id requires expected_version")
        if expected_version is not None and (type(expected_version) is not int or expected_version < 0):
            raise ProductionError("expected_version must be a non-negative integer")
        if correction_reason is not None and (not correction_reason.strip() or len(correction_reason) > 2000):
            raise ProductionError("correction_reason must contain 1 to 2000 characters")
        deployment = self.db.scalar(
            select(Deployment).where(Deployment.deployment_no == deployment_no)
            .with_for_update().execution_options(populate_existing=True)
        )
        if not deployment:
            raise ProductionError("Deployment not found")
        request_content = {
            "deployment_no": deployment_no, "actual_release_id": str(actual_release_id),
            "actual_snapshot_id": str(actual_snapshot_id),
            "deployed_at": timestamp_content(deployed_at),
            "expected_version": expected_version, "correction_reason": correction_reason,
        }
        event_no = f"EVT-DA-{(request_id or uuid.uuid4()).hex}"
        if request_id is not None:
            event = self.db.scalar(select(AuditEvent).where(AuditEvent.event_no == event_no))
            if event is not None:
                if (event.entity_type != "DEPLOYMENT" or event.entity_id != deployment.id
                        or event.action not in ("ACTUAL_REPORTED", "ACTUAL_CORRECTED")
                        or not audit_actor_matches(event, actor)
                        or event.payload_json.get("request") != request_content):
                    raise ProductionError("request_id already used for different or legacy content")
                result = self._actual_result(deployment, event.payload_json["after"])
                self.db.commit()
                return result

        baseline = self.db.scalar(
            select(DeploymentActualBaseline)
            .where(DeploymentActualBaseline.deployment_id == deployment.id)
        )
        physical_reported = (
            deployment.actual_release_id is not None
            or deployment.actual_snapshot_id is not None
        )
        if baseline is None and physical_reported:
            # Compatibility for pre-ledger rows and direct model fixtures: capture
            # the already-stored fact before applying a keyed correction.
            baseline = DeploymentActualBaseline(
                deployment_id=deployment.id,
                actual_release_id=deployment.actual_release_id,
                actual_snapshot_id=deployment.actual_snapshot_id,
                recorded_status=deployment.status,
                recorded_actual_version=deployment.actual_version,
                recorded_deployed_at=deployment.deployed_at,
                source="IMPORTED_CURRENT",
            )
            self.db.add(baseline)
            self.db.flush()
        current = effective_actual(self.db, deployment)
        if expected_version is not None and expected_version != current.actual_version:
            raise ProductionError(
                f"actual_version conflict: expected {expected_version}, current {current.actual_version}"
            )
        is_correction = baseline is not None
        if is_correction and request_id is None:
            raise ProductionError(
                "Replacing an actual report requires request_id, expected_version and correction_reason"
            )
        if is_correction and correction_reason is None:
            raise ProductionError("Replacing an actual report requires correction_reason")

        release = self.db.get(Release, actual_release_id)
        snapshot = self.db.get(ReleaseSnapshot, actual_snapshot_id)
        if not release or not snapshot or snapshot.release_id != release.id:
            raise ProductionError("Actual snapshot does not belong to actual release")
        head = self.db.scalar(
            select(DeploymentActualCorrection)
            .where(DeploymentActualCorrection.deployment_id == deployment.id)
            .order_by(DeploymentActualCorrection.revision.desc()).limit(1)
        )
        actual_time = (
            deployed_at.replace(tzinfo=deployed_at.tzinfo or timezone.utc)
            if deployed_at else datetime.now(timezone.utc)
        )
        before = {
            "actual_release_id": str(current.actual_release_id) if current.actual_release_id else None,
            "actual_snapshot_id": str(current.actual_snapshot_id) if current.actual_snapshot_id else None,
            "status": current.status, "actual_version": current.actual_version,
            "deployed_at": timestamp_content(current.deployed_at),
        }
        status = ("MATCH" if release.id == deployment.expected_release_id
                  and snapshot.id == deployment.expected_snapshot_id else "MISMATCH")
        after = {
            "actual_release_id": str(release.id), "actual_snapshot_id": str(snapshot.id),
            "status": status, "actual_version": current.actual_version + 1,
            "deployed_at": timestamp_content(actual_time),
        }
        result = self._actual_result(deployment, after)

        if not is_correction:
            deployment.actual_release_id = release.id
            deployment.actual_snapshot_id = snapshot.id
            deployment.deployed_at = actual_time
            deployment.status = status
            deployment.actual_version = after["actual_version"]
            self.db.add(DeploymentActualBaseline(
                deployment_id=deployment.id, actual_release_id=release.id,
                actual_snapshot_id=snapshot.id, recorded_status=status,
                recorded_actual_version=after["actual_version"],
                recorded_deployed_at=actual_time, source="FIRST_REPORT",
                baseline_event_no=event_no,
            ))
        else:
            self.db.add(DeploymentActualCorrection(
                id=request_id, deployment_id=deployment.id, baseline_id=baseline.id,
                predecessor_id=head.id if head is not None else None,
                revision=(head.revision if head is not None else 0) + 1,
                actual_release_id=release.id, actual_snapshot_id=snapshot.id,
                correction_reason=correction_reason, actor_name=actor.name,
                actor_principal_id=actor.principal_id, request_json=request_content,
                audit_event_no=event_no,
            ))
        try:
            commit_with_audit(self.db, lambda: {
                "event_no": event_no, "event_type": "DEPLOYMENT",
                "action": "ACTUAL_CORRECTED" if is_correction else "ACTUAL_REPORTED",
                "entity_type": "DEPLOYMENT", "entity_id": deployment.id,
                "entity_ref": deployment.deployment_no, **actor.audit_fields(),
                "summary": "Actual deployed software corrected" if is_correction else "Actual deployed software reported",
                "occurred_at": actual_time,
                "payload": {"before": before, "after": after,
                    "correction_reason": correction_reason, "actor_source": actor.source,
                    "request": request_content if request_id is not None else None},
            })
        except AuditEventError as exc:
            raise ProductionError("request_id already used for different content") from exc
        return result

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
        authorization = lock_chain(
            self.db, "AUTHORIZATION", deployment.authorization_id, ProductionError
        ).authorization
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
        if not authorization:
            raise ProductionError("Production authorization not found")
        ensure_chain_active(self.db, "AUTHORIZATION", authorization.id, ProductionError)
        actual = effective_actual(self.db, deployment)
        if actual.status != "MATCH":
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
