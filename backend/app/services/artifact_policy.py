from dataclasses import dataclass
from sqlalchemy import select
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
        artifacts = self.release_artifacts(release_id)
        artifact_ids = [a.id for a in artifacts]
        rules = self.db.scalars(
            select(ArtifactDistributionRule).where(ArtifactDistributionRule.artifact_id.in_(artifact_ids))
        ).all() if artifact_ids else []
        rules_by_artifact = {}
        for rule in rules:
            rules_by_artifact.setdefault(rule.artifact_id, []).append(rule)

        sha_complete = sum(1 for a in artifacts if bool(a.sha256))
        policy_complete = 0
        externally_eligible = 0
        approval_required = 0
        internal_only = 0

        for artifact in artifacts:
            artifact_rules = rules_by_artifact.get(artifact.id, [])
            if artifact.distribution_level == "INTERNAL_ONLY":
                internal_only += 1
                policy_complete += 1
                continue

            if artifact_rules:
                policy_complete += 1
                if any(r.decision == "ALLOW" for r in artifact_rules):
                    externally_eligible += 1
                if any(r.decision == "APPROVAL_REQUIRED" for r in artifact_rules):
                    approval_required += 1

        return ArtifactPolicySummary(
            artifact_total=len(artifacts),
            sha_complete=sha_complete,
            policy_complete=policy_complete,
            externally_eligible=externally_eligible,
            approval_required=approval_required,
            internal_only=internal_only,
        )

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
