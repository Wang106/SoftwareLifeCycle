from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.change import ChangePoint, SoftwareChangeRequest
from app.models.testing import ChangePointDvpItem, DvpExecution, DvpItem, IssueDvpItem
from app.models.core import Release


@dataclass
class CoverageResult:
    change_points_total: int
    change_points_covered: int
    issues_total: int
    issues_covered: int
    required_dvp_total: int
    current_snapshot_passed: int
    snapshot_match: bool

    def as_dict(self) -> dict:
        return {
            "change_points_total": self.change_points_total,
            "change_points_covered": self.change_points_covered,
            "change_coverage": 100 if self.change_points_total == 0 else round(self.change_points_covered / self.change_points_total * 100),
            "issues_total": self.issues_total,
            "issues_covered": self.issues_covered,
            "issue_verification_coverage": 100 if self.issues_total == 0 else round(self.issues_covered / self.issues_total * 100),
            "required_dvp_total": self.required_dvp_total,
            "current_snapshot_passed": self.current_snapshot_passed,
            "snapshot_match": self.snapshot_match,
        }


class TraceabilityService:
    def __init__(self, db: Session):
        self.db = db

    def release_coverage(self, release_id):
        release = self.db.get(Release, release_id)
        if not release:
            return CoverageResult(0, 0, 0, 0, 0, 0, False)

        change_points = self.db.scalars(select(ChangePoint)).all()
        cp_ids = [cp.id for cp in change_points]
        covered_cp_ids = set(
            self.db.scalars(
                select(ChangePointDvpItem.change_point_id).where(ChangePointDvpItem.change_point_id.in_(cp_ids))
            ).all()
        ) if cp_ids else set()

        issue_links = self.db.scalars(select(IssueDvpItem.issue_id)).all()
        issue_ids = set(issue_links)

        dvp_items = self.db.scalars(select(DvpItem)).all()
        dvp_ids = [item.id for item in dvp_items]
        executions = self.db.scalars(
            select(DvpExecution).where(DvpExecution.dvp_item_id.in_(dvp_ids))
        ).all() if dvp_ids else []

        current_snapshot_passed = sum(
            1 for execution in executions
            if getattr(execution, "result", None) == "PASS"
            and getattr(execution, "release_id", None) == release.id
            and getattr(execution, "snapshot_id", None) is not None
        )

        snapshot_match = any(
            getattr(execution, "release_id", None) == release.id
            and getattr(execution, "snapshot_id", None) is not None
            for execution in executions
        )

        return CoverageResult(
            change_points_total=len(cp_ids),
            change_points_covered=len(covered_cp_ids),
            issues_total=len(issue_ids),
            issues_covered=len(issue_ids),
            required_dvp_total=len(dvp_ids),
            current_snapshot_passed=current_snapshot_passed,
            snapshot_match=snapshot_match,
        )
