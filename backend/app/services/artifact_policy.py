from dataclasses import dataclass
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.core import Artifact, ReleaseComponent
from app.models.policy import ArtifactDistributionRule


@dataclass
class ArtifactPolicySummary:
    artifact_total: int
    sha_complete: int
    policy_complete: int
    externally_eligible: int
    approval_required: int
    internal_only: int

    def as_dict(self):
        return {
            "artifact_total": self.artifact_total,
            "sha_complete": self.sha_complete,
            "sha_completeness": 100 if self.artifact_total == 0 else round(self.sha_complete / self.artifact_total * 100),
            "policy_complete": self.policy_complete,
            "policy_completeness": 100 if self.artifact_total == 0 else round(self.policy_complete / self.artifact_total * 100),
            "externally_eligible": self.externally_eligible,
            "approval_required": self.approval_required,
            "internal_only": self.internal_only,
        }


class ArtifactPolicyService:
    def __init__(self, db: Session):
        self.db = db

    def release_artifacts(self, release_id):
        return self.db.scalars(
            select(Artifact)
            .join(ReleaseComponent, ReleaseComponent.id == Artifact.release_component_id)
            .where(ReleaseComponent.release_id == release_id)
        ).all()

    def summarize_release(self, release_id) -> ArtifactPolicySummary:
        # EXISTS counts artifacts once even when recipient rules are duplicated.
        # These are recording/completeness indicators, not permission evaluations.
        artifact = Artifact
        def rules(decision=None):
            stmt = select(ArtifactDistributionRule.id).where(ArtifactDistributionRule.artifact_id == artifact.id)
            if decision is not None:
                stmt = stmt.where(ArtifactDistributionRule.decision == decision)
            return stmt.exists()
        internal = artifact.distribution_level == "INTERNAL_ONLY"
        def total(expression):
            return func.coalesce(func.sum(expression), 0)
        row = self.db.execute(select(func.count(),
            total(case((artifact.sha256 != '', 1), else_=0)),
            total(case((internal, 1), (rules(), 1), else_=0)),
            total(case((internal, 0), (rules('ALLOW'), 1), else_=0)),
            total(case((internal, 0), (rules('APPROVAL_REQUIRED'), 1), else_=0)),
            total(case((internal, 1), else_=0)))
            .select_from(Artifact).join(ReleaseComponent, ReleaseComponent.id == artifact.release_component_id)
            .where(ReleaseComponent.release_id == release_id)).one()
        return ArtifactPolicySummary(*row)

    def evaluate(self, artifact: Artifact, recipient_type: str, purpose: str, recipient_code: str | None = None) -> str:
        if artifact.distribution_level == "INTERNAL_ONLY":
            return "DENY"

        rules = self.db.scalars(
            select(ArtifactDistributionRule).where(
                ArtifactDistributionRule.artifact_id == artifact.id,
                ArtifactDistributionRule.recipient_type == recipient_type,
                ArtifactDistributionRule.purpose == purpose,
            )
        ).all()

        specific = [r for r in rules if r.recipient_code and r.recipient_code == recipient_code]
        generic = [r for r in rules if not r.recipient_code]
        selected = specific[0] if specific else (generic[0] if generic else None)

        if selected:
            return selected.decision
        if artifact.distribution_level == "CONTROLLED_EXTERNAL":
            return "DENY"
        return "DENY"
