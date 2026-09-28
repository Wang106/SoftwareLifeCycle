from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest, ReleaseDecision
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release
from app.models.distribution import DeliveryPackage, DeliveryPackageItem, Distribution, SoftwareAuthorization
from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
from app.models.snapshot_policy import SnapshotArtifactDistributionRule


class DistributionError(ValueError):
    pass


class DistributionService:
    def __init__(self, db: Session):
        self.db = db

    def _latest_release_decision(self, release_id):
        return self.db.scalars(
            select(ReleaseDecision)
            .where(ReleaseDecision.release_id == release_id)
            .order_by(ReleaseDecision.decided_at.desc())
        ).first()

    def create_delivery(
        self,
        release_id,
        package_no: str,
        revision: int,
        recipient_type: str,
        recipient_code: str,
        purpose: str,
        snapshot_artifact_ids: list,
        created_by: str | None = None,
    ):
        if not snapshot_artifact_ids:
            raise DistributionError("Delivery package must contain at least one snapshot artifact")
        if len(snapshot_artifact_ids) != len(set(snapshot_artifact_ids)):
            raise DistributionError("Delivery package contains duplicate snapshot artifacts")

        release = self.db.get(Release, release_id)
        if not release:
            raise DistributionError("Release not found")

        existing = self.db.scalars(
            select(DeliveryPackage).where(
                DeliveryPackage.package_no == package_no,
                DeliveryPackage.revision == revision,
            )
        ).first()
        if existing:
            raise DistributionError("Delivery package number and revision already exist")

        decision = self._latest_release_decision(release.id)
        if not decision or decision.decision != "RELEASE":
            raise DistributionError("Delivery requires an explicit RELEASE decision")

        snapshot = self.db.get(ReleaseSnapshot, decision.snapshot_id)
        if not snapshot or snapshot.release_id != release.id:
            raise DistributionError("Release decision snapshot mismatch")
        approval = self.db.get(ApprovalRequest, decision.approval_request_id)
        if not approval or approval.status != "APPROVED" or approval.snapshot_id != snapshot.id:
            raise DistributionError("Release decision approval is not valid for the frozen snapshot")

        package = DeliveryPackage(
            package_no=package_no,
            revision=revision,
            release_id=release.id,
            snapshot_id=snapshot.id,
            recipient_type=recipient_type,
            recipient_code=recipient_code,
            purpose=purpose,
            status="READY",
            created_by=created_by,
        )
        self.db.add(package)
        self.db.flush()

        for snapshot_artifact_id in snapshot_artifact_ids:
            artifact = self.db.get(SnapshotArtifact, snapshot_artifact_id)
            if not artifact or artifact.snapshot_id != snapshot.id:
                raise DistributionError("Delivery item is not from the approved snapshot")
            if artifact.distribution_level == "INTERNAL_ONLY":
                raise DistributionError(f"{artifact.filename} is INTERNAL_ONLY")

            rules = self.db.scalars(
                select(SnapshotArtifactDistributionRule).where(
                    SnapshotArtifactDistributionRule.snapshot_artifact_id == artifact.id,
                    SnapshotArtifactDistributionRule.recipient_type == recipient_type,
                    SnapshotArtifactDistributionRule.purpose == purpose,
                )
            ).all()
            specific = [r for r in rules if r.recipient_code == recipient_code]
            generic = [r for r in rules if r.recipient_code is None]
            rule = specific[0] if specific else (generic[0] if generic else None)
            if not rule or rule.decision == "DENY":
                raise DistributionError(f"{artifact.filename} is not eligible for this recipient/purpose")

            approval_reference = None
            if rule.decision == "APPROVAL_REQUIRED":
                approval_reference = approval.approval_no

            self.db.add(
                DeliveryPackageItem(
                    delivery_package_id=package.id,
                    snapshot_artifact_id=artifact.id,
                    policy_decision=rule.decision,
                    exception_reference=approval_reference,
                )
            )

        self.db.commit()
        self.db.refresh(package)
        return package

    def create_distribution(
        self,
        delivery_package_id,
        distribution_no: str,
        recipient_type: str,
        recipient_code: str,
    ):
        package = self.db.get(DeliveryPackage, delivery_package_id)
        if not package:
            raise DistributionError("Delivery package not found")
        if package.status not in ("READY", "APPROVED"):
            raise DistributionError("Delivery package is not distributable")
        if package.recipient_type != recipient_type or package.recipient_code != recipient_code:
            raise DistributionError("Distribution recipient does not match delivery package")
        if not self.db.scalars(
            select(DeliveryPackageItem).where(
                DeliveryPackageItem.delivery_package_id == package.id
            )
        ).first():
            raise DistributionError("Delivery package has no frozen snapshot artifacts")
        if self.db.scalars(
            select(Distribution).where(Distribution.distribution_no == distribution_no)
        ).first():
            raise DistributionError("Distribution number already exists")

        row = Distribution(
            distribution_no=distribution_no,
            delivery_package_id=package.id,
            recipient_type=recipient_type,
            recipient_code=recipient_code,
            status="READY",
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def create_authorization(
        self,
        release_id,
        distribution_id,
        authorization_no: str,
        customer_id,
        project_id,
        site_code: str,
        line_code: str,
        purpose: str = "PRODUCTION",
        batch_limit: int | None = None,
        restriction_note: str | None = None,
    ):
        release = self.db.get(Release, release_id)
        if not release:
            raise DistributionError("Release not found")
        if batch_limit is not None and batch_limit < 1:
            raise DistributionError("Authorization batch limit must be at least one")

        if self.db.scalars(
            select(SoftwareAuthorization).where(
                SoftwareAuthorization.authorization_no == authorization_no
            )
        ).first():
            raise DistributionError("Authorization number already exists")

        decision = self._latest_release_decision(release.id)
        if not decision or decision.decision != "RELEASE":
            raise DistributionError("Authorization requires an explicit RELEASE decision")

        distribution = self.db.get(Distribution, distribution_id)
        if not distribution:
            raise DistributionError("Distribution not found")
        if distribution.status not in ("READY", "SENT", "ACKNOWLEDGED"):
            raise DistributionError("Authorization requires a distributable distribution record")
        package = self.db.get(DeliveryPackage, distribution.delivery_package_id)
        if not package:
            raise DistributionError("Distribution delivery package not found")
        if package.release_id != release.id or package.snapshot_id != decision.snapshot_id:
            raise DistributionError("Distribution does not match the released snapshot")
        if package.purpose != purpose:
            raise DistributionError("Authorization purpose does not match delivery package")

        detail = self.db.get(ApplicationReleaseDetail, release.id)
        if not detail:
            raise DistributionError("Authorization requires an application release")
        if detail.customer_id != customer_id or detail.project_id != project_id:
            raise DistributionError("Authorization customer/project does not match application release")
        customer = self.db.get(Customer, customer_id)
        project = self.db.get(Project, project_id)
        if not customer or not project:
            raise DistributionError("Authorization customer or project not found")
        if (
            distribution.recipient_type != "CUSTOMER"
            or distribution.recipient_code != customer.code
            or package.recipient_type != distribution.recipient_type
            or package.recipient_code != distribution.recipient_code
        ):
            raise DistributionError("Distribution recipient does not match authorization customer")

        row = SoftwareAuthorization(
            authorization_no=authorization_no,
            distribution_id=distribution.id,
            release_id=release.id,
            snapshot_id=decision.snapshot_id,
            customer_id=customer_id,
            project_id=project_id,
            site_code=site_code,
            line_code=line_code,
            purpose=purpose,
            status="DRAFT",
            batch_limit=batch_limit,
            restriction_note=restriction_note,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
