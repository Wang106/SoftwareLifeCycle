export type ManufacturingSearch = Record<string, string | string[] | undefined>;
export type SiteRow = { id: string; site_code: string; name: string; region: string | null; status: string;
  customer_id: string; customer_code: string | null; customer_name: string | null; project_id: string; project_code: string | null; project_name: string | null;
  line_count: number; deployed_line_count: number; matching_line_count: number; attention_line_count: number };
export type SiteSummary = SiteRow & { kind: 'manufacturing-site'; approved_authorization_line_count: number;
  first_deployment_id: string | null; first_deployment_no: string | null; first_authorization_id: string | null; first_authorization_no: string | null; first_authorization_status: string | null;
  first_expected_release_id: string | null; first_expected_version: string | null; first_expected_type: string | null; first_expected_snapshot_id: string | null; first_expected_snapshot_no: string | null;
  first_changeover_id: string | null; first_changeover_changeover_no: string | null; first_changeover_status: string | null;
  context_batch_id: string | null; context_batch_batch_no: string | null; context_batch_status: string | null; context_batch_note: string | null };
export type LineRow = { id: string; line_code: string; name: string; status: string; deployment_id: string | null; deployment_no: string | null; deployment_status: string | null;
  authorization_id: string | null; authorization_no: string | null; authorization_status: string | null;
  expected_release_id: string | null; expected_version: string | null; expected_type: string | null; expected_snapshot_id: string | null; expected_snapshot_no: string | null;
  actual_release_id: string | null; actual_release_version: string | null; actual_type: string | null; actual_snapshot_id: string | null; actual_snapshot_no: string | null; actual_version: number | null; deployed_at: string | null };
export type ManufacturingPage<T> = { kind: string; site_id?: string; site_code?: string; total: number; limit: number; offset: number; next_offset: number | null; items: T[] };
export function manufacturingQuery(search: ManufacturingSearch, keys: string[]) {
  const query = new URLSearchParams();
  for (const key of keys) if (search[key] !== undefined) query.set(key, typeof search[key] === 'string' ? search[key] as string : 'invalid');
  return query;
}
export function siteMatches(identifier: string, row: SiteRow) {
  if (row.site_code === identifier) return true;
  const compact = identifier.replace('urn:uuid:', '').replace(/[{}-]/g, '');
  return /^[0-9a-f]{32}$/i.test(compact) && row.id.replaceAll('-', '').toLowerCase() === compact.toLowerCase();
}
