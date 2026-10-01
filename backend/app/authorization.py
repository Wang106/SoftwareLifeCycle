"""Fail-closed scoped authorization for authenticated write requests."""

from collections.abc import Iterable
import uuid

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import AuthenticatedPrincipal
from app.core.config import settings
from app.models.approval import ApprovalRequest
from app.models.change import Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.core import ApplicationReleaseDetail, Release
from app.models.distribution import DeliveryPackage, Distribution, SoftwareAuthorization
from app.models.production import Deployment
from app.models.security import GlobalRoleAssignment, ProjectMembership, SoftwareMembership
from app.models.snapshot import ReleaseSnapshot
from app.models.testing import DvpExecution, DvpItem, DvpPlan, TestRelease


class AuthorizationError(ValueError):
    pass


def _principal(request: Request | None) -> AuthenticatedPrincipal | None:
    if settings.auth_mode != "oidc":
        return None
    principal = getattr(request.state, "principal", None) if request is not None else None
    if not isinstance(principal, AuthenticatedPrincipal):
        raise AuthorizationError("authenticated_principal_required")
    return principal


def _has_global_admin(db: Session, principal_id: uuid.UUID) -> bool:
    return db.scalar(
        select(GlobalRoleAssignment.id).where(
            GlobalRoleAssignment.principal_id == principal_id,
            GlobalRoleAssignment.role == "PLATFORM_ADMIN",
        ).limit(1)
    ) is not None


def _has_project_role(
    db: Session,
    principal_id: uuid.UUID,
    project_id: uuid.UUID,
    roles: frozenset[str],
) -> bool:
    if not roles:
        return False
    return db.scalar(
        select(ProjectMembership.id).where(
            ProjectMembership.principal_id == principal_id,
            ProjectMembership.project_id == project_id,
            ProjectMembership.role.in_(roles),
            ProjectMembership.status == "ACTIVE",
        ).limit(1)
    ) is not None


def _has_software_role(
    db: Session,
    principal_id: uuid.UUID,
    software_id: uuid.UUID,
    roles: frozenset[str],
) -> bool:
    if not roles:
        return False
    return db.scalar(
        select(SoftwareMembership.id).where(
            SoftwareMembership.principal_id == principal_id,
            SoftwareMembership.software_id == software_id,
            SoftwareMembership.role.in_(roles),
            SoftwareMembership.status == "ACTIVE",
        ).limit(1)
    ) is not None


def _require_any_scope(
    request: Request | None,
    db: Session,
    *,
    project_ids: Iterable[uuid.UUID] = (),
    project_roles: frozenset[str] = frozenset(),
    software_ids: Iterable[uuid.UUID] = (),
    software_roles: frozenset[str] = frozenset(),
) -> None:
    principal = _principal(request)
    if principal is None or _has_global_admin(db, principal.id):
        return
    if any(_has_project_role(db, principal.id, value, project_roles) for value in set(project_ids)):
        return
    if any(_has_software_role(db, principal.id, value, software_roles) for value in set(software_ids)):
        return
    raise AuthorizationError("insufficient_scope")


def _require_all_projects(
    request: Request | None,
    db: Session,
    project_ids: Iterable[uuid.UUID],
    roles: frozenset[str],
) -> None:
    principal = _principal(request)
    if principal is None or _has_global_admin(db, principal.id):
        return
    scopes = set(project_ids)
    if scopes and all(_has_project_role(db, principal.id, value, roles) for value in scopes):
        return
    raise AuthorizationError("insufficient_scope")


def _release_scope(db: Session, release_id: uuid.UUID):
    release = db.get(Release, release_id)
    if release is None:
        return None, None
    detail = db.get(ApplicationReleaseDetail, release.id)
    return release.software_id, detail.project_id if detail else None


def authorize_release(
    request: Request | None,
    db: Session,
    release_id: uuid.UUID,
    *,
    project_roles: frozenset[str],
    software_roles: frozenset[str] = frozenset(),
) -> None:
    software_id, project_id = _release_scope(db, release_id)
    _require_any_scope(
        request,
        db,
        project_ids=([project_id] if project_id else []),
        project_roles=project_roles,
        software_ids=([software_id] if software_id else []),
        software_roles=software_roles,
    )


def authorize_project(
    request: Request | None,
    db: Session,
    project_id: uuid.UUID,
    role: str,
) -> None:
    _require_any_scope(request, db, project_ids=[project_id], project_roles=frozenset({role}))


def authorize_change(
    request: Request | None,
    db: Session,
    request_no: str,
    role: str,
) -> None:
    change = db.scalars(
        select(SoftwareChangeRequest).where(SoftwareChangeRequest.request_no == request_no)
    ).first()
    _require_any_scope(
        request,
        db,
        project_ids=([change.project_id] if change and change.project_id else []),
        project_roles=frozenset({role}),
    )


def authorize_approval(
    request: Request | None,
    db: Session,
    approval_no: str,
    role: str,
) -> None:
    approval = db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.approval_no == approval_no)
    ).first()
    if approval and approval.target_type == "RELEASE":
        authorize_release(
            request,
            db,
            approval.target_id,
            project_roles=frozenset({role}),
        )
        return
    if approval and approval.target_type == "SCR":
        change = db.get(SoftwareChangeRequest, approval.target_id)
        _require_any_scope(
            request,
            db,
            project_ids=([change.project_id] if change and change.project_id else []),
            project_roles=frozenset({role}),
        )
        return
    _require_any_scope(request, db)


def authorize_delivery_package(
    request: Request | None,
    db: Session,
    package_id: uuid.UUID,
    role: str,
) -> None:
    package = db.get(DeliveryPackage, package_id)
    authorize_release(
        request,
        db,
        package.release_id if package else uuid.UUID(int=0),
        project_roles=frozenset({role}),
    )


def authorize_distribution(
    request: Request | None,
    db: Session,
    distribution_id: uuid.UUID,
    role: str,
) -> None:
    distribution = db.get(Distribution, distribution_id)
    authorize_delivery_package(
        request,
        db,
        distribution.delivery_package_id if distribution else uuid.UUID(int=0),
        role,
    )


def authorize_authorization(
    request: Request | None,
    db: Session,
    authorization_id: uuid.UUID,
    role: str,
) -> None:
    authorization = db.get(SoftwareAuthorization, authorization_id)
    _require_any_scope(
        request,
        db,
        project_ids=([authorization.project_id] if authorization else []),
        project_roles=frozenset({role}),
    )


def authorize_deployment(
    request: Request | None,
    db: Session,
    deployment_no: str,
    role: str,
) -> None:
    deployment = db.scalars(
        select(Deployment).where(Deployment.deployment_no == deployment_no)
    ).first()
    authorize_authorization(
        request,
        db,
        deployment.authorization_id if deployment else uuid.UUID(int=0),
        role,
    )


def authorize_issue_assessment(
    request: Request | None,
    db: Session,
    issue_no: str,
    release_id: uuid.UUID,
) -> None:
    principal = _principal(request)
    if principal is None or _has_global_admin(db, principal.id):
        return
    _, project_id = _release_scope(db, release_id)
    issue = db.scalars(select(Issue).where(Issue.issue_no == issue_no)).first()
    linked_projects = set(db.scalars(
        select(SoftwareChangeRequest.project_id)
        .join(
            IssueChangeRequestRelation,
            IssueChangeRequestRelation.change_request_id == SoftwareChangeRequest.id,
        )
        .where(
            IssueChangeRequestRelation.issue_id == (issue.id if issue else uuid.UUID(int=0)),
            SoftwareChangeRequest.project_id.is_not(None),
        )
    ).all())
    if (
        project_id is not None
        and project_id in linked_projects
        and _has_project_role(db, principal.id, project_id, frozenset({"REVIEWER"}))
    ):
        return
    raise AuthorizationError("insufficient_scope")


def authorize_resource(
    request: Request | None,
    db: Session,
    entity_type: str,
    entity_id: uuid.UUID,
) -> None:
    role = frozenset({"CONTRIBUTOR"})
    if entity_type == "PROJECT":
        _require_any_scope(request, db, project_ids=[entity_id], project_roles=role)
        return
    if entity_type == "RELEASE":
        authorize_release(request, db, entity_id, project_roles=role)
        return
    if entity_type == "SNAPSHOT":
        snapshot = db.get(ReleaseSnapshot, entity_id)
        authorize_release(
            request, db, snapshot.release_id if snapshot else uuid.UUID(int=0), project_roles=role
        )
        return
    if entity_type == "SCR":
        change = db.get(SoftwareChangeRequest, entity_id)
        _require_any_scope(
            request,
            db,
            project_ids=([change.project_id] if change and change.project_id else []),
            project_roles=role,
        )
        return
    if entity_type == "DVP_ITEM":
        item = db.get(DvpItem, entity_id)
        plan = db.get(DvpPlan, item.plan_id) if item else None
        change = db.get(SoftwareChangeRequest, plan.change_request_id) if plan else None
        _require_any_scope(
            request,
            db,
            project_ids=([change.project_id] if change and change.project_id else []),
            project_roles=role,
        )
        return
    if entity_type == "TEST_RELEASE":
        test_release = db.get(TestRelease, entity_id)
        authorize_release(
            request,
            db,
            test_release.release_id if test_release else uuid.UUID(int=0),
            project_roles=role,
        )
        return
    if entity_type == "DVP_EXECUTION":
        execution = db.get(DvpExecution, entity_id)
        authorize_release(
            request,
            db,
            execution.release_id if execution else uuid.UUID(int=0),
            project_roles=role,
        )
        return
    if entity_type == "ISSUE":
        issue = db.get(Issue, entity_id)
        project_ids = db.scalars(
            select(SoftwareChangeRequest.project_id)
            .join(
                IssueChangeRequestRelation,
                IssueChangeRequestRelation.change_request_id == SoftwareChangeRequest.id,
            )
            .where(
                IssueChangeRequestRelation.issue_id == (issue.id if issue else uuid.UUID(int=0)),
                SoftwareChangeRequest.project_id.is_not(None),
            )
        ).all()
        _require_all_projects(request, db, project_ids, role)
        return
    # Supplier and customer records do not carry an authoritative project/software scope.
    _require_any_scope(request, db)
