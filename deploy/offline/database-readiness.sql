-- psql 16 script, NOT executed by the offline Python checker.
-- Only for a separately authorized, trusted, quiescent synthetic PostgreSQL 16
-- database. Read docs/offline-database-readiness.md before any future execution.
-- Read-only mode is not a sandbox against hostile databases or user functions.
-- No connection command, business-table scan, role change or permission change.
\set ON_ERROR_STOP on
\set QUIET on
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';
SET LOCAL idle_in_transaction_session_timeout = '15s';
SET LOCAL search_path = pg_catalog;

WITH
role_info AS (
    SELECT r.oid, r.rolsuper, r.rolcreatedb, r.rolcreaterole,
           r.rolreplication, r.rolbypassrls
    FROM pg_catalog.pg_roles AS r WHERE r.rolname = CURRENT_USER
),
database_info AS (
    SELECT d.oid FROM pg_catalog.pg_database AS d
    WHERE d.datname = pg_catalog.current_database()
),
non_system_schemas AS (
    SELECT n.oid, n.nspname FROM pg_catalog.pg_namespace AS n
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
),
relations AS (
    SELECT c.* FROM pg_catalog.pg_class AS c
    JOIN non_system_schemas AS n ON n.oid = c.relnamespace
),
migration_relation AS (
    SELECT c.* FROM pg_catalog.pg_class AS c
    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relname = 'alembic_version'
),
migration_shape AS (
    -- Do not select version_num from a view, foreign/partitioned/inherited table,
    -- custom type, generated column or RLS/rewrite-rule-bearing relation.
    SELECT c.oid FROM migration_relation AS c
    WHERE c.relkind = 'r' AND c.relpersistence = 'p' AND NOT c.relispartition
      AND NOT c.relrowsecurity AND NOT c.relforcerowsecurity AND NOT c.relhasrules
      AND c.relam = (SELECT a.oid FROM pg_catalog.pg_am AS a WHERE a.amname = 'heap')
      AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_inherits AS i
                      WHERE i.inhrelid = c.oid OR i.inhparent = c.oid)
      AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_trigger AS t
                      WHERE t.tgrelid = c.oid AND NOT t.tgisinternal)
      -- Planner/index access may invoke callbacks even for a read. Permit only
      -- simple, valid builtin btree indexes, including the normal Alembic PK.
      AND NOT EXISTS (
          SELECT 1 FROM pg_catalog.pg_index AS i
          JOIN pg_catalog.pg_class AS index_relation ON index_relation.oid = i.indexrelid
          WHERE i.indrelid = c.oid AND (
              index_relation.relam <> (SELECT a.oid FROM pg_catalog.pg_am AS a WHERE a.amname = 'btree')
              OR i.indexprs IS NOT NULL OR i.indpred IS NOT NULL
              OR NOT i.indisvalid OR NOT i.indisready OR NOT i.indislive
              OR EXISTS (
                  SELECT 1 FROM pg_catalog.pg_opclass AS o
                  JOIN pg_catalog.pg_namespace AS n ON n.oid = o.opcnamespace
                  WHERE o.oid = ANY(i.indclass) AND n.nspname <> 'pg_catalog'
              )
          )
      )
      AND (SELECT pg_catalog.count(*) FROM pg_catalog.pg_attribute AS a
           WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped) = 1
      AND EXISTS (
          SELECT 1 FROM pg_catalog.pg_attribute AS a
          WHERE a.attrelid = c.oid AND a.attnum = 1 AND a.attname = 'version_num'
            AND NOT a.attisdropped AND a.attnotnull
            AND a.atttypid = 'pg_catalog.varchar'::pg_catalog.regtype
            AND a.atttypmod = 68 AND NOT a.atthasdef
            AND a.attgenerated = '' AND a.attidentity = ''
      )
),
migration_access AS (
    SELECT c.oid FROM migration_shape AS c
    WHERE pg_catalog.has_column_privilege(CURRENT_USER, c.oid, 'version_num', 'SELECT')
)
SELECT pg_catalog.jsonb_build_object(
    'format', 'slc-offline-database-evidence-v1',
    'server_version_num', pg_catalog.current_setting('server_version_num')::pg_catalog.int4,
    'transaction_read_only', pg_catalog.current_setting('transaction_read_only') = 'on',
    'session_role_unchanged', CURRENT_USER = SESSION_USER,
    'role_count', (SELECT pg_catalog.count(*) FROM role_info),
    'role_superuser', (SELECT r.rolsuper FROM role_info AS r),
    'role_create_db', (SELECT r.rolcreatedb FROM role_info AS r),
    'role_create_role', (SELECT r.rolcreaterole FROM role_info AS r),
    'role_replication', (SELECT r.rolreplication FROM role_info AS r),
    'role_bypass_rls', (SELECT r.rolbypassrls FROM role_info AS r),
    -- Reject every membership involving this role, regardless of PG16 inherit/
    -- set/admin options. No recursive SET ROLE capability claim is made.
    'role_membership_count', (
        SELECT pg_catalog.count(*) FROM pg_catalog.pg_auth_members AS m
        WHERE m.member = (SELECT r.oid FROM role_info AS r)
           OR m.roleid = (SELECT r.oid FROM role_info AS r)
    ),
    -- Ownership dependencies include database/schema/relation/routine/type and
    -- other owned objects in this database plus shared objects. ACLs alone do not.
    'owned_object_count', (
        SELECT pg_catalog.count(*) FROM pg_catalog.pg_shdepend AS d
        WHERE d.refclassid = 'pg_catalog.pg_authid'::pg_catalog.regclass
          AND d.refobjid = (SELECT r.oid FROM role_info AS r) AND d.deptype = 'o'
          AND (d.dbid = 0 OR d.dbid = (SELECT b.oid FROM database_info AS b))
    ),
    'database_create', pg_catalog.has_database_privilege(CURRENT_USER, pg_catalog.current_database(), 'CREATE'),
    'database_temp', pg_catalog.has_database_privilege(CURRENT_USER, pg_catalog.current_database(), 'TEMP'),
    'schema_create_count', (
        SELECT pg_catalog.count(*) FROM pg_catalog.pg_namespace AS n
        WHERE pg_catalog.has_schema_privilege(CURRENT_USER, n.oid, 'CREATE')
    ),
    'table_write_count', (
        -- System-schema ACL grants are dangerous too. CASE prevents unsupported
        -- relation kinds from reaching a privilege function if plans reorder.
        SELECT pg_catalog.count(*) FROM pg_catalog.pg_class AS c
        WHERE CASE WHEN c.relkind IN ('r', 'p', 'v', 'm', 'f')
          THEN pg_catalog.has_table_privilege(CURRENT_USER, c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
          ELSE false END
    ),
    'column_write_count', (
        SELECT pg_catalog.count(*) FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_attribute AS a ON a.attrelid = c.oid
        WHERE CASE WHEN c.relkind IN ('r', 'p', 'v', 'm', 'f') AND a.attnum > 0 AND NOT a.attisdropped
          THEN pg_catalog.has_column_privilege(CURRENT_USER, c.oid, a.attnum, 'INSERT,UPDATE,REFERENCES')
          ELSE false END
    ),
    'sequence_write_count', (
        SELECT pg_catalog.count(*) FROM pg_catalog.pg_class AS c
        WHERE CASE WHEN c.relkind = 'S'
          THEN pg_catalog.has_sequence_privilege(CURRENT_USER, c.oid, 'USAGE,UPDATE')
          ELSE false END
    ),
    'routine_execute_count', (
        SELECT pg_catalog.count(*) FROM pg_catalog.pg_proc AS p
        JOIN non_system_schemas AS n ON n.oid = p.pronamespace
        WHERE pg_catalog.has_function_privilege(CURRENT_USER, p.oid, 'EXECUTE')
    ),
    'unexpected_schema_count', (
        SELECT pg_catalog.count(*) FROM non_system_schemas AS n WHERE n.nspname <> 'public'
    ),
    'unsupported_relation_count', (
        SELECT pg_catalog.count(*) FROM relations AS c
        WHERE c.relkind NOT IN ('r', 'i', 'S') OR c.relpersistence <> 'p'
           OR c.relispartition OR c.relrowsecurity OR c.relforcerowsecurity OR c.relhasrules
           OR (c.relkind = 'r' AND c.relam <> (SELECT a.oid FROM pg_catalog.pg_am AS a WHERE a.amname = 'heap'))
           OR (c.relkind = 'i' AND c.relam NOT IN (
               SELECT a.oid FROM pg_catalog.pg_am AS a
               WHERE a.amname IN ('btree', 'hash', 'gist', 'spgist', 'gin', 'brin')))
           OR EXISTS (SELECT 1 FROM pg_catalog.pg_inherits AS i
                      WHERE i.inhrelid = c.oid OR i.inhparent = c.oid)
    ),
    'unsupported_type_count', (
        -- Only table composite types and their automatically generated arrays
        -- are supported outside system schemas. Domains/enums/custom types fail.
        SELECT pg_catalog.count(*) FROM pg_catalog.pg_type AS t
        JOIN non_system_schemas AS n ON n.oid = t.typnamespace
        WHERE NOT (t.typtype = 'c' AND t.typrelid <> 0)
          AND NOT (t.typtype = 'b' AND t.typelem <> 0 AND EXISTS (
              SELECT 1 FROM pg_catalog.pg_type AS e
              WHERE e.oid = t.typelem AND e.typtype = 'c' AND e.typrelid <> 0
          ))
    ),
    'unsupported_object_count', (
        (SELECT pg_catalog.count(*) FROM pg_catalog.pg_extension AS e WHERE e.extname <> 'plpgsql')
        + (SELECT pg_catalog.count(*) FROM pg_catalog.pg_foreign_data_wrapper)
        + (SELECT pg_catalog.count(*) FROM pg_catalog.pg_foreign_server)
        + (SELECT pg_catalog.count(*) FROM pg_catalog.pg_event_trigger)
        + (SELECT pg_catalog.count(*) FROM pg_catalog.pg_publication)
        + (SELECT pg_catalog.count(*) FROM pg_catalog.pg_language AS l WHERE l.lanname NOT IN ('internal', 'c', 'sql', 'plpgsql'))
        + (SELECT pg_catalog.count(*) FROM pg_catalog.pg_collation AS c JOIN non_system_schemas AS n ON n.oid = c.collnamespace)
        + (SELECT pg_catalog.count(*) FROM pg_catalog.pg_conversion AS c JOIN non_system_schemas AS n ON n.oid = c.connamespace)
        + (SELECT pg_catalog.count(*) FROM pg_catalog.pg_operator AS o JOIN non_system_schemas AS n ON n.oid = o.oprnamespace)
        + (SELECT pg_catalog.count(*) FROM pg_catalog.pg_opclass AS o JOIN non_system_schemas AS n ON n.oid = o.opcnamespace)
        + (SELECT pg_catalog.count(*) FROM pg_catalog.pg_opfamily AS o JOIN non_system_schemas AS n ON n.oid = o.opfnamespace)
    ),
    'large_object_count', (SELECT pg_catalog.count(*) FROM pg_catalog.pg_largeobject_metadata),
    'app_schema_count', (SELECT pg_catalog.count(*) FROM pg_catalog.pg_namespace AS n WHERE n.nspname = 'public'),
    'migration_table_present', EXISTS (SELECT 1 FROM migration_relation),
    'migration_table_supported', EXISTS (SELECT 1 FROM migration_shape),
    'migration_select_permitted', EXISTS (SELECT 1 FROM migration_access)
) AS metadata, EXISTS (SELECT 1 FROM migration_access) AS migration_readable
\gset readiness_

\if :readiness_migration_readable
-- This is the sole non-catalog read: at most two migration bookkeeping values,
-- never returned verbatim. The shape guard above must pass before parsing it.
SELECT pg_catalog.jsonb_build_object(
    'migration_row_count', pg_catalog.count(*),
    'migration_expected_head_count', pg_catalog.count(*) FILTER (
        WHERE v.version_num COLLATE pg_catalog."C" = '0029_changeover_batch_history'
    )
) AS migration
FROM (SELECT version_num FROM ONLY public.alembic_version LIMIT 2) AS v
\gset readiness_
\else
SELECT pg_catalog.jsonb_build_object(
    'migration_row_count', NULL, 'migration_expected_head_count', NULL
) AS migration
\gset readiness_
\endif

SELECT (:'readiness_metadata'::pg_catalog.jsonb || :'readiness_migration'::pg_catalog.jsonb) AS document
\gset readiness_
ROLLBACK;
-- Emit only after every required statement, including transaction end, succeeds.
\echo :readiness_document
