"""Provider-neutral principals and scoped role grants."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0015_identity_roles"
down_revision = "0014_resource_links"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "security_principals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("principal_type", sa.String(20), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("issuer", "subject", name="uq_security_principal_subject"),
        sa.CheckConstraint("principal_type IN ('USER','SERVICE')", name="ck_security_principal_type"),
        sa.CheckConstraint("status IN ('ACTIVE','DISABLED')", name="ck_security_principal_status"),
    )
    op.create_index("ix_security_principals_email", "security_principals", ["email"])

    op.create_table(
        "global_role_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("security_principals.id"), nullable=False),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("principal_id", "role", name="uq_global_role_assignment"),
        sa.CheckConstraint("role IN ('PLATFORM_ADMIN','AUDITOR')", name="ck_global_role"),
    )
    op.create_index("ix_global_role_assignments_principal_id", "global_role_assignments", ["principal_id"])

    op.create_table(
        "software_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("security_principals.id"), nullable=False),
        sa.Column("software_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("software_products.id"), nullable=False),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("principal_id", "software_id", "role", name="uq_software_membership"),
        sa.CheckConstraint("role IN ('SOFTWARE_VIEWER','SOFTWARE_MAINTAINER')", name="ck_software_membership_role"),
        sa.CheckConstraint("status IN ('ACTIVE','SUSPENDED')", name="ck_software_membership_status"),
    )
    op.create_index("ix_software_memberships_principal_id", "software_memberships", ["principal_id"])
    op.create_index("ix_software_memberships_software_id", "software_memberships", ["software_id"])

    op.create_table(
        "project_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("security_principals.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("principal_id", "project_id", "role", name="uq_project_membership"),
        sa.CheckConstraint(
            "role IN ('PROJECT_VIEWER','CONTRIBUTOR','REVIEWER','RELEASE_AUTHORITY',"
            "'DISTRIBUTION_AUTHORITY','PRODUCTION_AUTHORITY','PRODUCTION_OPERATOR')",
            name="ck_project_membership_role",
        ),
        sa.CheckConstraint("status IN ('ACTIVE','SUSPENDED')", name="ck_project_membership_status"),
    )
    op.create_index("ix_project_memberships_principal_id", "project_memberships", ["principal_id"])
    op.create_index("ix_project_memberships_project_id", "project_memberships", ["project_id"])


def downgrade():
    op.drop_table("project_memberships")
    op.drop_table("software_memberships")
    op.drop_table("global_role_assignments")
    op.drop_table("security_principals")
