"""Customer-scoped ASR identities, preserving legacy records without backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '0024_release_customer_scope'
down_revision = '0023_impact_withdrawal_history'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('releases', sa.Column('customer_scope_id', postgresql.UUID(as_uuid=True)))
    op.create_foreign_key('fk_release_customer_scope', 'releases', 'customers', ['customer_scope_id'], ['id'])
    op.create_check_constraint('ck_release_customer_scope', 'releases', "(release_type = 'APPLICATION' OR customer_scope_id IS NULL) AND (customer_scope_id IS NULL OR customer_scope_id <> '00000000-0000-0000-0000-000000000000')")
    op.execute("CREATE UNIQUE INDEX uq_release_customer_version ON releases (software_id, release_type, version, COALESCE(customer_scope_id, '00000000-0000-0000-0000-000000000000'::uuid))")
    op.drop_constraint('releases_software_id_release_type_version_key', 'releases', type_='unique')
    op.execute("""
    CREATE FUNCTION check_release_customer_scope() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE rid uuid; scope uuid; kind text; product uuid; detail record;
    BEGIN
      IF TG_TABLE_NAME = 'releases' THEN
        rid := NEW.id;
        IF TG_OP = 'UPDATE' AND OLD.customer_scope_id IS DISTINCT FROM NEW.customer_scope_id THEN
          RAISE EXCEPTION 'Release customer scope is immutable' USING ERRCODE = '23514';
        END IF;
      ELSE
        IF TG_OP = 'DELETE' THEN rid := OLD.release_id; ELSE rid := NEW.release_id; END IF;
        IF TG_OP = 'UPDATE' AND OLD.release_id <> NEW.release_id AND EXISTS
          (SELECT 1 FROM releases WHERE id = OLD.release_id AND customer_scope_id IS NOT NULL) THEN
          RAISE EXCEPTION 'Scoped detail cannot move to another release' USING ERRCODE = '23514';
        END IF;
      END IF;
      SELECT customer_scope_id, release_type, software_id INTO scope, kind, product FROM releases WHERE id = rid;
      IF scope IS NULL THEN RETURN NULL; END IF;
      SELECT a.customer_id, p.customer_id AS project_customer,
             b.software_id AS base_product, b.release_type AS base_type INTO detail
        FROM application_release_details a JOIN projects p ON p.id = a.project_id
        JOIN releases b ON b.id = a.standard_base_release_id WHERE a.release_id = rid;
      IF NOT FOUND OR kind <> 'APPLICATION' OR detail.customer_id <> scope OR detail.project_customer <> scope
         OR detail.base_product <> product OR detail.base_type <> 'STANDARD' THEN
        RAISE EXCEPTION 'Scoped ASR requires matching customer, project and standard product' USING ERRCODE = '23514';
      END IF;
      RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER release_customer_scope_check AFTER INSERT OR UPDATE ON releases
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_release_customer_scope();
    CREATE CONSTRAINT TRIGGER application_customer_scope_check AFTER INSERT OR UPDATE OR DELETE ON application_release_details
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_release_customer_scope();
    """)


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM releases WHERE customer_scope_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Cannot downgrade: customer-scoped release identities would be lost';
      END IF;
    END $$""")
    op.execute('DROP TRIGGER application_customer_scope_check ON application_release_details')
    op.execute('DROP TRIGGER release_customer_scope_check ON releases')
    op.execute('DROP FUNCTION check_release_customer_scope()')
    op.create_unique_constraint('releases_software_id_release_type_version_key', 'releases', ['software_id', 'release_type', 'version'])
    op.drop_index('uq_release_customer_version', table_name='releases')
    op.drop_constraint('ck_release_customer_scope', 'releases', type_='check')
    op.drop_constraint('fk_release_customer_scope', 'releases', type_='foreignkey')
    op.drop_column('releases', 'customer_scope_id')
