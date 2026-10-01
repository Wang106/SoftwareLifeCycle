import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from app import authorization
from app.auth import AuthenticatedPrincipal
from app.authorization import AuthorizationError
from app.core.db import Base
from app.models.change import Issue, IssueChangeRequestRelation, SoftwareChangeRequest
from app.models.core import (
    ApplicationReleaseDetail,
    Customer,
    Project,
    Release,
    SoftwareProduct,
    Supplier,
)
from app.models.security import (
    GlobalRoleAssignment,
    ProjectMembership,
    SecurityPrincipal,
    SoftwareMembership,
)


TABLES = [
    Supplier.__table__,
    Customer.__table__,
    Project.__table__,
    SoftwareProduct.__table__,
    Release.__table__,
    ApplicationReleaseDetail.__table__,
    Issue.__table__,
    SoftwareChangeRequest.__table__,
    IssueChangeRequestRelation.__table__,
    SecurityPrincipal.__table__,
    GlobalRoleAssignment.__table__,
    SoftwareMembership.__table__,
    ProjectMembership.__table__,
]


def database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=TABLES)
    return Session(engine)


def context(db):
    supplier = Supplier(code="SUP", name="Supplier")
    customer = Customer(code="CUS", name="Customer")
    db.add_all([supplier, customer])
    db.flush()
    project = Project(customer_id=customer.id, project_code="P1", name="Project 1")
    other_project = Project(customer_id=customer.id, project_code="P2", name="Project 2")
    software = SoftwareProduct(supplier_id=supplier.id, code="SW1", name="Software 1")
    other_software = SoftwareProduct(supplier_id=supplier.id, code="SW2", name="Software 2")
    principal = SecurityPrincipal(
        issuer="https://identity.example.com",
        subject="user-123",
        principal_type="USER",
        display_name="Scoped User",
    )
    db.add_all([project, other_project, software, other_software, principal])
    db.flush()
    standard = Release(software_id=software.id, release_type="STANDARD", version="1.0")
    other_standard = Release(
        software_id=other_software.id, release_type="STANDARD", version="2.0"
    )
    application = Release(software_id=software.id, release_type="APPLICATION", version="1.0-P1")
    other_application = Release(
        software_id=software.id, release_type="APPLICATION", version="1.0-P2"
    )
    db.add_all([standard, other_standard, application, other_application])
    db.flush()
    db.add_all(
        [
            ApplicationReleaseDetail(
                release_id=application.id,
                customer_id=customer.id,
                project_id=project.id,
                standard_base_release_id=standard.id,
            ),
            ApplicationReleaseDetail(
                release_id=other_application.id,
                customer_id=customer.id,
                project_id=other_project.id,
                standard_base_release_id=standard.id,
            ),
        ]
    )
    db.commit()
    return {
        "project": project,
        "other_project": other_project,
        "software": software,
        "standard": standard,
        "other_standard": other_standard,
        "application": application,
        "other_application": other_application,
        "principal": principal,
    }


def authenticated_request(principal):
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
    request.state.principal = AuthenticatedPrincipal(
        id=principal.id,
        issuer=principal.issuer,
        subject=principal.subject,
        principal_type=principal.principal_type,
        display_name=principal.display_name,
        email=principal.email,
    )
    return request


def enable_oidc(monkeypatch):
    monkeypatch.setattr(authorization.settings, "auth_mode", "oidc")


def test_disabled_mode_preserves_controlled_local_writes(monkeypatch):
    db = database()
    values = context(db)
    monkeypatch.setattr(authorization.settings, "auth_mode", "disabled")
    authorization.authorize_release(
        None,
        db,
        values["application"].id,
        project_roles=frozenset({"CONTRIBUTOR"}),
    )


def test_project_role_is_exact_active_and_role_specific(monkeypatch):
    db = database()
    values = context(db)
    db.add(
        ProjectMembership(
            principal_id=values["principal"].id,
            project_id=values["project"].id,
            role="CONTRIBUTOR",
        )
    )
    db.commit()
    enable_oidc(monkeypatch)
    request = authenticated_request(values["principal"])

    authorization.authorize_release(
        request,
        db,
        values["application"].id,
        project_roles=frozenset({"CONTRIBUTOR"}),
    )
    with pytest.raises(AuthorizationError, match="insufficient_scope"):
        authorization.authorize_release(
            request,
            db,
            values["other_application"].id,
            project_roles=frozenset({"CONTRIBUTOR"}),
        )
    with pytest.raises(AuthorizationError, match="insufficient_scope"):
        authorization.authorize_release(
            request,
            db,
            values["application"].id,
            project_roles=frozenset({"REVIEWER"}),
        )

    membership = db.query(ProjectMembership).one()
    membership.status = "SUSPENDED"
    db.commit()
    with pytest.raises(AuthorizationError, match="insufficient_scope"):
        authorization.authorize_release(
            request,
            db,
            values["application"].id,
            project_roles=frozenset({"CONTRIBUTOR"}),
        )


def test_software_role_is_exact_and_does_not_grant_another_product(monkeypatch):
    db = database()
    values = context(db)
    db.add(
        SoftwareMembership(
            principal_id=values["principal"].id,
            software_id=values["software"].id,
            role="SOFTWARE_MAINTAINER",
        )
    )
    db.commit()
    enable_oidc(monkeypatch)
    request = authenticated_request(values["principal"])

    authorization.authorize_release(
        request,
        db,
        values["standard"].id,
        project_roles=frozenset({"CONTRIBUTOR"}),
        software_roles=frozenset({"SOFTWARE_MAINTAINER"}),
    )
    with pytest.raises(AuthorizationError, match="insufficient_scope"):
        authorization.authorize_release(
            request,
            db,
            values["other_standard"].id,
            project_roles=frozenset({"CONTRIBUTOR"}),
            software_roles=frozenset({"SOFTWARE_MAINTAINER"}),
        )


def test_platform_admin_is_the_only_scope_free_override(monkeypatch):
    db = database()
    values = context(db)
    db.add(
        GlobalRoleAssignment(principal_id=values["principal"].id, role="PLATFORM_ADMIN")
    )
    db.commit()
    enable_oidc(monkeypatch)
    authorization.authorize_release(
        authenticated_request(values["principal"]),
        db,
        uuid.uuid4(),
        project_roles=frozenset({"RELEASE_AUTHORITY"}),
    )


def test_issue_review_requires_reviewer_on_linked_release_project(monkeypatch):
    db = database()
    values = context(db)
    issue = Issue(issue_no="ISS-1", title="Issue", scope="PROJECT", severity="HIGH")
    change = SoftwareChangeRequest(
        request_no="SCR-1",
        title="Change",
        source="CUSTOMER",
        scope="PROJECT",
        change_type="FIX",
        software_id=values["software"].id,
        project_id=values["project"].id,
    )
    db.add_all([issue, change])
    db.flush()
    db.add(IssueChangeRequestRelation(issue_id=issue.id, change_request_id=change.id, relation_type="FIXES"))
    db.add(
        ProjectMembership(
            principal_id=values["principal"].id,
            project_id=values["project"].id,
            role="REVIEWER",
        )
    )
    db.commit()
    enable_oidc(monkeypatch)
    request = authenticated_request(values["principal"])

    authorization.authorize_issue_assessment(
        request, db, issue.issue_no, values["application"].id
    )
    with pytest.raises(AuthorizationError, match="insufficient_scope"):
        authorization.authorize_issue_assessment(
            request, db, issue.issue_no, values["other_application"].id
        )
