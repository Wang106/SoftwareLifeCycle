"""Compare frozen manifests without consulting mutable source artifacts."""


class SnapshotComparisonError(ValueError):
    pass


FIELDS = ('artifact_type', 'component_version', 'sha256', 'classification',
          'distribution_level', 'ai_access_policy', 'policy_rules')


def _index(manifest):
    result = {}
    for artifact in manifest:
        key = (artifact['component_code'], artifact['filename'])
        if key in result:
            raise SnapshotComparisonError(
                f'Ambiguous frozen file identity: {key[0]} / {key[1]}')
        value = {field: artifact.get(field) for field in FIELDS}
        # Database row IDs and rule ordering are not policy changes.
        value['policy_rules'] = sorted(artifact.get('policy_rules', []), key=lambda rule: (
            rule['recipient_type'], rule['purpose'], rule.get('recipient_code') or '', rule['decision']))
        result[key] = value
    return result


def compare_manifests(before, after):
    source, target = _index(before), _index(after)
    summary = dict.fromkeys(('added', 'removed', 'modified', 'unchanged'), 0)
    files = []
    for component, filename in sorted(source.keys() | target.keys()):
        old, new = source.get((component, filename)), target.get((component, filename))
        changed = [field for field in FIELDS if old and new and old[field] != new[field]]
        kind = 'added' if old is None else 'removed' if new is None else 'modified' if changed else 'unchanged'
        summary[kind] += 1
        files.append({'component_code': component, 'filename': filename, 'change_type': kind,
                      'changed_fields': changed, 'before': old, 'after': new})
    return {'summary': summary, 'files': files}
