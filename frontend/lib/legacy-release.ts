import { apiGet } from './api';

type Resolution = { state: 'unique' | 'ambiguous' | 'missing'; release: { id: string; version: string } | null };

/** Resolve exact UUID/version matches without loading a release directory. */
export async function legacyReleaseTarget(id: string, suffix = ''): Promise<string> {
  if (id === 'demo') return '/releases/application';
  const result = await apiGet<Resolution>(`/api/v1/release-catalog/application/resolve?${new URLSearchParams({identifier: id})}`);
  return result?.state === 'unique' && result.release
    ? `/releases/application/${encodeURIComponent(result.release.id)}${suffix}`
    : '/releases/application';
}
