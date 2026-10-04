export type OrganizationKind = 'suppliers' | 'customers' | 'projects';
export type OrganizationSearch = Record<string, string | string[] | undefined>;
export type OrganizationRow = { id: string; code: string; name: string; status: string;
  country?: string | null; region?: string | null; website?: string | null; description?: string | null;
  software_count?: number; project_count?: number; released_project_count?: number; site_count?: number;
  customer_id?: string; customer_code?: string | null; customer_name?: string | null; vehicle_platform?: string | null;
  release_id?: string | null; release_version?: string | null; release_status?: string | null; type?: string | null };
export type OrganizationSummary = OrganizationRow & { kind: OrganizationKind };
export type OrganizationPage = { kind: OrganizationKind; organization_id?: string; total: number;
  limit: number; offset: number; next_offset: number | null; items: OrganizationRow[] };
export function organizationQuery(search: OrganizationSearch, keys: string[]) {
  const query = new URLSearchParams();
  for (const key of keys) if (search[key] !== undefined)
    query.set(key, typeof search[key] === 'string' ? search[key] as string : 'invalid');
  return query;
}

export function organizationMatches(kind: OrganizationKind, identifier: string, row: OrganizationSummary) {
  if (row.kind !== kind) return false;
  if (kind !== 'projects') return row.code === identifier;
  const compact = identifier.replace('urn:uuid:', '').replace(/[{}-]/g, '');
  return /^[0-9a-f]{32}$/i.test(compact) ? row.id.replaceAll('-', '').toLowerCase() === compact.toLowerCase() : row.code === identifier;
}
