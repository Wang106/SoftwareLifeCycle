"""Bounded PG16 system-catalog observations on a caller-owned read-only transaction.

No connection creation, CLI, environment configuration, DDL, commit or rollback.
This is NOT the public-schema checklist and does not claim schema acceptance.
"""
import hashlib
import json
import re

TABLES = ('alembic_version', 'releases', 'release_snapshots', 'changeover_baselines',
          'changeover_corrections', 'batch_baselines', 'batch_corrections')
FUNCTIONS = ('reject_changeover_batch_history_mutation', 'guard_changeover_physical_write',
             'guard_batch_physical_write')
TRIGGERS = ('changeover_baselines_append_only', 'changeover_corrections_append_only',
            'batch_baselines_append_only', 'batch_corrections_append_only',
            'changeover_physical_write_guard', 'batch_physical_write_guard')
MAX_TEXT = 16384
MAX_OUTPUT = 524288
LIMITS = {'tables': 8, 'columns': 512, 'constraints': 256, 'indexes': 128,
          'functions': 16, 'triggers': 32}
EXAMPLES = {
    'tables': {'namespace': 'x', 'name': 'releases', 'kind': 'r', 'persistence': 'p',
               'access_method': 'heap', 'row_security': False, 'force_row_security': False},
    'columns': {'namespace': 'x', 'table': 'releases', 'name': 'id', 'position': 1,
                'type': 'uuid', 'not_null': True, 'identity': '', 'generated': ''},
    'constraints': {'namespace': 'x', 'table': 'releases', 'name': 'releases_pkey',
                    'kind': 'p', 'columns': ['id'], 'reference_namespace': None,
                    'reference_table': None, 'reference_columns': [], 'definition': 'PRIMARY KEY (id)',
                    'validated': True, 'deferrable': False, 'initially_deferred': False},
    'indexes': {'namespace': 'x', 'table': 'releases', 'name': 'releases_pkey',
                'access_method': 'btree', 'unique': True, 'valid': True, 'ready': True,
                'live': True, 'definition': 'CREATE UNIQUE INDEX', 'predicate': None},
    'functions': {'namespace': 'x', 'name': FUNCTIONS[0], 'identity_arguments': '',
                  'result': 'trigger', 'language': 'plpgsql', 'security_definer': False, 'source': ''},
    'triggers': {'namespace': 'x', 'table': 'changeover_baselines', 'name': TRIGGERS[0],
                 'function_namespace': 'x', 'function_name': FUNCTIONS[0],
                 'function_arguments': '', 'type_bits': 27, 'enabled': 'O',
                 'internal': False, 'constraint': False, 'definition': 'CREATE TRIGGER'},
}


def literals(names):
    return '(' + ','.join("'" + name + "'" for name in names) + ')'


CONTEXT = """SELECT pg_catalog.jsonb_build_object(
 'server_version_num', pg_catalog.current_setting('server_version_num')::int,
 'read_only', pg_catalog.current_setting('transaction_read_only') = 'on',
 'isolation', pg_catalog.current_setting('transaction_isolation'),
 'search_path', pg_catalog.current_setting('search_path'),
 'statement_timeout_ms', (SELECT setting::int FROM pg_catalog.pg_settings WHERE name='statement_timeout'),
 'lock_timeout_ms', (SELECT setting::int FROM pg_catalog.pg_settings WHERE name='lock_timeout'),
 'idle_timeout_ms', (SELECT setting::int FROM pg_catalog.pg_settings WHERE name='idle_in_transaction_session_timeout'),
 'namespace_oid', n.oid::bigint)
 FROM pg_catalog.pg_namespace n WHERE n.nspname = %s LIMIT 2"""


def query(fields, source, where, order, limit):
    pairs = ',\n'.join("'" + key + "', " + expression for key, expression in fields.items())
    return (f'SELECT pg_catalog.jsonb_build_object({pairs})\nFROM {source}\n'
            f'WHERE n.oid = %s AND {where}\nORDER BY {order} LIMIT {limit + 1}')


RELATIONS = 'pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace'
SELECTED = 'c.relname IN ' + literals(TABLES)
QUERIES = {
 'tables': query({
    'namespace': 'n.nspname', 'name': 'c.relname', 'kind': 'c.relkind',
    'persistence': 'c.relpersistence', 'access_method': 'am.amname',
    'row_security': 'c.relrowsecurity', 'force_row_security': 'c.relforcerowsecurity'},
    RELATIONS + ' LEFT JOIN pg_catalog.pg_am am ON am.oid=c.relam', SELECTED,
    'c.relname, c.oid', LIMITS['tables']),
 'columns': query({
    'namespace': 'n.nspname', 'table': 'c.relname', 'name': 'a.attname',
    'position': 'a.attnum', 'type': 'pg_catalog.format_type(a.atttypid,a.atttypmod)',
    'not_null': 'a.attnotnull', 'identity': 'a.attidentity', 'generated': 'a.attgenerated'},
    RELATIONS + ' JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid',
    SELECTED + ' AND a.attnum>0 AND NOT a.attisdropped', 'c.relname,a.attnum', LIMITS['columns']),
 'constraints': query({
    'namespace': 'n.nspname', 'table': 'c.relname', 'name': 'k.conname', 'kind': 'k.contype',
    'columns': "ARRAY(SELECT a.attname FROM unnest(k.conkey) WITH ORDINALITY u(num,ord) JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum=u.num ORDER BY u.ord)",
    'reference_namespace': 'rn.nspname', 'reference_table': 'rc.relname',
    'reference_columns': "ARRAY(SELECT a.attname FROM unnest(k.confkey) WITH ORDINALITY u(num,ord) JOIN pg_catalog.pg_attribute a ON a.attrelid=rc.oid AND a.attnum=u.num ORDER BY u.ord)",
    'definition': 'pg_catalog.substr(pg_catalog.pg_get_constraintdef(k.oid,false),1,16385)',
    'validated': 'k.convalidated', 'deferrable': 'k.condeferrable', 'initially_deferred': 'k.condeferred'},
    RELATIONS + ' JOIN pg_catalog.pg_constraint k ON k.conrelid=c.oid LEFT JOIN pg_catalog.pg_class rc ON rc.oid=k.confrelid LEFT JOIN pg_catalog.pg_namespace rn ON rn.oid=rc.relnamespace',
    SELECTED, 'c.relname,k.conname,k.oid', LIMITS['constraints']),
 'indexes': query({
    'namespace': 'n.nspname', 'table': 'c.relname', 'name': 'ic.relname',
    'access_method': 'am.amname', 'unique': 'i.indisunique', 'valid': 'i.indisvalid',
    'ready': 'i.indisready', 'live': 'i.indislive',
    'definition': 'pg_catalog.substr(pg_catalog.pg_get_indexdef(i.indexrelid),1,16385)',
    'predicate': 'pg_catalog.substr(pg_catalog.pg_get_expr(i.indpred,i.indrelid,false),1,16385)'},
    RELATIONS + ' JOIN pg_catalog.pg_index i ON i.indrelid=c.oid JOIN pg_catalog.pg_class ic ON ic.oid=i.indexrelid JOIN pg_catalog.pg_am am ON am.oid=ic.relam',
    SELECTED, 'c.relname,ic.relname,i.indexrelid', LIMITS['indexes']),
 'functions': query({
    'namespace': 'n.nspname', 'name': 'p.proname',
    'identity_arguments': 'pg_catalog.substr(pg_catalog.pg_get_function_identity_arguments(p.oid),1,16385)',
    'result': 'pg_catalog.substr(pg_catalog.pg_get_function_result(p.oid),1,16385)',
    'language': 'l.lanname', 'security_definer': 'p.prosecdef',
    'source': 'pg_catalog.substr(p.prosrc,1,16385)'},
    'pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace JOIN pg_catalog.pg_language l ON l.oid=p.prolang',
    'p.proname IN ' + literals(FUNCTIONS), 'p.proname,p.oid', LIMITS['functions']),
 'triggers': query({
    'namespace': 'n.nspname', 'table': 'c.relname', 'name': 't.tgname',
    'function_namespace': 'pn.nspname', 'function_name': 'p.proname',
    'function_arguments': 'pg_catalog.substr(pg_catalog.pg_get_function_identity_arguments(p.oid),1,16385)',
    'type_bits': 't.tgtype', 'enabled': 't.tgenabled', 'internal': 't.tgisinternal',
    'constraint': 't.tgconstraint <> 0',
    'definition': 'pg_catalog.substr(pg_catalog.pg_get_triggerdef(t.oid,false),1,16385)'},
    RELATIONS + ' JOIN pg_catalog.pg_trigger t ON t.tgrelid=c.oid JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace',
    't.tgname IN ' + literals(TRIGGERS) + ' AND c.relname IN ' + literals(TABLES + ('software_changeovers', 'production_batches')),
    'c.relname,t.tgname,t.oid', LIMITS['triggers']),
}


class CatalogError(ValueError):
    def __init__(self):
        super().__init__('CATALOG_COLLECTION_FAILED')


def validate_namespace(namespace):
    if (type(namespace) is not str or not re.fullmatch('[a-z_][a-z0-9_]{0,62}', namespace)
            or namespace.startswith('pg_') or namespace == 'information_schema'):
        raise CatalogError()


def validate_context(row):
    keys = {'server_version_num', 'read_only', 'isolation', 'search_path',
            'statement_timeout_ms', 'lock_timeout_ms', 'idle_timeout_ms', 'namespace_oid'}
    if type(row) is not dict or set(row) != keys:
        raise CatalogError()
    if (type(row['server_version_num']) is not int or not 160000 <= row['server_version_num'] < 170000
            or row['read_only'] is not True or row['isolation'] != 'repeatable read'
            or row['search_path'] != 'pg_catalog' or type(row['namespace_oid']) is not int
            or not 1 <= row['namespace_oid'] <= 2**32 - 1):
        raise CatalogError()
    for key, maximum in [('statement_timeout_ms', 5000), ('lock_timeout_ms', 1000), ('idle_timeout_ms', 15000)]:
        if type(row[key]) is not int or not 1 <= row[key] <= maximum:
            raise CatalogError()


def validate_record(group, row, namespace):
    expected = EXAMPLES[group]
    if type(row) is not dict or row.keys() != expected.keys() or row['namespace'] != namespace:
        raise CatalogError()
    for key, value in row.items():
        example = expected[key]
        if example is None:
            if value is not None and type(value) is not str:
                raise CatalogError()
        elif type(value) is not type(example):
            raise CatalogError()
        if type(value) is str:
            if len(value.encode('utf-8')) > MAX_TEXT or '\x00' in value:
                raise CatalogError()
        elif type(value) is int and not 0 <= value <= 2**32 - 1:
            raise CatalogError()
        elif type(value) is list:
            if len(value) > 32 or any(type(x) is not str or len(x.encode('utf-8')) > 63 for x in value):
                raise CatalogError()
    table = row.get('table', row.get('name') if group == 'tables' else None)
    if table is not None and table not in TABLES + ('software_changeovers', 'production_batches'):
        raise CatalogError()
    if group == 'functions' and row['name'] not in FUNCTIONS:
        raise CatalogError()
    if group == 'triggers' and row['name'] not in TRIGGERS:
        raise CatalogError()


def require_active_transaction(connection):
    # psycopg exposes its libpq transaction state as an IntEnum. Checking the
    # state (not merely default GUCs) excludes idle/autocommit multi-snapshot reads.
    state = connection.info.transaction_status
    if (not isinstance(state, int) or isinstance(state, bool)
            or int(state) != 2 or getattr(state, 'name', None) != 'INTRANS'):
        raise CatalogError()


def collect(connection, namespace):
    """Observe in caller's transaction; caller alone owns completion/rollback.

    The caller must set a read-only repeatable-read transaction and bounded local
    timeouts before calling. No receipt proves it later committed or rolled back.
    Missing objects remain absent observations, not invented defaults or MATCHED.
    """
    validate_namespace(namespace)
    cursor = None
    result = None
    try:
        require_active_transaction(connection)
        cursor = connection.cursor()
        cursor.execute(CONTEXT, (namespace,))
        rows = cursor.fetchmany(2)
        if len(rows) != 1 or len(rows[0]) != 1:
            raise CatalogError()
        context = rows[0][0]
        validate_context(context)
        observations = {}
        for group, sql in QUERIES.items():
            cursor.execute(sql, (context['namespace_oid'],))
            rows = cursor.fetchmany(LIMITS[group] + 1)
            if len(rows) > LIMITS[group]:
                raise CatalogError()
            collected, seen = [], set()
            for item in rows:
                if type(item) not in (tuple, list) or len(item) != 1:
                    raise CatalogError()
                row = item[0]
                validate_record(group, row, namespace)
                identity = (row.get('table'), row['name'], row.get('identity_arguments'))
                if identity in seen:
                    raise CatalogError()
                seen.add(identity)
                row = dict(row)
                if group == 'functions':
                    body = row.pop('source').encode('utf-8')
                    row['body_sha256'] = hashlib.sha256(body).hexdigest()
                    row['body_bytes'] = len(body)
                collected.append(row)
            observations[group] = collected
            if len(json.dumps(observations, ensure_ascii=True).encode()) > MAX_OUTPUT:
                raise CatalogError()
        result = {'format': 'slc-pg16-catalog-observation-v1',
                  'status': 'CATALOG_COLLECTED_NOT_ACCEPTANCE', 'namespace': namespace,
                  'namespace_oid': context['namespace_oid'], 'server_version_num': context['server_version_num'],
                  'database_verified': False, 'complete_schema_verified': False,
                  'transaction_completed': False, 'observations': observations}
    except Exception:
        raise CatalogError() from None
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                raise CatalogError() from None
    try:
        require_active_transaction(connection)
    except Exception:
        raise CatalogError() from None
    return result
