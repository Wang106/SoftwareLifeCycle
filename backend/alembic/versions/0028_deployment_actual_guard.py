"""Freeze Deployment physical actual values behind append-only history.

Revision ID: 0028_deployment_actual_guard
Revises: 0027_production_actual_history
"""
from alembic import op

revision = "0028_deployment_actual_guard"
down_revision = "0027_production_actual_history"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE FUNCTION guard_deployment_actual_write() RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        IF OLD.actual_release_id IS NOT NULL
           OR OLD.actual_snapshot_id IS NOT NULL
           OR EXISTS (
             SELECT 1 FROM deployment_actual_baselines
             WHERE deployment_id = OLD.id
           ) THEN
          RAISE EXCEPTION
            'reported Deployment actual values are immutable; append a correction'
            USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
      END IF;

      IF ROW(OLD.actual_release_id, OLD.actual_snapshot_id, OLD.status,
             OLD.actual_version, OLD.deployed_at)
         IS NOT DISTINCT FROM
         ROW(NEW.actual_release_id, NEW.actual_snapshot_id, NEW.status,
             NEW.actual_version, NEW.deployed_at) THEN
        RETURN NEW;
      END IF;

      IF OLD.actual_release_id IS NOT NULL
         OR OLD.actual_snapshot_id IS NOT NULL
         OR EXISTS (
           SELECT 1 FROM deployment_actual_baselines
           WHERE deployment_id = OLD.id
         ) THEN
        RAISE EXCEPTION
          'reported Deployment actual values are immutable; append a correction'
          USING ERRCODE = '55000';
      END IF;

      IF OLD.actual_release_id IS NULL
         AND OLD.actual_snapshot_id IS NULL
         AND OLD.actual_version = 0
         AND NEW.actual_release_id IS NOT NULL
         AND NEW.actual_snapshot_id IS NOT NULL
         AND NEW.status IN ('MATCH', 'MISMATCH')
         AND NEW.actual_version = 1
         AND NEW.deployed_at IS NOT NULL THEN
        RETURN NEW;
      END IF;

      RAISE EXCEPTION
        'Deployment actual transition must be a complete first report'
        USING ERRCODE = '55000';
    END;
    $$ LANGUAGE plpgsql
    """)
    op.execute("""
    CREATE TRIGGER deployments_actual_write_guard
    BEFORE UPDATE OR DELETE ON deployments
    FOR EACH ROW EXECUTE FUNCTION guard_deployment_actual_write()
    """)

    op.execute("""
    CREATE FUNCTION verify_deployment_actual_baseline() RETURNS trigger AS $$
    DECLARE
      baseline deployment_actual_baselines%ROWTYPE;
    BEGIN
      SELECT * INTO baseline
      FROM deployment_actual_baselines
      WHERE deployment_id = NEW.id;

      IF NEW.actual_release_id IS NULL AND NEW.actual_snapshot_id IS NULL THEN
        IF FOUND THEN
          RAISE EXCEPTION
            'unreported Deployment must not have an actual baseline'
            USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
      END IF;

      IF NEW.actual_release_id IS NULL OR NEW.actual_snapshot_id IS NULL THEN
        RAISE EXCEPTION
          'Deployment actual release and snapshot must be reported together'
          USING ERRCODE = '55000';
      END IF;

      IF NOT FOUND
         OR baseline.actual_release_id IS DISTINCT FROM NEW.actual_release_id
         OR baseline.actual_snapshot_id IS DISTINCT FROM NEW.actual_snapshot_id
         OR baseline.recorded_status IS DISTINCT FROM NEW.status
         OR baseline.recorded_actual_version IS DISTINCT FROM NEW.actual_version
         OR baseline.recorded_deployed_at IS DISTINCT FROM NEW.deployed_at THEN
        RAISE EXCEPTION
          'reported Deployment must match its immutable actual baseline'
          USING ERRCODE = '55000';
      END IF;

      IF baseline.source = 'FIRST_REPORT' AND (
        baseline.baseline_event_no IS NULL OR NOT EXISTS (
          SELECT 1 FROM audit_events event
          WHERE event.event_no = baseline.baseline_event_no
            AND event.entity_type = 'DEPLOYMENT'
            AND event.entity_id = NEW.id
            AND event.action = 'ACTUAL_REPORTED'
            AND event.payload_json -> 'after' ->> 'actual_release_id'
                = NEW.actual_release_id::text
            AND event.payload_json -> 'after' ->> 'actual_snapshot_id'
                = NEW.actual_snapshot_id::text
            AND event.payload_json -> 'after' ->> 'status' = NEW.status
            AND (event.payload_json -> 'after' ->> 'actual_version')::integer
                = NEW.actual_version
            AND (event.payload_json -> 'after' ->> 'deployed_at')::timestamptz
                IS NOT DISTINCT FROM NEW.deployed_at
        )
      ) THEN
        RAISE EXCEPTION
          'first Deployment actual report requires its matching audit proof'
          USING ERRCODE = '55000';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """)
    op.execute("""
    CREATE CONSTRAINT TRIGGER deployments_actual_baseline_guard
    AFTER INSERT OR UPDATE ON deployments
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION verify_deployment_actual_baseline()
    """)


def downgrade():
    op.execute(
        "DROP TRIGGER deployments_actual_baseline_guard ON deployments"
    )
    op.execute(
        "DROP TRIGGER deployments_actual_write_guard ON deployments"
    )
    op.execute("DROP FUNCTION verify_deployment_actual_baseline()")
    op.execute("DROP FUNCTION guard_deployment_actual_write()")
