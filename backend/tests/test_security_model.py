import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import Base
from app.models.core import Customer, Project, SoftwareProduct, Supplier
from app.models.security import (
    GlobalRoleAssignment,
    ProjectMembership,
    SecurityPrincipal,
    SoftwareMembership,
)
from app.security_roles import ALL_ROLES, GLOBAL_ROLES, PROJECT_ROLES, SOFTWARE_ROLES


def database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Supplier.__table__,
            Customer.__table__,
            Project.__table__,
            SoftwareProduct.__table__,
            SecurityPrincipal.__table__,
            GlobalRoleAssignment.__table__,
            SoftwareMembership.__table__,
            ProjectMembership.__table__,
        ],
    )
    return Session(engine)


def context(db):
    supplier = Supplier(code="SUP", name="Supplier")
    customer = Customer(code="CUS", name="Customer")
    db.add_all([supplier, customer])
    db.flush()
    project = Project(customer_id=customer.id, project_code="P1", name="Project")
    software = SoftwareProduct(supplier_id=supplier.id, code="SW", name="Software")
    principal = SecurityPrincipal(
        issuer="https://identity.example.com",
        subject="user-123",
        principal_type="USER",
        display_name="Release Reviewer",
        email="reviewer@example.com",
    )
    service = SecurityPrincipal(
        issuer="https://identity.example.com",
        subject="service-automation",
        principal_type="SERVICE",
        display_name="Release Automation",
    )
    db.add_all([project, software, principal, service])
    db.flush()
    return project, software, principal, service


def test_role_sets_are_disjoint_and_schema_head_is_current():
    assert not (GLOBAL_ROLES & SOFTWARE_ROLES)
    assert not (GLOBAL_ROLES & PROJECT_ROLES)
    assert not (SOFTWARE_ROLES & PROJECT_ROLES)
    assert ALL_ROLES == GLOBAL_ROLES | SOFTWARE_ROLES | PROJECT_ROLES
    assert settings.required_db_revision == "0022_acceptance_history"


def test_user_and_service_principals_accept_scoped_grants_without_credentials():
    db = database()
    project, software, principal, service = context(db)
    db.add_all(
        [
            GlobalRoleAssignment(principal_id=service.id, role="PLATFORM_ADMIN"),
            SoftwareMembership(
                principal_id=principal.id,
                software_id=software.id,
                role="SOFTWARE_MAINTAINER",
            ),
            ProjectMembership(
                principal_id=principal.id,
                project_id=project.id,
                role="RELEASE_AUTHORITY",
            ),
        ]
    )
    db.commit()

    assert db.query(SecurityPrincipal).count() == 2
    assert db.query(ProjectMembership).one().status == "ACTIVE"
    assert {column.name for column in SecurityPrincipal.__table__.columns}.isdisjoint(
        {"password", "password_hash", "access_token", "refresh_token", "client_secret"}
    )


def test_principal_subject_and_scoped_role_grants_are_unique():
    db = database()
    project, _, principal, _ = context(db)
    db.add(ProjectMembership(principal_id=principal.id, project_id=project.id, role="REVIEWER"))
    db.commit()

    db.add(
        SecurityPrincipal(
            id=uuid.uuid4(),
            issuer=principal.issuer,
            subject=principal.subject,
            principal_type="USER",
            display_name="Duplicate",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.add(ProjectMembership(principal_id=principal.id, project_id=project.id, role="REVIEWER"))
    with pytest.raises(IntegrityError):
        db.commit()
