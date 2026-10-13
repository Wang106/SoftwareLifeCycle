import identities from './demo-family-identities.json';

type State = 'confirmed' | 'unavailable' | 'invalid' | 'incomplete' | 'mismatch';
type Family = {state: State; records: number | null; expectedRecords: number};
function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}
function family(value: unknown, expected: Record<string, string>, key: 'source_ref' | 'version'): Family {
  const expectedRecords = Object.keys(expected).length;
  const empty = (state: State): Family => ({state, records: null, expectedRecords});
  if (value == null) return empty('unavailable');
  const data = object(value);
  if (!data || data.sample_only !== true || typeof data.initialized !== 'boolean' || !Array.isArray(data.items)
    || data.items.length > expectedRecords) return empty('invalid');
  const seen = new Set<string>();
  for (const item of data.items) {
    const row = object(item), label = row?.[key];
    if (!row || typeof label !== 'string' || !Object.prototype.hasOwnProperty.call(expected, label)
      || row.release_id !== expected[label] || seen.has(label)
      || row.release_type !== ((key === 'source_ref' ? label.startsWith('SSR') : label.includes('-SSR-')) ? 'STANDARD' : 'APPLICATION'))
      return empty('invalid');
    if (key === 'source_ref' && data.initialized && row.approval_no !== 'APR-ZFI-' + label) return empty('invalid');
    seen.add(label);
  }
  if (data.initialized && (data.items.length !== expectedRecords
    || (key === 'source_ref' && (data.synthetic_approvals !== true || data.import_event_no !== 'EVT-ZFI-IMPORT-V1'))))
    return empty('invalid');
  return {state: data.initialized ? 'confirmed' : 'incomplete', records: data.items.length, expectedRecords};
}

/** Fixed sample identities and current read contract only; never certifies a release or a browser. */
export function inspectDemoStatus(health: unknown, excel: unknown, evidence: unknown) {
  const observed = object(health);
  const version = typeof observed?.version === 'string' && observed.version.length <= 32 && /^\d+\.\d+\.\d+$/.test(observed.version) ? observed.version : null;
  const revision = typeof observed?.database_revision === 'string' && /^[a-zA-Z0-9_]{1,128}$/.test(observed.database_revision) ? observed.database_revision : null;
  let state: State;
  if (health == null) state = 'unavailable';
  else if (!observed || (observed.status !== 'ready' && observed.status !== 'not_ready')) state = 'invalid';
  else if (observed.status === 'not_ready') state = 'incomplete';
  else if (!version || !revision) state = 'invalid';
  else state = version === identities.api_version && revision === identities.database_revision ? 'confirmed' : 'mismatch';
  const api = {state, version, revision, expectedVersion: identities.api_version, expectedRevision: identities.database_revision};
  const excelFamily = family(excel, identities.excel, 'source_ref');
  const evidenceFamily = family(evidence, identities.evidence, 'version');
  const excelCheck = {...excelFamily,
    standard: excelFamily.records === null ? null : (object(excel)!.items as Record<string, unknown>[]).filter(r => r.release_type === 'STANDARD').length,
    application: excelFamily.records === null ? null : (object(excel)!.items as Record<string, unknown>[]).filter(r => r.release_type === 'APPLICATION').length};
  return {api, excel: excelCheck, evidence: evidenceFamily,
    allConfirmed: api.state === 'confirmed' && excelCheck.state === 'confirmed' && evidenceFamily.state === 'confirmed'};
}
