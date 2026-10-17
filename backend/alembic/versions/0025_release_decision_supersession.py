"""Append-only ReleaseDecision supersession history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0025_release_decision_supersession"
down_revision = "0024_release_customer_scope"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("release_decisions", sa.Column("supersedes_id", postgresql.UUID(as_uuid=True)))
    op.add_column("release_decisions", sa.Column("correction_reason", sa.Text()))
    op.create_unique_constraint(
        "uq_release_decision_context", "release_decisions", ["id", "release_id", "snapshot_id"]
    )
    op.create_unique_constraint(
        "uq_release_decision_supersedes", "release_decisions", ["supersedes_id"]
    )
    op.create_foreign_key(
        "fk_release_decision_supersedes_context", "release_decisions", "release_decisions",
        ["supersedes_id", "release_id", "snapshot_id"], ["id", "release_id", "snapshot_id"],
    )
    op.create_check_constraint(
        "ck_release_decision_supersession_pair", "release_decisions",
        "(supersedes_id IS NULL AND correction_reason IS NULL) OR "
        "(supersedes_id IS NOT NULL AND correction_reason IS NOT NULL "
        "AND length(btrim(correction_reason)) BETWEEN 1 AND 4000)",
    )
    op.create_check_constraint(
        "ck_release_decision_not_self", "release_decisions",
        "supersedes_id IS NULL OR supersedes_id <> id",
    )
    op.create_index(
        "ix_release_decisions_effective", "release_decisions",
        ["release_id", sa.text("decided_at DESC"), sa.text("id DESC")],
    )
    op.execute("""
    CREATE FUNCTION reject_release_decision_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'Release decisions are append-only' USING ERRCODE = '55000';
    END $$;
    CREATE TRIGGER release_decisions_append_only
      BEFORE UPDATE OR DELETE ON release_decisions
      FOR EACH ROW EXECUTE FUNCTION reject_release_decision_mutation();
    """)


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM release_decisions WHERE supersedes_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Cannot downgrade: release decision supersession history would be lost';
      END IF;
    END $$""")
    op.execute("DROP TRIGGER release_decisions_append_only ON release_decisions")
    op.execute("DROP FUNCTION reject_release_decision_mutation()")
    op.drop_index("ix_release_decisions_effective", table_name="release_decisions")
    op.drop_constraint("ck_release_decision_not_self", "release_decisions", type_="check")
    op.drop_constraint("ck_release_decision_supersession_pair", "release_decisions", type_="check")
    op.drop_constraint("fk_release_decision_supersedes_context", "release_decisions", type_="foreignkey")
    op.drop_constraint("uq_release_decision_supersedes", "release_decisions", type_="unique")
    op.drop_constraint("uq_release_decision_context", "release_decisions", type_="unique")
    op.drop_column("release_decisions", "correction_reason")
    op.drop_column("release_decisions", "supersedes_id")
