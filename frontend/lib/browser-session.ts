import 'server-only';
import { projectRegistrationReceipt } from './admin-registration-transport';
import type { RegistrationReview } from './admin-registration-draft';

// Server-only session helpers; OIDC routes opt in with explicit operator configuration.
export const SESSION_COOKIE = '__Host-slc_session';
const MAX_AGE = 900;
const MAX_COOKIE = 3800;
const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });
type Environment = Record<string, string | undefined>;
export type SessionConfig = Readonly<{ origin: string; apiBase: string; key: string; binding: string }>;
export type Identity = {
  principal: { id: string; principal_type: 'USER' | 'SERVICE'; display_name: string };
  read_only_mode: boolean;
  active_grant_counts: { GLOBAL: number; PROJECT: number; SOFTWARE: number };
};
type Envelope = { v: 2; sid: string; binding: string; issued: number; expires: number; principal: string; token: string };

function encode(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function decode(value: string): Uint8Array {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) throw new Error('invalid_encoding');
  const bytes = Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
  if (encode(bytes) !== value) throw new Error('invalid_encoding');
  return bytes;
}
function endpoint(value: string | undefined, originOnly = false): string {
  if (!value) throw new Error('session_configuration_required');
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash ||
      (originOnly && url.pathname !== '/')) throw new Error('invalid_session_endpoint');
  return originOnly ? url.origin : url.href.replace(/\/$/, '');
}
export async function sessionConfig(env: Environment, providerBinding = ''): Promise<SessionConfig | null> {
  if (!env.BROWSER_SESSION_MODE || env.BROWSER_SESSION_MODE === 'disabled') return null;
  if (env.BROWSER_SESSION_MODE !== 'encrypted') throw new Error('invalid_session_mode');
  const key = env.BROWSER_SESSION_KEY || '';
  if (decode(key).length !== 32) throw new Error('invalid_session_key');
  const origin = endpoint(env.BROWSER_SESSION_ORIGIN, true);
  // Deliberately do not fall back to any NEXT_PUBLIC variable.
  const apiBase = endpoint(env.API_BASE_URL);
  const binding = encode(new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(JSON.stringify([origin, apiBase, providerBinding])))));
  return Object.freeze({ origin, apiBase, key, binding });
}
async function encryptionKey(config: SessionConfig) {
  return crypto.subtle.importKey('raw', decode(config.key) as BufferSource, 'AES-GCM', false, ['encrypt', 'decrypt']);
}
export async function sealCookie(config: SessionConfig, name: string, value: unknown): Promise<string | null> {
  const bytes = encoder.encode(JSON.stringify(value));
  if (bytes.length > 2700) return null;
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv, additionalData: encoder.encode(name) },
    await encryptionKey(config), bytes);
  const result = `v1.${encode(iv)}.${encode(new Uint8Array(ciphertext))}`;
  return result.length <= MAX_COOKIE ? result : null;
}
export async function openCookie(config: SessionConfig, name: string, value: string | undefined): Promise<unknown> {
  if (!value || value.length > MAX_COOKIE) return null;
  try {
    const parts = value.split('.');
    if (parts.length !== 3 || parts[0] !== 'v1') return null;
    const iv = decode(parts[1]); if (iv.length !== 12) return null;
    const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: iv as BufferSource,
      additionalData: encoder.encode(name) }, await encryptionKey(config), decode(parts[2]) as BufferSource);
    return JSON.parse(decoder.decode(new Uint8Array(plaintext)));
  } catch { return null; }
}
function validToken(token: string): boolean {
  return typeof token === 'string' && token.length > 0 && token.length <= 2400 && !/[\s\x00-\x1f\x7f]/.test(token);
}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function parseIdentity(value: unknown): Identity | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as Identity;
  if (!data.principal || typeof data.principal.id !== 'string' || !uuid.test(data.principal.id) ||
      !['USER', 'SERVICE'].includes(data.principal.principal_type) ||
      typeof data.principal.display_name !== 'string' || typeof data.read_only_mode !== 'boolean' ||
      !data.active_grant_counts || !['GLOBAL', 'PROJECT', 'SOFTWARE'].every(scope => {
        const count = data.active_grant_counts[scope as keyof Identity['active_grant_counts']];
        return Number.isSafeInteger(count) && count >= 0;
      })) return null;
  // Explicit projection: an upstream extra field can never disclose a token.
  return { principal: { id: data.principal.id, principal_type: data.principal.principal_type,
    display_name: data.principal.display_name }, read_only_mode: data.read_only_mode,
    active_grant_counts: { GLOBAL: data.active_grant_counts.GLOBAL, PROJECT: data.active_grant_counts.PROJECT,
      SOFTWARE: data.active_grant_counts.SOFTWARE } };
}
async function privateRequest(config: SessionConfig, path: string, token: string, fetcher: typeof fetch,
  options: RequestInit = {}, sessionId?: string, responseLimit = 16384): Promise<{ status: number; value: unknown } | null> {
  try {
    const response = await fetcher(`${config.apiBase}${path}`, { ...options,
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(sessionId ? { 'X-Browser-Session': sessionId } : {}) },
      cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(5000),
    });
    if (!response.headers.get('content-type')?.includes('application/json')) { await response.body?.cancel(); return null; }
    // Bound both declared and streamed size; never parse arbitrary provider bodies.
    if (Number(response.headers.get('content-length') || '0') > responseLimit) { await response.body?.cancel(); return null; }
    const reader = response.body?.getReader();
    if (!reader) return null;
    const chunks: Uint8Array[] = []; let size = 0;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > responseLimit) { await reader.cancel(); return null; }
        chunks.push(value);
      }
    } finally { reader.releaseLock(); }
    const bytes = new Uint8Array(size); let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
    return { status: response.status, value: JSON.parse(decoder.decode(bytes)) };
  } catch { return null; }
}
async function currentIdentity(config: SessionConfig, token: string, fetcher: typeof fetch, sessionId?: string): Promise<Identity | null> {
  const result = await privateRequest(config, '/api/v1/security/me', token, fetcher, {}, sessionId);
  if (!result || result.status !== 200) return null;
  if (sessionId && (!result.value || typeof result.value !== 'object' ||
      (result.value as { browser_session_id?: string }).browser_session_id !== sessionId)) return null;
  return parseIdentity(result.value);
}
export function sessionCookie(value: string, maxAge: number) {
  return { name: SESSION_COOKIE, value, httpOnly: true, secure: true, sameSite: 'lax' as const,
    path: '/', maxAge, priority: 'high' as const };
}
export function clearSessionCookie() { return sessionCookie('', 0); }

// Only call after provider code/PKCE/nonce and access-token expiration validation.
// The backend must also accept the access token before any session is issued.
export async function establishSession(config: SessionConfig, token: string, tokenExpires: number,
  fetcher: typeof fetch = fetch, now = Math.floor(Date.now() / 1000)) {
  if (!validToken(token) || !Number.isSafeInteger(now) || !Number.isSafeInteger(tokenExpires) || tokenExpires <= now) return null;
  const identity = await currentIdentity(config, token, fetcher);
  if (!identity || identity.principal.principal_type !== 'USER') return null;
  const expires = Math.min(tokenExpires, now + MAX_AGE);
  const sid = crypto.randomUUID();
  const registered = await privateRequest(config, '/api/v1/security/me/browser-sessions', token, fetcher,
    { method: 'POST', body: JSON.stringify({ id: sid, expires_at: expires }) });
  if (!registered || registered.status !== 200 || !registered.value || typeof registered.value !== 'object') return null;
  const record = registered.value as { id: string; expires_at: number };
  if (record.id !== sid || !Number.isSafeInteger(record.expires_at) || record.expires_at !== expires) return null;
  const envelope: Envelope = { v: 2, sid, binding: config.binding, issued: now, expires, principal: identity.principal.id, token };
  const value = await sealCookie(config, SESSION_COOKIE, envelope);
  if (!value) return null;
  return { cookie: sessionCookie(value, expires - now), identity };
}

export async function resolveSession(config: SessionConfig, value: string | undefined,
  fetcher: typeof fetch = fetch, now = Math.floor(Date.now() / 1000)): Promise<Identity | null> {
  if (!value || value.length > MAX_COOKIE || !Number.isSafeInteger(now)) return null;
  try {
    const envelope = await openCookie(config, SESSION_COOKIE, value) as Envelope | null;
    if (!envelope || envelope.v !== 2 || typeof envelope.sid !== 'string' || !uuid.test(envelope.sid) || envelope.binding !== config.binding || !Number.isSafeInteger(envelope.issued) ||
        !Number.isSafeInteger(envelope.expires) || envelope.issued > now || envelope.expires <= now ||
        envelope.expires <= envelope.issued || envelope.expires - envelope.issued > MAX_AGE ||
        typeof envelope.principal !== 'string' || !uuid.test(envelope.principal) || !validToken(envelope.token)) return null;
    const identity = await currentIdentity(config, envelope.token, fetcher, envelope.sid);
    return identity?.principal.id === envelope.principal && identity.principal.principal_type === 'USER' ? identity : null;
  } catch { return null; }
}

// Revoke before clearing browser cookies. Never claim success on an unconfirmed server failure.
export async function revokeSession(config: SessionConfig, value: string | undefined,
  fetcher: typeof fetch = fetch, now = Math.floor(Date.now() / 1000)): Promise<boolean> {
  const envelope = await openCookie(config, SESSION_COOKIE, value) as Envelope | null;
  if (!envelope || envelope.v !== 2 || typeof envelope.sid !== 'string' || !uuid.test(envelope.sid) ||
      envelope.binding !== config.binding || !validToken(envelope.token)) return true;
  if (Number.isSafeInteger(envelope.expires) && envelope.expires <= now) return true;
  const result = await privateRequest(config, `/api/v1/security/me/browser-sessions/${envelope.sid}/revoke`,
    envelope.token, fetcher, { method: 'POST' });
  if (!result || !result.value || typeof result.value !== 'object') return false;
  const body = result.value as { id?: string; status?: string; detail?: string };
  return (result.status === 200 && body.id === envelope.sid && body.status === 'revoked') ||
    (result.status === 404 && body.detail === 'session_not_found');
}


export type AdminGrant = {
  id: string; scope: 'GLOBAL' | 'PROJECT' | 'SOFTWARE'; role: string;
  status: 'ACTIVE' | 'SUSPENDED'; effective: boolean;
  principal: { id: string; display_name: string; status: 'ACTIVE' | 'DISABLED' };
  target: { id: string; code: string; name: string } | null;
};
export type AdminGrantResult =
  | { state: 'ready'; total: number; next_offset: number | null; items: AdminGrant[] }
  | { state: 'session_required' | 'forbidden' | 'unavailable' | 'invalid_filter' };

// A global grant count is not authorization. The backend checks PLATFORM_ADMIN
// for each catalog request, including server-session revocation and exact scope.
export async function readAdminGrants(config: SessionConfig, cookie: string | undefined,
  scope: string, status: string, offset: number, fetcher: typeof fetch = fetch): Promise<AdminGrantResult> {
  if (!['GLOBAL', 'PROJECT', 'SOFTWARE'].includes(scope) ||
      !['', 'ACTIVE', 'SUSPENDED'].includes(status) ||
      !Number.isSafeInteger(offset) || offset < 0 || offset > 100000)
    return { state: 'invalid_filter' };
  const identity = await resolveSession(config, cookie, fetcher);
  if (!identity) return { state: 'session_required' };
  const envelope = await openCookie(config, SESSION_COOKIE, cookie) as Envelope;
  const query = new URLSearchParams({ scope, limit: '10', offset: String(offset) });
  if (status) query.set('status', status);
  const result = await privateRequest(config, '/api/v1/security/admin/grants?' + query,
    envelope.token, fetcher, {}, envelope.sid);
  if (!result) return { state: 'unavailable' };
  if (result.status === 401) return { state: 'session_required' };
  if (result.status === 403) return { state: 'forbidden' };
  if (result.status !== 200 || !result.value || typeof result.value !== 'object') return { state: 'unavailable' };
  const data = result.value as Record<string, unknown>;
  if (data.scope !== scope || data.limit !== 10 || data.offset !== offset ||
      !Number.isSafeInteger(data.total) || (data.total as number) < 0 ||
      !(data.next_offset === null || (Number.isSafeInteger(data.next_offset) &&
        (data.next_offset as number) === offset + 10 && (data.next_offset as number) <= 100000)) ||
      !Array.isArray(data.items) || data.items.length > 10 ||
      data.items.length > (data.total as number)) return { state: 'unavailable' };
  const items: AdminGrant[] = [];
  for (const row of data.items) {
    if (!row || typeof row !== 'object' || typeof row.id !== 'string' || !uuid.test(row.id) ||
        row.scope !== scope || typeof row.role !== 'string' || row.role.length > 100 ||
        !['ACTIVE', 'SUSPENDED'].includes(row.status) || (status && row.status !== status) ||
        typeof row.effective !== 'boolean' || !row.principal ||
        typeof row.principal.id !== 'string' || !uuid.test(row.principal.id) ||
        typeof row.principal.display_name !== 'string' ||
        !['ACTIVE', 'DISABLED'].includes(row.principal.status)) return { state: 'unavailable' };
    if (scope === 'GLOBAL' ? row.target !== null : (!row.target ||
        typeof row.target.id !== 'string' || !uuid.test(row.target.id) ||
        typeof row.target.code !== 'string' || typeof row.target.name !== 'string')) return { state: 'unavailable' };
    // Explicit projection: never pass a cookie, token or arbitrary backend JSON to React.
    items.push({ id: row.id, scope: row.scope, role: row.role, status: row.status,
      effective: row.effective, principal: { id: row.principal.id,
        display_name: row.principal.display_name, status: row.principal.status },
      target: row.target === null ? null : { id: row.target.id, code: row.target.code, name: row.target.name } });
  }
  return { state: 'ready', total: data.total as number,
    next_offset: data.next_offset as number | null, items };
}


export type GrantHistoryEvent = {
  id: string; event_no: string; action: string; occurred_at: string;
  actor_principal_id: string | null; actor_display_name: string | null;
  expected_status: 'ACTIVE' | 'SUSPENDED' | null; status: 'ACTIVE' | 'SUSPENDED' | null;
  reason: string | null; reason_truncated: boolean;
};
export type GrantDetailResult =
  | { state: 'ready'; grant: AdminGrant; read_only_mode: boolean; current_status: 'ACTIVE' | 'SUSPENDED';
      coverage: string; total: number; next_offset: number | null; items: GrantHistoryEvent[] }
  | { state: 'session_required' | 'forbidden' | 'unavailable' | 'invalid_filter' | 'not_found' };
function adminReadFailure(result: { status: number; value: unknown } | null) {
  return result?.status === 401 ? 'session_required' as const :
    result?.status === 403 ? 'forbidden' as const :
    result?.status === 404 ? 'not_found' as const : 'unavailable' as const;
}
function projectExactGrant(value: unknown, scope: string, id: string): AdminGrant | null {
  if (!value || typeof value !== 'object') return null;
  const row = value as AdminGrant;
  if (row.id !== id || row.scope !== scope || typeof row.role !== 'string' || row.role.length > 100 ||
      !['ACTIVE', 'SUSPENDED'].includes(row.status) || typeof row.effective !== 'boolean' ||
      !row.principal || typeof row.principal.id !== 'string' || !uuid.test(row.principal.id) ||
      typeof row.principal.display_name !== 'string' ||
      !['ACTIVE', 'DISABLED'].includes(row.principal.status)) return null;
  if (scope === 'GLOBAL' ? row.target !== null : (!row.target ||
      typeof row.target.id !== 'string' || !uuid.test(row.target.id) ||
      typeof row.target.code !== 'string' || typeof row.target.name !== 'string')) return null;
  return { id: row.id, scope: row.scope, role: row.role, status: row.status, effective: row.effective,
    principal: { id: row.principal.id, display_name: row.principal.display_name, status: row.principal.status },
    target: row.target === null ? null : { id: row.target.id, code: row.target.code, name: row.target.name } };
}
export async function readAdminGrantDetail(config: SessionConfig, cookie: string | undefined,
  scope: string, id: string, offset: number, fetcher: typeof fetch = fetch): Promise<GrantDetailResult> {
  if (!['GLOBAL', 'PROJECT', 'SOFTWARE'].includes(scope) || !uuid.test(id) ||
      !Number.isSafeInteger(offset) || offset < 0 || offset > 100000) return { state: 'invalid_filter' };
  // UUID paths are canonical, not version/name based; response identity must match.
  id = id.toLowerCase();
  const identity = await resolveSession(config, cookie, fetcher);
  if (!identity) return { state: 'session_required' };
  const envelope = await openCookie(config, SESSION_COOKIE, cookie) as Envelope;
  const path = '/api/v1/security/admin/grants/' + scope + '/' + id;
  const detail = await privateRequest(config, path, envelope.token, fetcher, {}, envelope.sid);
  if (!detail || detail.status !== 200) return { state: adminReadFailure(detail) };
  const grant = projectExactGrant(detail.value, scope, id);
  if (!grant) return { state: 'unavailable' };
  const result = await privateRequest(config, path + '/history?limit=10&offset=' + offset,
    envelope.token, fetcher, {}, envelope.sid, 32768);
  if (!result || result.status !== 200) return { state: adminReadFailure(result) };
  if (!result.value || typeof result.value !== 'object') return { state: 'unavailable' };
  const data = result.value as Record<string, unknown>;
  const coverage = scope === 'GLOBAL' ? 'GLOBAL_ROLE_STATUS_CHANGED_ONLY' : 'MEMBERSHIP_STATUS_CHANGED_ONLY';
  if (data.scope !== scope || data.grant_id !== id || data.coverage !== coverage ||
      !['ACTIVE', 'SUSPENDED'].includes(data.current_status as string) ||
      data.limit !== 10 || data.offset !== offset || !Number.isSafeInteger(data.total) ||
      (data.total as number) < 0 || !Array.isArray(data.items) || data.items.length > 10 ||
      data.items.length > (data.total as number) ||
      !(data.next_offset === null || (data.next_offset === offset + 10 && offset + 10 <= 100000)))
    return { state: 'unavailable' };
  const items: GrantHistoryEvent[] = [];
  for (const row of data.items) {
    if (!row || typeof row !== 'object' || typeof row.id !== 'string' || !uuid.test(row.id) ||
        typeof row.event_no !== 'string' || typeof row.action !== 'string' ||
        typeof row.occurred_at !== 'string' || !Number.isFinite(Date.parse(row.occurred_at)) ||
        !(row.actor_principal_id === null || (typeof row.actor_principal_id === 'string' && uuid.test(row.actor_principal_id))) ||
        !(row.actor_display_name === null || typeof row.actor_display_name === 'string') ||
        ![null, 'ACTIVE', 'SUSPENDED'].includes(row.expected_status) ||
        ![null, 'ACTIVE', 'SUSPENDED'].includes(row.status) ||
        !(row.reason === null || (typeof row.reason === 'string' && row.reason.length <= 500)) ||
        typeof row.reason_truncated !== 'boolean') return { state: 'unavailable' };
    items.push({ id: row.id, event_no: row.event_no, action: row.action, occurred_at: row.occurred_at,
      actor_principal_id: row.actor_principal_id, actor_display_name: row.actor_display_name,
      expected_status: row.expected_status, status: row.status, reason: row.reason,
      reason_truncated: row.reason_truncated });
  }
  // Detail and history are independent READ COMMITTED snapshots; retain both statuses.
  return { state: 'ready', grant, read_only_mode: identity.read_only_mode, current_status: data.current_status as 'ACTIVE' | 'SUSPENDED',
    coverage, total: data.total as number, next_offset: data.next_offset as number | null, items };
}


// Server-only transport for an already validated, exact grant status command.
// No retries: a missing/invalid receipt after POST means the outcome is unknown.
export type GrantStatusCommand = Readonly<{ scope: 'GLOBAL' | 'PROJECT' | 'SOFTWARE'; grant_id: string;
  event_no: string; expected_status: 'ACTIVE' | 'SUSPENDED'; status: 'ACTIVE' | 'SUSPENDED'; reason: string }>;
export async function submitGrantStatus(config: SessionConfig, cookie: string | undefined,
  command: GrantStatusCommand, fetcher: typeof fetch = fetch): Promise<{ status: number; value: unknown }> {
  const identity = await resolveSession(config, cookie, fetcher);
  if (!identity) return { status: 401, value: { error: 'session_required' } };
  if (identity.read_only_mode) return { status: 403, value: { error: 'read_only_mode' } };
  const envelope = await openCookie(config, SESSION_COOKIE, cookie) as Envelope;
  const path = command.scope === 'GLOBAL' ? '/api/v1/security/admin/global-roles/' + command.grant_id + '/status' :
    '/api/v1/security/admin/memberships/' + command.scope + '/' + command.grant_id + '/status';
  const body = { event_no: command.event_no, expected_status: command.expected_status,
    status: command.status, reason: command.reason };
  // Backend independently checks PLATFORM_ADMIN, active issuer/actor/session,
  // expected state, actor-bound replay, last-admin protection and atomic audit.
  const result = await privateRequest(config, path, envelope.token, fetcher,
    { method: 'POST', body: JSON.stringify(body) }, envelope.sid);
  const unknown = { status: 502, value: { error: 'outcome_unknown' } };
  if (!result) return unknown;
  if (result.status === 200 && result.value && typeof result.value === 'object') {
    const data = result.value as Record<string, unknown>;
    const target = command.scope === 'GLOBAL' ? data.grant_id : data.membership_id;
    if (typeof target !== 'string' || target.toLowerCase() !== command.grant_id || data.scope !== command.scope ||
        data.audit_event_no !== command.event_no || data.applied_status !== command.status ||
        !['ACTIVE', 'SUSPENDED'].includes(data.current_status as string) || typeof data.replayed !== 'boolean') return unknown;
    return { status: 200, value: { grant_id: command.grant_id, scope: command.scope,
      audit_event_no: command.event_no, applied_status: data.applied_status, current_status: data.current_status,
      replayed: data.replayed } };
  }
  const denied: Record<number, string> = { 401: 'session_required', 403: 'submission_forbidden',
    404: 'grant_not_found', 422: 'invalid_request' };
  if (denied[result.status]) return { status: result.status, value: { error: denied[result.status] } };
  if (result.status === 409) {
    const detail = result.value && typeof result.value === 'object' ?
      (result.value as Record<string, unknown>).detail : undefined;
    const known = ['audit_event_conflict', 'membership_status_conflict', 'global_role_status_conflict',
      'recipient_inactive', 'recipient_issuer_mismatch', 'last_active_admin_protected'];
    return { status: 409, value: { error: typeof detail === 'string' && known.includes(detail) ? detail : 'submission_conflict' } };
  }
  return unknown;
}

// Only accepts a canonical server-prepared registration review. Backend remains
// authoritative for PLATFORM_ADMIN, recipients, uniqueness and atomic audit.
export async function submitAdminRegistration(config: SessionConfig, cookie: string | undefined,
  review: RegistrationReview, fetcher: typeof fetch = fetch): Promise<{ status: number; value: unknown }> {
  const identity = await resolveSession(config, cookie, fetcher);
  if (!identity) return { status: 401, value: { error: 'session_required' } };
  if (identity.read_only_mode) return { status: 403, value: { error: 'read_only_mode' } };
  const envelope = await openCookie(config, SESSION_COOKIE, cookie) as Envelope;
  const result = await privateRequest(config, review.request.path, envelope.token, fetcher,
    { method: 'POST', body: JSON.stringify(review.request.body) }, envelope.sid);
  const unknown = { status: 502, value: { error: 'outcome_unknown' } };
  if (!result) return unknown;
  if (result.status === 200) {
    const receipt = projectRegistrationReceipt(result.value, review, true);
    return receipt ? { status: 200, value: receipt } : unknown;
  }
  const denied: Record<number, string> = { 401: 'session_required', 403: 'submission_forbidden',
    404: 'registration_target_not_found', 422: 'invalid_request' };
  if (denied[result.status]) return { status: result.status, value: { error: denied[result.status] } };
  const detail = result.value && typeof result.value === 'object' ?
    (result.value as Record<string, unknown>).detail : undefined;
  if (result.status === 409) {
    const known = ['audit_event_conflict','principal_registration_conflict','global_role_registration_conflict',
      'membership_registration_conflict','recipient_inactive','recipient_issuer_mismatch','admin_recipient_protected'];
    return { status: 409, value: { error: typeof detail === 'string' && known.includes(detail) ? detail : 'submission_conflict' } };
  }
  if (result.status === 503 && detail === 'configured_issuer_required')
    return { status: 503, value: { error: 'configured_issuer_required' } };
  return unknown;
}

