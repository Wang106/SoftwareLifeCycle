export const governanceKinds = ['RELEASE', 'DELIVERY_PACKAGE', 'DISTRIBUTION', 'AUTHORIZATION'] as const;
export type GovernanceKind = typeof governanceKinds[number];
export type RevocationRecord = {
  id: string; revocation_no: string; target_kind: GovernanceKind;
  reason: string; revoked_by: string; revoked_at: string;
};
export type GovernanceObservation = {
  recorded_status: string | null;
  governance_state: 'ACTIVE' | 'REVOKED' | 'BLOCKED_BY_ANCESTOR' | 'UNRESOLVED';
  eligible_for_new_work: boolean;
  self_revocation: RevocationRecord | null;
  ancestor_revocations: RevocationRecord[];
};
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export function governanceTarget(kind: string, id: string): {kind: GovernanceKind; id: string} | null {
  const normalized = kind.toUpperCase() as GovernanceKind;
  return governanceKinds.includes(normalized) && uuid.test(id) ? {kind: normalized, id: id.toLowerCase()} : null;
}

/** The permanent ledger permits one event per node: at most four on an exact path. */
export function parseGovernance(value: unknown, kind: GovernanceKind): GovernanceObservation | null {
  if (!object(value) || !(value.recorded_status === null ||
      (typeof value.recorded_status === 'string' && value.recorded_status.length <= 30)) ||
      typeof value.eligible_for_new_work !== 'boolean' || !Array.isArray(value.ancestor_revocations)) return null;
  const depth = governanceKinds.indexOf(kind);
  if (value.ancestor_revocations.length > depth) return null;
  function record(item: unknown): item is RevocationRecord {
    return object(item) && typeof item.id === 'string' && uuid.test(item.id) &&
      item.revocation_no === `RCR-${item.id.replaceAll('-', '').toLowerCase()}` &&
      governanceKinds.includes(item.target_kind as GovernanceKind) &&
      typeof item.reason === 'string' && item.reason.trim().length > 0 && item.reason.length <= 4000 &&
      typeof item.revoked_by === 'string' && item.revoked_by.length > 0 && item.revoked_by.length <= 120 &&
      typeof item.revoked_at === 'string' && item.revoked_at.length <= 64 &&
      /^\d{4}-\d{2}-\d{2}T/.test(item.revoked_at) && Number.isFinite(Date.parse(item.revoked_at));
  }
  const own = value.self_revocation;
  if (!(own === null || (record(own) && own.target_kind === kind))) return null;
  if (!value.ancestor_revocations.every(item => record(item) && governanceKinds.indexOf(item.target_kind) < depth)) return null;
  const ancestors = value.ancestor_revocations as RevocationRecord[];
  const events = own === null ? ancestors : [own as RevocationRecord, ...ancestors];
  if (new Set(events.map(item => item.id.toLowerCase())).size !== events.length ||
      new Set(events.map(item => item.target_kind)).size !== events.length) return null;
  const expected = own ? 'REVOKED' : ancestors.length ? 'BLOCKED_BY_ANCESTOR' : 'ACTIVE';
  if (value.governance_state === 'UNRESOLVED') {
    if (value.eligible_for_new_work || events.length) return null;
  } else if (value.governance_state !== expected || value.eligible_for_new_work !== (expected === 'ACTIVE')) return null;
  return value as unknown as GovernanceObservation;
}
