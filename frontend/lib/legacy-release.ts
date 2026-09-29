import { apiGet } from './api';

type ReleaseRecord = { id: string; version: string };

/** Resolve old version-based URLs only when they identify exactly one real ASR. */
export async function legacyReleaseTarget(id: string, suffix = ''): Promise<string> {
  if (id === 'demo') return '/releases/application';
  const releases = await apiGet<ReleaseRecord[]>('/api/v1/releases/application');
  const matches = releases?.filter(row => row.id === id || row.version === id) || [];
  return matches.length === 1
    ? `/releases/application/${encodeURIComponent(matches[0].id)}${suffix}`
    : '/releases/application';
}
