from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import case, func, literal, select, union
from sqlalchemy.orm import Session

from app.models.change import ChangePoint, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.testing import ChangePointDvpItem, DvpExecution, IssueDvpItem
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

    def _release_scr_query(self, release: Release):
        detail = self.db.get(ApplicationReleaseDetail, release.id) if release.release_type == "APPLICATION" else None
        stmt = select(SoftwareChangeRequest.id).where(SoftwareChangeRequest.software_id == release.software_id)
        if detail is not None:
            stmt = stmt.where(
                (SoftwareChangeRequest.project_id == detail.project_id) |
                (SoftwareChangeRequest.project_id.is_(None))
            )
        return stmt

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
                .limit(1)
            ).first()

        # Keep scopes relational: neither growing ID arrays nor child ORM rows
        # cross the database boundary. UNION preserves the previous set semantics,
        # including recorded bindings whose metadata is absent in legacy data.
        scrs = self._release_scr_query(release).cte("coverage_scrs")
        change_points = select(ChangePoint.id).where(
            ChangePoint.change_request_id.in_(select(scrs.c.id))
        ).cte("coverage_change_points")
        cp_links = select(
            ChangePointDvpItem.change_point_id, ChangePointDvpItem.dvp_item_id
        ).where(ChangePointDvpItem.change_point_id.in_(select(change_points.c.id))).cte("coverage_cp_links")
        issues = select(IssueChangeRequestRelation.issue_id).where(
            IssueChangeRequestRelation.change_request_id.in_(select(scrs.c.id))
        ).distinct().cte("coverage_issues")
        issue_links = select(IssueDvpItem.issue_id, IssueDvpItem.dvp_item_id).where(
            IssueDvpItem.issue_id.in_(select(issues.c.issue_id))
        ).cte("coverage_issue_links")
        required = union(
            select(cp_links.c.dvp_item_id), select(issue_links.c.dvp_item_id)
        ).cte("coverage_required")

        def count_rows(scope):
            return select(func.count()).select_from(scope).scalar_subquery()

        def count_distinct(column):
            return select(func.count(func.distinct(column))).scalar_subquery()

        counts = [
            count_rows(change_points), count_distinct(cp_links.c.change_point_id),
            count_rows(issues), count_distinct(issue_links.c.issue_id), count_rows(required),
        ]
        if snapshot is not None:
            current = select(
                func.count(func.distinct(DvpExecution.dvp_item_id)).label("executed"),
                func.count(func.distinct(case(
                    (DvpExecution.result == "PASS", DvpExecution.dvp_item_id),
                    else_=None,
                ))).label("passed"),
            ).where(
                DvpExecution.release_id == release.id,
                DvpExecution.snapshot_id == snapshot.id,
                DvpExecution.dvp_item_id.in_(select(required.c.dvp_item_id)),
            ).subquery()
            counts.extend([current.c.executed, current.c.passed])
        else:
            counts.extend([literal(0), literal(0)])
        cp_total, cp_covered, issue_total, issue_covered, required_total, executed, passed = (
            self.db.execute(select(*counts)).one()
        )

        return CoverageResult(
            snapshot_id=str(snapshot.id) if snapshot else None,
            snapshot_no=snapshot.snapshot_no if snapshot else None,
            change_points_total=cp_total,
            change_points_covered=cp_covered,
            issues_total=issue_total,
            issues_covered=issue_covered,
            required_dvp_total=required_total,
            current_snapshot_passed=passed,
            current_snapshot_executed=executed,
            snapshot_match=snapshot is not None and bool(executed),
        )
