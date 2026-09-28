"""delivery distribution and authorization"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="0007_distribution_authorization"
down_revision="0006_approval_release_decision"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table(
        "delivery_packages",
        sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),
        sa.Column("package_no",sa.String(50),nullable=False),
        sa.Column("revision",sa.Integer(),nullable=False),
        sa.Column("release_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("releases.id"),nullable=False),
        sa.Column("snapshot_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("release_snapshots.id"),nullable=False),
        sa.Column("recipient_type",sa.String(50),nullable=False),
        sa.Column("recipient_code",sa.String(80),nullable=False),
        sa.Column("purpose",sa.String(50),nullable=False),
        sa.Column("status",sa.String(30),nullable=False),
        sa.Column("created_by",sa.String(120)),
        sa.Column("created_at",sa.DateTime(timezone=True)),
        sa.UniqueConstraint("package_no","revision",name="uq_delivery_package_revision"),
    )
    op.create_index("ix_delivery_packages_release_id","delivery_packages",["release_id"])
    op.create_table(
        "delivery_package_items",
        sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),
        sa.Column("delivery_package_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("delivery_packages.id"),nullable=False),
        sa.Column("snapshot_artifact_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("snapshot_artifacts.id"),nullable=False),
        sa.Column("policy_decision",sa.String(30),nullable=False),
        sa.Column("exception_reference",sa.String(80)),
        sa.UniqueConstraint("delivery_package_id","snapshot_artifact_id",name="uq_delivery_package_item"),
    )
    op.create_index("ix_delivery_package_items_package_id","delivery_package_items",["delivery_package_id"])
    op.create_table(
        "distributions",
        sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),
        sa.Column("distribution_no",sa.String(50),nullable=False,unique=True),
        sa.Column("delivery_package_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("delivery_packages.id"),nullable=False),
        sa.Column("recipient_type",sa.String(50),nullable=False),
        sa.Column("recipient_code",sa.String(80),nullable=False),
        sa.Column("status",sa.String(30),nullable=False),
        sa.Column("sent_at",sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at",sa.DateTime(timezone=True)),
        sa.Column("note",sa.Text()),
    )
    op.create_index("ix_distributions_package_id","distributions",["delivery_package_id"])
    op.create_table(
        "software_authorizations",
        sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),
        sa.Column("authorization_no",sa.String(50),nullable=False,unique=True),
        sa.Column("release_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("releases.id"),nullable=False),
        sa.Column("snapshot_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("release_snapshots.id"),nullable=False),
        sa.Column("customer_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("customers.id"),nullable=False),
        sa.Column("project_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("projects.id"),nullable=False),
        sa.Column("site_code",sa.String(80),nullable=False),
        sa.Column("line_code",sa.String(80),nullable=False),
        sa.Column("purpose",sa.String(50),nullable=False),
        sa.Column("status",sa.String(30),nullable=False),
        sa.Column("restriction_note",sa.Text()),
        sa.Column("approved_at",sa.DateTime(timezone=True)),
    )
    op.create_index("ix_software_authorizations_release_id","software_authorizations",["release_id"])

def downgrade():
    op.drop_index("ix_software_authorizations_release_id",table_name="software_authorizations")
    op.drop_table("software_authorizations")
    op.drop_index("ix_distributions_package_id",table_name="distributions")
    op.drop_table("distributions")
    op.drop_index("ix_delivery_package_items_package_id",table_name="delivery_package_items")
    op.drop_table("delivery_package_items")
    op.drop_index("ix_delivery_packages_release_id",table_name="delivery_packages")
    op.drop_table("delivery_packages")
