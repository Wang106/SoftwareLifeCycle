"""Permanent release-chain revocation ledger and old-writer guards."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0026_release_chain_revocation"
down_revision = "0025_release_decision_supersession"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "release_chain_revocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("revocation_no", sa.String(50), nullable=False, unique=True),
        sa.Column("target_kind", sa.String(30), nullable=False),
        sa.Column("release_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("releases.id")),
        sa.Column("delivery_package_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("delivery_packages.id")),
        sa.Column("distribution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("distributions.id")),
        sa.Column("authorization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("software_authorizations.id")),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("release_snapshots.id"), nullable=False),
        sa.Column("release_decision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("release_decisions.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("revoked_by", sa.String(120), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("target_kind IN ('RELEASE','DELIVERY_PACKAGE','DISTRIBUTION','AUTHORIZATION')", name="ck_release_chain_revocation_kind"),
        sa.CheckConstraint("num_nonnulls(release_id, delivery_package_id, distribution_id, authorization_id) = 1", name="ck_release_chain_revocation_one_target"),
        sa.CheckConstraint("length(btrim(reason)) BETWEEN 1 AND 4000", name="ck_release_chain_revocation_reason"),
    )
    op.create_index("uq_revoked_release", "release_chain_revocations", ["release_id"], unique=True,
                    postgresql_where=sa.text("release_id IS NOT NULL"))
    op.create_index("uq_revoked_delivery", "release_chain_revocations", ["delivery_package_id"], unique=True,
                    postgresql_where=sa.text("delivery_package_id IS NOT NULL"))
    op.create_index("uq_revoked_distribution", "release_chain_revocations", ["distribution_id"], unique=True,
                    postgresql_where=sa.text("distribution_id IS NOT NULL"))
    op.create_index("uq_revoked_authorization", "release_chain_revocations", ["authorization_id"], unique=True,
                    postgresql_where=sa.text("authorization_id IS NOT NULL"))
    op.execute("""
    CREATE FUNCTION reject_release_chain_revocation_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'Release-chain revocations are append-only' USING ERRCODE = '55000';
    END $$;
    CREATE TRIGGER release_chain_revocations_append_only
      BEFORE UPDATE OR DELETE ON release_chain_revocations
      FOR EACH ROW EXECUTE FUNCTION reject_release_chain_revocation_mutation();

    CREATE FUNCTION reject_revoked_chain_insert() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE v_release uuid; v_package uuid; v_distribution uuid; v_authorization uuid;
    BEGIN
      IF TG_TABLE_NAME = 'release_decisions' THEN v_release := NEW.release_id;
      ELSIF TG_TABLE_NAME = 'delivery_packages' THEN v_release := NEW.release_id;
      ELSIF TG_TABLE_NAME = 'distributions' THEN v_package := NEW.delivery_package_id;
      ELSIF TG_TABLE_NAME = 'software_authorizations' THEN
        v_release := NEW.release_id; v_distribution := NEW.distribution_id;
      ELSIF TG_TABLE_NAME = 'deployments' THEN v_authorization := NEW.authorization_id;
      ELSIF TG_TABLE_NAME = 'production_batches' THEN v_authorization := NEW.authorization_id;
      END IF;
      IF v_authorization IS NOT NULL THEN
        SELECT a.distribution_id, a.release_id INTO v_distribution, v_release
          FROM software_authorizations a WHERE a.id=v_authorization;
      END IF;
      IF v_distribution IS NOT NULL THEN
        SELECT d.delivery_package_id INTO v_package FROM distributions d WHERE d.id=v_distribution;
      END IF;
      IF v_package IS NOT NULL THEN
        SELECT p.release_id INTO v_release FROM delivery_packages p WHERE p.id=v_package;
      END IF;
      IF EXISTS (SELECT 1 FROM release_chain_revocations r WHERE
          r.release_id=v_release OR r.delivery_package_id=v_package OR
          r.distribution_id=v_distribution OR r.authorization_id=v_authorization) THEN
        RAISE EXCEPTION 'Release chain is revoked; new permission-bearing records are forbidden'
          USING ERRCODE = '55000';
      END IF;
      RETURN NEW;
    END $$;
    """)
    for table in ("release_decisions", "delivery_packages", "distributions",
                  "software_authorizations", "deployments", "production_batches"):
        op.execute(f"CREATE TRIGGER {table}_revocation_insert_guard BEFORE INSERT ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION reject_revoked_chain_insert()")


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM release_chain_revocations) THEN
        RAISE EXCEPTION 'Cannot downgrade: release-chain revocation history would be lost';
      END IF;
    END $$""")
    for table in ("release_decisions", "delivery_packages", "distributions",
                  "software_authorizations", "deployments", "production_batches"):
        op.execute(f"DROP TRIGGER {table}_revocation_insert_guard ON {table}")
    op.execute("DROP FUNCTION reject_revoked_chain_insert()")
    op.execute("DROP TRIGGER release_chain_revocations_append_only ON release_chain_revocations")
    op.execute("DROP FUNCTION reject_release_chain_revocation_mutation()")
    op.drop_table("release_chain_revocations")
