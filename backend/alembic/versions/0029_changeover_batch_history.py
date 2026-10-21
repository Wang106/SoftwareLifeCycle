"""Append-only Changeover and Batch history baselines and corrections.

Adds two immutable baseline tables and two typed correction ledgers for
SoftwareChangeover and ProductionBatch, freezes the physical columns behind
append-only guards, and captures legacy current values as ``LEGACY_CURRENT``
baselines. No correction write commands are opened by this migration.

Revision ID: 0029_changeover_batch_history
Revises: 0028_deployment_actual_guard
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0029_changeover_batch_history"
down_revision = "0028_deployment_actual_guard"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "changeover_baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("changeover_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("software_changeovers.id"), nullable=False),
        sa.Column("from_release_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("releases.id"), nullable=False),
        sa.Column("to_release_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("releases.id"), nullable=False),
        sa.Column("recorded_status", sa.String(30), nullable=False),
        sa.Column("recorded_changed_at", sa.DateTime(timezone=True)),
        sa.Column("recorded_note", sa.Text()),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("baseline_event_no", sa.String(50)),
        sa.UniqueConstraint("changeover_id", name="uq_changeover_baseline_target"),
        sa.CheckConstraint(
            "source IN ('LEGACY_CURRENT','IMPORTED_CURRENT','FIRST_RECORD')",
            name="ck_changeover_baseline_source"),
    )

    op.create_table(
        "changeover_corrections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("changeover_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("software_changeovers.id"), nullable=False),
        sa.Column("baseline_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("changeover_baselines.id"), nullable=False),
        sa.Column("predecessor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("from_release_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("releases.id"), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text()),
        sa.Column("correction_reason", sa.Text(), nullable=False),
        sa.Column("actor_name", sa.String(120), nullable=False),
        sa.Column("actor_principal_id", postgresql.UUID(as_uuid=True)),
        sa.Column("request_json", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("audit_event_no", sa.String(50), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("changeover_id", "revision",
                            name="uq_changeover_corr_revision"),
        sa.UniqueConstraint("baseline_id", "revision",
                            name="uq_changeover_corr_baseline_revision"),
        sa.UniqueConstraint("changeover_id", "id",
                            name="uq_changeover_corr_target_id"),
        sa.CheckConstraint("revision >= 1",
                           name="ck_changeover_corr_revision_positive"),
        sa.CheckConstraint("length(btrim(correction_reason)) BETWEEN 1 AND 2000",
                           name="ck_changeover_corr_reason"),
        sa.ForeignKeyConstraint(
            ["changeover_id", "predecessor_id"],
            ["changeover_corrections.changeover_id",
             "changeover_corrections.id"],
            name="fk_changeover_corr_predecessor"),
    )
    op.create_index("ix_changeover_corr_target_revision",
                    "changeover_corrections", ["changeover_id", "revision"])
    op.create_index("ux_changeover_corr_single_successor",
                    "changeover_corrections", ["predecessor_id"],
                    unique=True, postgresql_where=sa.text("predecessor_id IS NOT NULL"))

    op.create_table(
        "batch_baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("production_batches.id"), nullable=False),
        sa.Column("release_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("releases.id"), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("release_snapshots.id"), nullable=False),
        sa.Column("changeover_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("software_changeovers.id")),
        sa.Column("recorded_status", sa.String(30), nullable=False),
        sa.Column("recorded_started_at", sa.DateTime(timezone=True)),
        sa.Column("recorded_ended_at", sa.DateTime(timezone=True)),
        sa.Column("recorded_note", sa.Text()),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("baseline_event_no", sa.String(50)),
        sa.UniqueConstraint("batch_id", name="uq_batch_baseline_target"),
        sa.CheckConstraint(
            "source IN ('LEGACY_CURRENT','IMPORTED_CURRENT','FIRST_RECORD')",
            name="ck_batch_baseline_source"),
    )

    op.create_table(
        "batch_corrections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("production_batches.id"), nullable=False),
        sa.Column("baseline_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("batch_baselines.id"), nullable=False),
        sa.Column("predecessor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("changeover_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("software_changeovers.id")),
        sa.Column("note", sa.Text()),
        sa.Column("correction_reason", sa.Text(), nullable=False),
        sa.Column("actor_name", sa.String(120), nullable=False),
        sa.Column("actor_principal_id", postgresql.UUID(as_uuid=True)),
        sa.Column("request_json", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("audit_event_no", sa.String(50), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("batch_id", "revision",
                            name="uq_batch_corr_revision"),
        sa.UniqueConstraint("baseline_id", "revision",
                            name="uq_batch_corr_baseline_revision"),
        sa.UniqueConstraint("batch_id", "id",
                            name="uq_batch_corr_target_id"),
        sa.CheckConstraint("revision >= 1",
                           name="ck_batch_corr_revision_positive"),
        sa.CheckConstraint("length(btrim(correction_reason)) BETWEEN 1 AND 2000",
                           name="ck_batch_corr_reason"),
        sa.CheckConstraint(
            "(ended_at IS NULL) OR (started_at IS NULL) OR (ended_at >= started_at)",
            name="ck_batch_corr_ended_after_started"),
        sa.ForeignKeyConstraint(
            ["batch_id", "predecessor_id"],
            ["batch_corrections.batch_id", "batch_corrections.id"],
            name="fk_batch_corr_predecessor"),
    )
    op.create_index("ix_batch_corr_target_revision",
                    "batch_corrections", ["batch_id", "revision"])
    op.create_index("ux_batch_corr_single_successor",
                    "batch_corrections", ["predecessor_id"],
                    unique=True, postgresql_where=sa.text("predecessor_id IS NOT NULL"))

    # Append-only: no UPDATE/DELETE on any changeover/batch baseline or
    # correction ledger row.
    op.execute("""
    CREATE FUNCTION reject_changeover_batch_history_mutation() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'Changeover/batch history is append-only'
        USING ERRCODE = '55000';
    END $$;

    CREATE TRIGGER changeover_baselines_append_only
      BEFORE UPDATE OR DELETE ON changeover_baselines
      FOR EACH ROW EXECUTE FUNCTION reject_changeover_batch_history_mutation();
    CREATE TRIGGER changeover_corrections_append_only
      BEFORE UPDATE OR DELETE ON changeover_corrections
      FOR EACH ROW EXECUTE FUNCTION reject_changeover_batch_history_mutation();
    CREATE TRIGGER batch_baselines_append_only
      BEFORE UPDATE OR DELETE ON batch_baselines
      FOR EACH ROW EXECUTE FUNCTION reject_changeover_batch_history_mutation();
    CREATE TRIGGER batch_corrections_append_only
      BEFORE UPDATE OR DELETE ON batch_corrections
      FOR EACH ROW EXECUTE FUNCTION reject_changeover_batch_history_mutation();
    """)

    # Freeze the physical columns: once a baseline exists, the recorded facts
    # must not be overwritten in place. No-op transitions are allowed so the
    # existing create-only flows (which never change these values after insert)
    # remain compatible.
    op.execute("""
    CREATE FUNCTION guard_changeover_physical_write() RETURNS trigger AS $$
    BEGIN
      IF ROW(OLD.from_release_id, OLD.to_release_id, OLD.status, OLD.changed_at, OLD.note)
         IS NOT DISTINCT FROM
         ROW(NEW.from_release_id, NEW.to_release_id, NEW.status, NEW.changed_at, NEW.note) THEN
        RETURN NEW;
      END IF;
      IF EXISTS (SELECT 1 FROM changeover_baselines WHERE changeover_id = OLD.id) THEN
        RAISE EXCEPTION
          'Changeover recorded facts are immutable; append a correction'
          USING ERRCODE = '55000';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """)
    op.execute("""
    CREATE TRIGGER changeover_physical_write_guard
    BEFORE UPDATE OR DELETE ON software_changeovers
    FOR EACH ROW EXECUTE FUNCTION guard_changeover_physical_write()
    """)

    op.execute("""
    CREATE FUNCTION guard_batch_physical_write() RETURNS trigger AS $$
    BEGIN
      IF ROW(OLD.release_id, OLD.snapshot_id, OLD.status, OLD.started_at,
             OLD.ended_at, OLD.changeover_id, OLD.note)
         IS NOT DISTINCT FROM
         ROW(NEW.release_id, NEW.snapshot_id, NEW.status, NEW.started_at,
             NEW.ended_at, NEW.changeover_id, NEW.note) THEN
        RETURN NEW;
      END IF;
      IF EXISTS (SELECT 1 FROM batch_baselines WHERE batch_id = OLD.id) THEN
        RAISE EXCEPTION
          'Batch recorded facts are immutable; append a correction'
          USING ERRCODE = '55000';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """)
    op.execute("""
    CREATE TRIGGER batch_physical_write_guard
    BEFORE UPDATE OR DELETE ON production_batches
    FOR EACH ROW EXECUTE FUNCTION guard_batch_physical_write()
    """)

    # Capture legacy current values as LEGACY_CURRENT baselines for every
    # already-existing Changeover and Batch.
    op.execute("""
    INSERT INTO changeover_baselines
      (id, changeover_id, from_release_id, to_release_id, recorded_status,
       recorded_changed_at, recorded_note, source, recorded_at)
    SELECT gen_random_uuid(), id, from_release_id, to_release_id, status,
           changed_at, note, 'LEGACY_CURRENT', now()
      FROM software_changeovers
    """)
    op.execute("""
    INSERT INTO batch_baselines
      (id, batch_id, release_id, snapshot_id, changeover_id, recorded_status,
       recorded_started_at, recorded_ended_at, recorded_note, source, recorded_at)
    SELECT gen_random_uuid(), id, release_id, snapshot_id, changeover_id, status,
           started_at, ended_at, note, 'LEGACY_CURRENT', now()
      FROM production_batches
    """)


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM changeover_corrections) THEN
        RAISE EXCEPTION 'Cannot downgrade: changeover corrections would be lost';
      END IF;
      IF EXISTS (SELECT 1 FROM batch_corrections) THEN
        RAISE EXCEPTION 'Cannot downgrade: batch corrections would be lost';
      END IF;
      IF EXISTS (SELECT 1 FROM changeover_baselines b
                 WHERE b.source = 'FIRST_RECORD') THEN
        RAISE EXCEPTION 'Cannot downgrade: first-record changeover history would be lost';
      END IF;
      IF EXISTS (SELECT 1 FROM batch_baselines b
                 WHERE b.source = 'FIRST_RECORD') THEN
        RAISE EXCEPTION 'Cannot downgrade: first-record batch history would be lost';
      END IF;
    END $$""")
    op.execute("DROP TRIGGER changeover_physical_write_guard ON software_changeovers")
    op.execute("DROP TRIGGER batch_physical_write_guard ON production_batches")
    op.execute("DROP FUNCTION guard_changeover_physical_write()")
    op.execute("DROP FUNCTION guard_batch_physical_write()")
    op.execute("DROP TRIGGER changeover_baselines_append_only ON changeover_baselines")
    op.execute("DROP TRIGGER changeover_corrections_append_only ON changeover_corrections")
    op.execute("DROP TRIGGER batch_baselines_append_only ON batch_baselines")
    op.execute("DROP TRIGGER batch_corrections_append_only ON batch_corrections")
    op.execute("DROP FUNCTION reject_changeover_batch_history_mutation()")
    op.drop_table("batch_corrections")
    op.drop_table("batch_baselines")
    op.drop_table("changeover_corrections")
    op.drop_table("changeover_baselines")
