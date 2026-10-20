"""Append-only Deployment actual baselines and corrections with old-writer guards."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0027_production_actual_history"
down_revision = "0026_release_chain_revocation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "deployment_actual_baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("deployments.id"), nullable=False),
        sa.Column("actual_release_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("releases.id")),
        sa.Column("actual_snapshot_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("release_snapshots.id")),
        sa.Column("recorded_status", sa.String(30), nullable=False),
        sa.Column("recorded_actual_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recorded_deployed_at", sa.DateTime(timezone=True)),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("baseline_event_no", sa.String(50)),
        sa.UniqueConstraint("deployment_id", name="uq_deployment_actual_baseline_target"),
        sa.CheckConstraint(
            "source IN ('LEGACY_CURRENT','IMPORTED_CURRENT','FIRST_REPORT')",
            name="ck_deployment_actual_baseline_source"),
        sa.CheckConstraint("recorded_actual_version >= 0",
                           name="ck_deployment_actual_baseline_version"),
        sa.CheckConstraint("(actual_release_id IS NULL) = (actual_snapshot_id IS NULL)",
                           name="ck_deployment_actual_baseline_pair"),
    )

    op.create_table(
        "deployment_actual_corrections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("deployments.id"), nullable=False),
        sa.Column("baseline_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("deployment_actual_baselines.id"), nullable=False),
        sa.Column("predecessor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("actual_release_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("releases.id")),
        sa.Column("actual_snapshot_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("release_snapshots.id")),
        sa.Column("correction_reason", sa.Text(), nullable=False),
        sa.Column("actor_name", sa.String(120), nullable=False),
        sa.Column("actor_principal_id", postgresql.UUID(as_uuid=True)),
        sa.Column("request_json", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("audit_event_no", sa.String(50), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("deployment_id", "revision",
                            name="uq_deployment_actual_corr_revision"),
        sa.UniqueConstraint("baseline_id", "revision",
                            name="uq_deployment_actual_corr_baseline_revision"),
        sa.UniqueConstraint("deployment_id", "id",
                            name="uq_deployment_actual_corr_target_id"),
        sa.CheckConstraint("revision >= 1",
                           name="ck_deployment_actual_corr_revision_positive"),
        sa.CheckConstraint("(actual_release_id IS NULL) = (actual_snapshot_id IS NULL)",
                           name="ck_deployment_actual_corr_pair"),
        sa.CheckConstraint("length(btrim(correction_reason)) BETWEEN 1 AND 2000",
                           name="ck_deployment_actual_corr_reason"),
        sa.ForeignKeyConstraint(
            ["deployment_id", "predecessor_id"],
            ["deployment_actual_corrections.deployment_id",
             "deployment_actual_corrections.id"],
            name="fk_deployment_actual_corr_predecessor"),
    )
    op.create_index("ix_deployment_actual_corr_target_revision",
                    "deployment_actual_corrections", ["deployment_id", "revision"])
    op.create_index("ux_deployment_actual_corr_single_successor",
                    "deployment_actual_corrections", ["predecessor_id"],
                    unique=True, postgresql_where=sa.text("predecessor_id IS NOT NULL"))

    # Append-only: no UPDATE/DELETE on baselines or corrections.
    op.execute("""
    CREATE FUNCTION reject_production_history_mutation() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'Production actual history is append-only'
        USING ERRCODE = '55000';
    END $$;

    CREATE TRIGGER deployment_actual_baselines_append_only
      BEFORE UPDATE OR DELETE ON deployment_actual_baselines
      FOR EACH ROW EXECUTE FUNCTION reject_production_history_mutation();

    CREATE TRIGGER deployment_actual_corrections_append_only
      BEFORE UPDATE OR DELETE ON deployment_actual_corrections
      FOR EACH ROW EXECUTE FUNCTION reject_production_history_mutation();
    """)

    # Capture legacy current values as LEGACY_CURRENT baselines for every
    # already-reported Deployment. Unreported rows get no baseline.
    op.execute("""
    INSERT INTO deployment_actual_baselines
      (id, deployment_id, actual_release_id, actual_snapshot_id, recorded_status,
       recorded_actual_version, recorded_deployed_at, source, recorded_at)
    SELECT gen_random_uuid(), id, actual_release_id, actual_snapshot_id, status,
           actual_version, deployed_at, 'LEGACY_CURRENT', now()
      FROM deployments
     WHERE actual_release_id IS NOT NULL AND actual_snapshot_id IS NOT NULL
    """)


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM deployment_actual_corrections) THEN
        RAISE EXCEPTION 'Cannot downgrade: production actual corrections would be lost';
      END IF;
      IF EXISTS (SELECT 1 FROM deployment_actual_baselines b
                 WHERE b.source = 'FIRST_REPORT') THEN
        RAISE EXCEPTION 'Cannot downgrade: first-report history would be lost';
      END IF;
    END $$""")
    op.execute("DROP TRIGGER deployment_actual_corrections_append_only ON deployment_actual_corrections")
    op.execute("DROP TRIGGER deployment_actual_baselines_append_only ON deployment_actual_baselines")
    op.execute("DROP FUNCTION reject_production_history_mutation()")
    op.drop_table("deployment_actual_corrections")
    op.drop_table("deployment_actual_baselines")
