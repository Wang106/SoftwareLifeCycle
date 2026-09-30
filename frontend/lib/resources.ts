export type Resource = { id: string; entity_type: string; entity_id: string; entity_ref: string; entity_href: string; title: string; location_kind: string; location: string; description: string; actor_name: string; reason: string; created_at: string };
export function safeWebLocation(row: Resource): string | null {
  if (row.location_kind !== 'WEB_URL' || !/^https?:\/\//.test(row.location) || /[\s\\]/.test(row.location)) return null;
  try { const url = new URL(row.location); return url.username || url.password ? null : row.location; } catch { return null; }
}
export const entityTypes = ['SUPPLIER', 'CUSTOMER', 'PROJECT', 'RELEASE', 'SNAPSHOT', 'SCR', 'ISSUE', 'DVP_ITEM', 'TEST_RELEASE', 'DVP_EXECUTION'];
