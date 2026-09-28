from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.change import ChangePoint, Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.testing import ChangePointDvpItem, DvpExecution, DvpItem, IssueDvpItem
from app.models.core import ApplicationReleaseDetail, Release
from app.models.snapshot import ReleaseSnapshot


@dataclass
class CoverageResult:
    snapshot_id: str | None
    snapshot_no: str | None
    change_points_total: int
    change_points_covered: int
    issues_total: int
    issues_covered: int
    required_dvp_total: int
    current_snapshot_passed: int
    current_snapshot_executed: int
    snapshot_match: bool

    def as_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_no": self.snapshot_no,
            "change_points_total": self.change_points_total,
            "change_points_covered": self.change_points_covered,
            "change_coverage": 100 if self.change_points_total == 0 else round(self.change_points_covered / self.change_points_total * 100),
            "issues_total": self.issues_total,
            "issues_covered": self.issues_covered,
            "issue_verification_coverage": 100 if self.issues_total == 0 else round(self.issues_covered / self.issues_total * 100),
            "required_dvp_total": self.required_dvp_total,
            "current_snapshot_passed": self.current_snapshot_passed,
            "current_snapshot_executed": self.current_snapshot_executed,
            "dvp_execution_coverage": 100 if self.required_dvp_total == 0 else round(self.current_snapshot_executed / self.required_dvp_total * 100),
            "snapshot_match": self.snapshot_match,
        }


class TraceabilityService:
    def __init__(self, db: Session):
        self.db = db

    def _release_scr_ids(self, release: Release) -> list:
        detail = self.db.get(ApplicationReleaseDetail, release.id) if release.release_type == "APPLICATION" else None
        stmt = select(SoftwareChangeRequest.id).where(SoftwareChangeRequest.software_id == release.software_id)
        if detail is not None:
            stmt = stmt.where(
                (SoftwareChangeRequest.project_id == detail.project_id) |
                (SoftwareChangeRequest.project_id.is_(None))
            )
        return list(self.db.scalars(stmt).all())

    def release_coverage(self, release_id, snapshot_id=None) -> CoverageResult:
        release = self.db.get(Release, release_id)
        if not release:
            return CoverageResult(None, None, 0, 0, 0, 0, 0, 0, 0, False)

        if snapshot_id is not None:
            snapshot = self.db.get(ReleaseSnapshot, snapshot_id)
            if snapshot is None or snapshot.release_id != release.id:
                snapshot = None
        else:
            snapshot = self.db.scalars(
                select(ReleaseSnapshot)
                .where(ReleaseSnapshot.release_id == release.id)
                .order_by(ReleaseSnapshot.snapshot_number.desc())
            ).first()

        scr_ids = self._release_scr_ids(release)
        change_points = self.db.scalars(
            select(ChangePoint).where(ChangePoint.change_request_id.in_(scr_ids))
        ).all() if scr_ids else []
        cp_ids = [cp.id for cp in change_points]

        cp_links = self.db.execute(
            select(ChangePointDvpItem.change_point_id, ChangePointDvpItem.dvp_item_id)
            .where(ChangePointDvpItem.change_point_id.in_(cp_ids))
        ).all() if cp_ids else []
        covered_cp_ids = {row[0] for row in cp_links}
        dvp_ids = {row[1] for row in cp_links}

        issue_ids = set(self.db.scalars(
            select(IssueChangeRequestRelation.issue_id)
            .where(IssueChangeRequestRelation.change_request_id.in_(scr_ids))
        ).all()) if scr_ids else set()

        issue_links = self.db.execute(
            select(IssueDvpItem.issue_id, IssueDvpItem.dvp_item_id)
            .where(IssueDvpItem.issue_id.in_(issue_ids))
        ).all() if issue_ids else []
        covered_issue_ids = {row[0] for row in issue_links}
        dvp_ids.update(row[1] for row in issue_links)

        executions = self.db.scalars(
            select(DvpExecution).where(
                DvpExecution.release_id == release.id,
                DvpExecution.dvp_item_id.in_(list(dvp_ids))
            )
        ).all() if dvp_ids else []

        current = [
            e for e in executions
            if snapshot is not None and e.snapshot_id == snapshot.id
        ]
        current_item_ids = {e.dvp_item_id for e in current}
        current_pass_ids = {e.dvp_item_id for e in current if e.result == "PASS"}

        return CoverageResult(
            snapshot_id=str(snapshot.id) if snapshot else None,
            snapshot_no=snapshot.snapshot_no if snapshot else None,
            change_points_total=len(cp_ids),
            change_points_covered=len(covered_cp_ids),
            issues_total=len(issue_ids),
            issues_covered=len(covered_issue_ids),
            required_dvp_total=len(dvp_ids),
            current_snapshot_passed=len(current_pass_ids),
            current_snapshot_executed=len(current_item_ids),
            snapshot_match=snapshot is not None and bool(current),
        )
