"""Compare selected PG16 guard observations with the fixed 0029 template.

No connection, SQL, process or CLI. Import performs no work. The caller supplies
an explicit namespace; observations are never rewritten to the public checklist.
Only the existing fixed local manifest is read during comparison. Reports may be
fabricated or stale: matching is not runtime, privilege or provenance acceptance.
"""
import json
import re

import offline_pg_catalog_evidence as catalog
import offline_migration_schema_evidence as schema

LIMITATIONS = (
    'Untrusted observation comparison for three selected functions and six selected '
    'triggers in the caller-specified namespace only. Not the public 120-fact checklist. '
    'No database identity, collection completion, freshness, source authentication, '
    'function behavior, complete schema, privilege isolation or deployment verified. '
    'Function body length is bounded metadata, not independently source-authenticated. '
    'Other PostgreSQL function and trigger attributes remain outside this contract.'
)
ENVELOPE = frozenset(('format', 'status', 'namespace', 'namespace_oid', 'server_version_num',
    'database_verified', 'complete_schema_verified', 'transaction_completed', 'observations'))


def report(status='UNKNOWN', checks=None):
    return {'format': 'slc-pg16-guard-contract-check-v1', 'status': status,
            'coverage': '0029-three-functions-six-triggers', 'checks': checks or [],
            'database_verified': False, 'complete_schema_verified': False,
            'readonly_role_verified': False, 'provenance_authenticated': False,
            'transaction_completed': False, 'limitations': LIMITATIONS}


def require(condition):
    if not condition:
        raise ValueError('GUARD_CONTRACT_INPUT_REJECTED')


def validate(document, namespace):
    catalog.validate_namespace(namespace)
    require(type(document) is dict and set(document) == ENVELOPE)
    require(type(document['format']) is str and document['format'] == 'slc-pg16-catalog-observation-v2'
            and type(document['status']) is str and document['status'] == 'CATALOG_COLLECTED_NOT_ACCEPTANCE'
            and type(document['namespace']) is str and document['namespace'] == namespace)
    require(type(document['namespace_oid']) is int and 1 <= document['namespace_oid'] <= 2**32 - 1
            and type(document['server_version_num']) is int and 160000 <= document['server_version_num'] < 170000)
    for key in ('database_verified', 'complete_schema_verified', 'transaction_completed'):
        require(document[key] is False)
    groups = document['observations']
    require(type(groups) is dict and set(groups) == set(catalog.LIMITS))
    for group, maximum in catalog.LIMITS.items():
        rows = groups[group]
        require(type(rows) is list and len(rows) <= maximum)
        seen = set()
        for row in rows:
            if group == 'functions':
                fields = (set(catalog.EXAMPLES[group]) - {'source'}) | {'body_sha256', 'body_bytes'}
                require(type(row) is dict and set(row) == fields)
                require(type(row['body_sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['body_sha256'])
                        and type(row['body_bytes']) is int and 0 <= row['body_bytes'] <= catalog.MAX_TEXT)
                # Validate the collector's unchanged metadata schema without
                # reconstructing or authenticating a body from its supplied hash.
                metadata = {key: value for key, value in row.items() if key not in ('body_sha256', 'body_bytes')}
                catalog.validate_record(group, dict(metadata, source=''), namespace)
            else:
                catalog.validate_record(group, row, namespace)
            identity = (row.get('table'), row['name'], row.get('identity_arguments'))
            require(identity not in seen)
            seen.add(identity)
    require(len(json.dumps(document, ensure_ascii=True).encode('utf-8')) <= catalog.MAX_OUTPUT)
    return groups


def check_observation(document, namespace):
    """No caller-supplied expected facts, database target, execution or mutation."""
    try:
        groups = validate(document, namespace)
        # Existing loader verifies the internal manifest's exact SHA256 and v2
        # metadata. Do not modify the manifest or accept a replacement checklist.
        facts = schema.expected_facts()
        checks = []
        for name in catalog.FUNCTIONS:
            expected = facts['function:' + name]
            require(expected['schema'] == 'public' and expected['argument_types'] == []
                    and expected['body_encoding'] == 'pg_proc.prosrc-utf8-exact-v1')
            rows = [row for row in groups['functions'] if row['name'] == name]
            matched = len(rows) == 1
            if matched:
                row = rows[0]
                matched = (row['identity_arguments'] == '' and row['result'] == expected['return_type']
                    and row['language'] == expected['language']
                    and row['security_definer'] is expected['security_definer']
                    and row['body_sha256'] == expected['body_sha256'])
            checks.append({'check': 'function:' + name, 'matched': matched})
        for name in catalog.TRIGGERS:
            expected = facts['trigger:' + name]
            require(expected['schema'] == expected['function_schema'] == 'public'
                    and expected['function_argument_types'] == expected['arguments'] == []
                    and expected['when'] is None and expected['timing'] == 'BEFORE'
                    and expected['level'] == 'ROW' and expected['events'] == ['DELETE', 'UPDATE'])
            rows = [row for row in groups['triggers'] if row['name'] == name]
            matched = len(rows) == 1
            if matched:
                row = rows[0]
                matched = (row['table'] == expected['table'] and row['function_namespace'] == namespace
                    and row['function_name'] == expected['function'] and row['function_arguments'] == ''
                    and row['type_bits'] == 27 and row['enabled'] == expected['enabled']
                    and row['internal'] is expected['internal'] and row['constraint'] is expected['constraint']
                    and row['argument_count'] == row['argument_bytes'] == 0 and row['has_when'] is False)
            checks.append({'check': 'trigger:' + name, 'matched': matched})
        return report('GUARD_CONTRACT_MATCHED' if all(check['matched'] for check in checks)
                      else 'GUARD_CONTRACT_MISMATCH', checks)
    except Exception:
        return report()
