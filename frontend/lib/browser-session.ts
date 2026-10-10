import {parseAcceptanceCorrectionCommand,acceptanceCorrectionPath,acceptanceCorrectionEvent,type AcceptanceCorrectionCommand} from './acceptance-correction-transport';
import {projectAcceptanceCorrectionAudit} from './acceptance-correction-audit';
import {parseEvidenceCommand,evidencePath,evidenceEvent,type EvidenceCommand} from './evidence-command-transport';
import {projectEvidenceAudit} from './evidence-command-audit';
import {parseResourceCommand,resourcePath,resourceEvent,type ResourceCommand} from './resource-command-transport';
import {projectResourceAudit} from './resource-command-audit';
import { parseProductionCommand, productionPath, productionEvent, type ProductionCommand } from './production-command-transport';
import { projectProductionAudit } from './production-command-audit';
import { parseDistributionCommand, distributionPath, distributionEvent, type DistributionCommand } from './distribution-command-transport';
import { projectDistributionAudit } from './distribution-command-audit';
import { parseGovernanceCommand, governancePath, governanceEvent, type GovernanceCommand } from './governance-command-transport';
import { projectGovernanceAudit } from './governance-command-audit';
import 'server-only';
import { parseFirstCommand, firstCommandPath, firstCommandEvent, type FirstCommand } from './first-command-transport';
import { projectFirstAudit } from './first-command-audit';
import { parsePrincipalStatusCommand, projectPrincipalStatusReceipt, type PrincipalStatusCommand } from './principal-status-transport';
import { projectRegistrationReceipt } from './admin-registration-transport';
import type { RegistrationReview } from './admin-registration-draft';

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
  | { state: 'ready'; read_only_mode: boolean; total: number; next_offset: number | null; items: AdminGrant[] }
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
  return { state: 'ready', read_only_mode: identity.read_only_mode, total: data.total as number,
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


export type AdminPrincipal = {
  id: string; principal_type: 'USER' | 'SERVICE'; display_name: string;
  status: 'ACTIVE' | 'DISABLED'; created_at: string;
  issuer_matches_configuration: boolean; admin_principal_protected: boolean;
};
export type PrincipalHistoryEvent = Omit<GrantHistoryEvent, 'expected_status' | 'status'> & {
  expected_status: 'ACTIVE' | 'DISABLED' | null; status: 'ACTIVE' | 'DISABLED' | null;
};
type PrincipalReadFailure = { state: 'session_required' | 'forbidden' | 'unavailable' | 'invalid_filter' | 'not_found' };
type PrincipalPage = { total: number; next_offset: number | null; navigation_limited: boolean };
export type PrincipalCatalogResult = PrincipalReadFailure |
  ({ state: 'ready'; read_only_mode: boolean; items: AdminPrincipal[] } & PrincipalPage);
export type PrincipalDetailResult = PrincipalReadFailure |
  ({ state: 'ready'; read_only_mode: boolean; principal: AdminPrincipal;
     current_status: 'ACTIVE' | 'DISABLED'; items: PrincipalHistoryEvent[] } & PrincipalPage);

function principalReadFailure(result: { status: number; value: unknown } | null) {
  if (result?.status === 404) return result.value && typeof result.value === 'object' &&
    (result.value as { detail?: unknown }).detail === 'principal_not_found' ? 'not_found' as const : 'unavailable' as const;
  return adminReadFailure(result);
}
function boundedText(value: unknown, max: number): value is string {
  return typeof value === 'string' && Array.from(value).length <= max;
}
function projectPrincipal(value: unknown): AdminPrincipal | null {
  if (!value || typeof value !== 'object') return null;
  const row = value as Record<string, unknown>;
  if (typeof row.id !== 'string' || !uuid.test(row.id) ||
      !['USER', 'SERVICE'].includes(row.principal_type as string) ||
      !boundedText(row.display_name, 200) ||
      !['ACTIVE', 'DISABLED'].includes(row.status as string) ||
      !boundedText(row.created_at, 64) || !Number.isFinite(Date.parse(row.created_at)) ||
      typeof row.issuer_matches_configuration !== 'boolean' ||
      typeof row.admin_principal_protected !== 'boolean' || row.status_history_supported !== true) return null;
  return { id: row.id.toLowerCase(), principal_type: row.principal_type as 'USER' | 'SERVICE',
    display_name: row.display_name, status: row.status as 'ACTIVE' | 'DISABLED', created_at: row.created_at,
    issuer_matches_configuration: row.issuer_matches_configuration,
    admin_principal_protected: row.admin_principal_protected };
}
function principalPage(value: unknown, offset: number): (PrincipalPage & { rows: unknown[] }) | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as Record<string, unknown>, total = data.total as number;
  if (data.limit !== 10 || data.offset !== offset || !Number.isSafeInteger(total) || total < 0 ||
      !Array.isArray(data.items) || data.items.length !== Math.max(0, Math.min(10, total-offset)) ||
      data.next_offset !== (offset+10 < total ? offset+10 : null)) return null;
  // The API may report a next offset beyond its accepted query budget. Keep the last
  // valid page readable without generating a link that the API will reject.
  const limited = typeof data.next_offset === 'number' && data.next_offset > 100000;
  return { total, next_offset: limited ? null : data.next_offset as number | null,
    navigation_limited: limited, rows: data.items };
}
export async function readAdminPrincipals(config: SessionConfig, cookie: string | undefined,
  principalId: string, kind: string, status: string, offset: number,
  fetcher: typeof fetch = fetch): Promise<PrincipalCatalogResult> {
  if ((principalId && !uuid.test(principalId)) || !['', 'USER', 'SERVICE'].includes(kind) ||
      !['', 'ACTIVE', 'DISABLED'].includes(status) ||
      !Number.isSafeInteger(offset) || offset < 0 || offset > 100000) return { state: 'invalid_filter' };
  const identity = await resolveSession(config, cookie, fetcher);
  if (!identity) return { state: 'session_required' };
  const envelope = await openCookie(config, SESSION_COOKIE, cookie) as Envelope;
  const query = new URLSearchParams({ limit: '10', offset: String(offset) });
  if (principalId) query.set('principal_id', principalId.toLowerCase());
  if (kind) query.set('principal_type', kind);
  if (status) query.set('status', status);
  const result = await privateRequest(config, '/api/v1/security/admin/principals?'+query,
    envelope.token, fetcher, {}, envelope.sid);
  if (!result || result.status !== 200) return { state: result?.status === 404 ? 'unavailable' : principalReadFailure(result) };
  const page = principalPage(result.value, offset);
  if (!page) return { state: 'unavailable' };
  const items: AdminPrincipal[] = [], seen = new Set<string>();
  for (const row of page.rows) {
    const item = projectPrincipal(row);
    if (!item || seen.has(item.id) || (principalId && item.id !== principalId.toLowerCase()) ||
        (kind && item.principal_type !== kind) || (status && item.status !== status)) return { state: 'unavailable' };
    seen.add(item.id); items.push(item);
  }
  return { state: 'ready', read_only_mode: identity.read_only_mode, total: page.total,
    next_offset: page.next_offset, navigation_limited: page.navigation_limited, items };
}
export async function readAdminPrincipalDetail(config: SessionConfig, cookie: string | undefined,
  id: string, offset: number, fetcher: typeof fetch = fetch): Promise<PrincipalDetailResult> {
  if (!uuid.test(id) || !Number.isSafeInteger(offset) || offset < 0 || offset > 100000)
    return { state: 'invalid_filter' };
  id = id.toLowerCase();
  const identity = await resolveSession(config, cookie, fetcher);
  if (!identity) return { state: 'session_required' };
  const envelope = await openCookie(config, SESSION_COOKIE, cookie) as Envelope;
  const path = '/api/v1/security/admin/principals/'+id;
  const detail = await privateRequest(config, path, envelope.token, fetcher, {}, envelope.sid);
  if (!detail || detail.status !== 200) return { state: principalReadFailure(detail) };
  const principal = projectPrincipal(detail.value);
  if (!principal || principal.id !== id) return { state: 'unavailable' };
  const history = await privateRequest(config, path+'/history?limit=10&offset='+offset,
    envelope.token, fetcher, {}, envelope.sid, 32768);
  if (!history || history.status !== 200) return { state: principalReadFailure(history) };
  const data = history.value as Record<string, unknown> | null;
  const page = principalPage(data, offset);
  if (!page || data?.principal_id !== id || data.coverage !== 'PRINCIPAL_STATUS_CHANGED_ONLY' ||
      !['ACTIVE', 'DISABLED'].includes(data.current_status as string)) return { state: 'unavailable' };
  const items: PrincipalHistoryEvent[] = [], seen = new Set<string>();
  for (const value of page.rows) {
    if (!value || typeof value !== 'object') return { state: 'unavailable' };
    const row = value as Record<string, unknown>;
    if (typeof row.id !== 'string' || !uuid.test(row.id) || seen.has(row.id.toLowerCase()) ||
        !boundedText(row.event_no, 50) || !boundedText(row.action, 100) ||
        !boundedText(row.occurred_at, 64) || !Number.isFinite(Date.parse(row.occurred_at)) ||
        !(row.actor_principal_id === null || (typeof row.actor_principal_id === 'string' && uuid.test(row.actor_principal_id))) ||
        !(row.actor_display_name === null || boundedText(row.actor_display_name, 255)) ||
        ![null, 'ACTIVE', 'DISABLED'].includes(row.expected_status as string | null) ||
        ![null, 'ACTIVE', 'DISABLED'].includes(row.status as string | null) ||
        !(row.reason === null || boundedText(row.reason, 500)) || typeof row.reason_truncated !== 'boolean')
      return { state: 'unavailable' };
    seen.add(row.id.toLowerCase());
    items.push({ id: row.id.toLowerCase(), event_no: row.event_no, action: row.action, occurred_at: row.occurred_at,
      actor_principal_id: row.actor_principal_id as string | null, actor_display_name: row.actor_display_name as string | null,
      expected_status: row.expected_status as 'ACTIVE' | 'DISABLED' | null,
      status: row.status as 'ACTIVE' | 'DISABLED' | null, reason: row.reason as string | null,
      reason_truncated: row.reason_truncated });
  }
  return { state: 'ready', principal, read_only_mode: identity.read_only_mode,
    current_status: data.current_status as 'ACTIVE' | 'DISABLED', total: page.total,
    next_offset: page.next_offset, navigation_limited: page.navigation_limited, items };
}

// Fixed identity status route; credentials remain in the sealed server-side session.
export async function submitPrincipalStatus(config: SessionConfig, cookie: string | undefined,
  input: PrincipalStatusCommand, fetcher: typeof fetch = fetch): Promise<{ status: number; value: unknown }> {
  const command = parsePrincipalStatusCommand(input);
  if (!command) return { status: 400, value: { error: 'invalid_request' } };
  const identity = await resolveSession(config, cookie, fetcher);
  if (!identity) return { status: 401, value: { error: 'session_required' } };
  if (identity.read_only_mode) return { status: 403, value: { error: 'read_only_mode' } };
  const envelope = await openCookie(config, SESSION_COOKIE, cookie) as Envelope;
  const { principal_id, ...body } = command;
  // Backend independently verifies current administrator, protected identities,
  // expected status, actor-bound replay and atomic audit/session revocation.
  const result = await privateRequest(config, '/api/v1/security/admin/principals/' + principal_id + '/status',
    envelope.token, fetcher, { method: 'POST', body: JSON.stringify(body) }, envelope.sid);
  const unknown = { status: 502, value: { error: 'outcome_unknown' } };
  if (!result) return unknown;
  if (result.status === 200) {
    const receipt = projectPrincipalStatusReceipt(result.value, command, true);
    return receipt ? { status: 200, value: receipt } : unknown;
  }
  const denied: Record<number, string> = { 401: 'session_required', 403: 'submission_forbidden', 422: 'invalid_request' };
  if (denied[result.status]) return { status: result.status, value: { error: denied[result.status] } };
  const detail = result.value && typeof result.value === 'object' ?
    (result.value as Record<string, unknown>).detail : undefined;
  // An unsupported API route is unavailable, not proof that this UUID is absent.
  if (result.status === 404 && detail === 'principal_not_found')
    return { status: 404, value: { error: 'principal_not_found' } };
  if (result.status === 409) {
    const known = ['audit_event_conflict', 'principal_status_conflict', 'admin_principal_protected'];
    return { status: 409, value: { error: typeof detail === 'string' && known.includes(detail) ? detail : 'submission_conflict' } };
  }
  return unknown;
}


// Three fixed business command paths. Recovery only reads the original atomic audit.
export async function executeFirstCommand(config: SessionConfig, cookie: string | undefined,
  input: FirstCommand, mode: 'submit' | 'recover', fetcher: typeof fetch = fetch): Promise<{ status: number; value: unknown }> {
  const command = parseFirstCommand(input);
  if (!command || !['submit', 'recover'].includes(mode)) return { status: 400, value: { error: 'invalid_request' } };
  const identity = await resolveSession(config, cookie, fetcher);
  if (!identity) return { status: 401, value: { error: 'session_required' } };
  // A read-only switch does not erase an already committed own-operation receipt.
  if (mode === 'submit' && identity.read_only_mode) return { status: 403, value: { error: 'read_only_mode' } };
  const envelope = await openCookie(config, SESSION_COOKIE, cookie) as Envelope;
  const unknown = { status: 502, value: { error: 'outcome_unknown' } };
  if (mode === 'submit') {
    const result = await privateRequest(config, firstCommandPath(command), envelope.token, fetcher,
      { method: 'POST', body: JSON.stringify(command.body) }, envelope.sid);
    if (!result) return unknown;
    const expectedStatus = command.operation === 'actual' ? 200 : 201;
    if (result.status !== expectedStatus) {
      const denied: Record<number, string> = { 401: 'session_required', 403: 'submission_forbidden', 422: 'invalid_request' };
      if (denied[result.status]) return { status: result.status, value: { error: denied[result.status] } };
      if (result.status === 409) {
        const detail = result.value && typeof result.value === 'object' ? (result.value as Record<string, unknown>).detail : null;
        const error = typeof detail === 'string' && /^request_id (already used|or business number already exists)/.test(detail) ? 'request_conflict' :
          typeof detail === 'string' && /^actual_version conflict: expected [0-9]+, current [0-9]+$/.test(detail) ? 'version_conflict' : 'submission_conflict';
        return { status: 409, value: { error } };
      }
      return unknown;
    }
  }
  // No query of current object status can prove this original command's result.
  const audit = await privateRequest(config, '/api/v1/activity/' + firstCommandEvent(command),
    envelope.token, fetcher, {}, envelope.sid);
  if (!audit || audit.status !== 200) return unknown;
  const receipt = projectFirstAudit(audit.value, command, identity.principal.id);
  return receipt ? { status: 200, value: receipt } : unknown;
}


// Two fixed approval/decision paths. Recovery only reads the original atomic audit.
export async function executeGovernanceCommand(config: SessionConfig, cookie: string | undefined,
  input: GovernanceCommand, mode: 'submit' | 'recover', fetcher: typeof fetch = fetch): Promise<{ status: number; value: unknown }> {
  const command = parseGovernanceCommand(input);
  if (!command || !['submit', 'recover'].includes(mode)) return { status: 400, value: { error: 'invalid_request' } };
  const identity = await resolveSession(config, cookie, fetcher);
  if (!identity) return { status: 401, value: { error: 'session_required' } };
  // A read-only switch does not erase an already committed own-operation receipt.
  if (mode === 'submit' && identity.read_only_mode) return { status: 403, value: { error: 'read_only_mode' } };
  const envelope = await openCookie(config, SESSION_COOKIE, cookie) as Envelope;
  const unknown = { status: 502, value: { error: 'outcome_unknown' } };
  if (mode === 'submit') {
    const result = await privateRequest(config, governancePath(command), envelope.token, fetcher,
      { method: 'POST', body: JSON.stringify(command.body) }, envelope.sid);
    if (!result) return unknown;
    const expectedStatus = command.operation === 'approval' ? 200 : 201;
    if (result.status !== expectedStatus) {
      const denied: Record<number, string> = { 401: 'session_required', 403: 'submission_forbidden', 422: 'invalid_request' };
      if (denied[result.status]) return { status: result.status, value: { error: denied[result.status] } };
      if (result.status === 409) {
        const detail = result.value && typeof result.value === 'object' ? (result.value as Record<string, unknown>).detail : null;
        const error = typeof detail === 'string' && /^request_id (already used|or business number already exists)/.test(detail) ? 'request_conflict' :
          detail === 'expected_step_id does not match the active approval step' ? 'step_conflict' : 'submission_conflict';
        return { status: 409, value: { error } };
      }
      return unknown;
    }
  }
  // No query of current object status can prove this original command's result.
  const audit = await privateRequest(config, '/api/v1/activity/' + governanceEvent(command),
    envelope.token, fetcher, {}, envelope.sid);
  if (!audit || audit.status !== 200) return unknown;
  const receipt = projectGovernanceAudit(audit.value, command, identity.principal.id);
  return receipt ? { status: 200, value: receipt } : unknown;
}


export async function executeDistributionCommand(config: SessionConfig, cookie: string | undefined,
  input: DistributionCommand, mode: 'submit' | 'recover', fetcher: typeof fetch = fetch): Promise<{ status: number; value: unknown }> {
  const command = parseDistributionCommand(input);
  if (!command || !['submit', 'recover'].includes(mode)) return { status: 400, value: { error: 'invalid_request' } };
  const identity = await resolveSession(config, cookie, fetcher);
  if (!identity) return { status: 401, value: { error: 'session_required' } };
  // A read-only switch does not erase an already committed own-operation receipt.
  if (mode === 'submit' && identity.read_only_mode) return { status: 403, value: { error: 'read_only_mode' } };
  const envelope = await openCookie(config, SESSION_COOKIE, cookie) as Envelope;
  const unknown = { status: 502, value: { error: 'outcome_unknown' } };
  if (mode === 'submit') {
    const result = await privateRequest(config, distributionPath(command), envelope.token, fetcher,
      { method: 'POST', body: JSON.stringify(command.body) }, envelope.sid);
    if (!result) return unknown;
    const expectedStatus = 201;
    if (result.status !== expectedStatus) {
      const denied: Record<number, string> = { 401: 'session_required', 403: 'submission_forbidden', 422: 'invalid_request' };
      if (denied[result.status]) return { status: result.status, value: { error: denied[result.status] } };
      if (result.status === 409) {
        const detail = result.value && typeof result.value === 'object' ? (result.value as Record<string, unknown>).detail : null;
        const error = typeof detail === 'string' && /^request_id (already used|or business number already exists)/.test(detail) ? 'request_conflict'  : 'submission_conflict';
        return { status: 409, value: { error } };
      }
      return unknown;
    }
  }
  // No query of current object status can prove this original command's result.
  const audit = await privateRequest(config, '/api/v1/activity/' + distributionEvent(command),
    envelope.token, fetcher, {}, envelope.sid);
  if (!audit || audit.status !== 200) return unknown;
  const receipt = projectDistributionAudit(audit.value, command, identity.principal.id);
  return receipt ? { status: 200, value: receipt } : unknown;
}


export async function executeProductionCommand(config: SessionConfig, cookie: string | undefined,
  input: ProductionCommand, mode: 'submit' | 'recover', fetcher: typeof fetch = fetch): Promise<{ status: number; value: unknown }> {
  const command = parseProductionCommand(input);
  if (!command || !['submit', 'recover'].includes(mode)) return { status: 400, value: { error: 'invalid_request' } };
  const identity = await resolveSession(config, cookie, fetcher);
  if (!identity) return { status: 401, value: { error: 'session_required' } };
  // A read-only switch does not erase an already committed own-operation receipt.
  if (mode === 'submit' && identity.read_only_mode) return { status: 403, value: { error: 'read_only_mode' } };
  const envelope = await openCookie(config, SESSION_COOKIE, cookie) as Envelope;
  const unknown = { status: 502, value: { error: 'outcome_unknown' } };
  if (mode === 'submit') {
    const result = await privateRequest(config, productionPath(command), envelope.token, fetcher,
      { method: 'POST', body: JSON.stringify(command.body) }, envelope.sid);
    if (!result) return unknown;
    const expectedStatuses = command.operation === 'test-release' ? [200,201] : [201];
    if (!expectedStatuses.includes(result.status)) {
      const denied: Record<number, string> = { 401: 'session_required', 403: 'submission_forbidden', 422: 'invalid_request' };
      if (denied[result.status]) return { status: result.status, value: { error: denied[result.status] } };
      if (result.status === 409) {
        const detail = result.value && typeof result.value === 'object' ? (result.value as Record<string, unknown>).detail : null;
        const error = typeof detail === 'string' && /^request_id (already used|or business number already exists)/.test(detail) ? 'request_conflict'  : 'submission_conflict';
        return { status: 409, value: { error } };
      }
      return unknown;
    }
  }
  // No query of current object status can prove this original command's result.
  const audit = await privateRequest(config, '/api/v1/activity/' + productionEvent(command),
    envelope.token, fetcher, {}, envelope.sid);
  if (!audit || audit.status !== 200) return unknown;
  const receipt = projectProductionAudit(audit.value, command, identity.principal.id);
  return receipt ? { status: 200, value: receipt } : unknown;
}


export async function executeResourceCommand(config: SessionConfig, cookie: string | undefined,
  input: ResourceCommand, mode: 'submit' | 'recover', fetcher: typeof fetch = fetch): Promise<{ status: number; value: unknown }> {
  const command = parseResourceCommand(input);
  if (!command || !['submit', 'recover'].includes(mode)) return { status: 400, value: { error: 'invalid_request' } };
  const identity = await resolveSession(config, cookie, fetcher);
  if (!identity) return { status: 401, value: { error: 'session_required' } };
  // A read-only switch does not erase an already committed own-operation receipt.
  if (mode === 'submit' && identity.read_only_mode) return { status: 403, value: { error: 'read_only_mode' } };
  const envelope = await openCookie(config, SESSION_COOKIE, cookie) as Envelope;
  const unknown = { status: 502, value: { error: 'outcome_unknown' } };
  if (mode === 'submit') {
    const result = await privateRequest(config, resourcePath(command), envelope.token, fetcher,
      { method: 'POST', body: JSON.stringify(command.body) }, envelope.sid);
    if (!result) return unknown;
    const expectedStatuses = [200,201];
    if (!expectedStatuses.includes(result.status)) {
      const denied: Record<number, string> = { 401: 'session_required', 403: 'submission_forbidden', 422: 'invalid_request' };
      if (denied[result.status]) return { status: result.status, value: { error: denied[result.status] } };
      if (result.status === 409) {
        const detail = result.value && typeof result.value === 'object' ? (result.value as Record<string, unknown>).detail : null;
        const error = typeof detail === 'string' && /^(request ID already used|resource request conflict)/.test(detail) ? 'request_conflict'  : 'submission_conflict';
        return { status: 409, value: { error } };
      }
      return unknown;
    }
  }
  // No query of current object status can prove this original command's result.
  const audit = await privateRequest(config, '/api/v1/activity/' + resourceEvent(command),
    envelope.token, fetcher, {}, envelope.sid);
  if (!audit || audit.status !== 200) return unknown;
  const receipt = await projectResourceAudit(audit.value, command, identity.principal.id);
  return receipt ? { status: 200, value: receipt } : unknown;
}


export async function executeEvidenceCommand(config: SessionConfig, cookie: string | undefined,
  input: EvidenceCommand, mode: 'submit' | 'recover', fetcher: typeof fetch = fetch): Promise<{ status: number; value: unknown }> {
  const command = parseEvidenceCommand(input);
  if (!command || !['submit', 'recover'].includes(mode)) return { status: 400, value: { error: 'invalid_request' } };
  const identity = await resolveSession(config, cookie, fetcher);
  if (!identity) return { status: 401, value: { error: 'session_required' } };
  // A read-only switch does not erase an already committed own-operation receipt.
  if (mode === 'submit' && identity.read_only_mode) return { status: 403, value: { error: 'read_only_mode' } };
  const envelope = await openCookie(config, SESSION_COOKIE, cookie) as Envelope;
  const unknown = { status: 502, value: { error: 'outcome_unknown' } };
  if (mode === 'submit') {
    const result = await privateRequest(config, evidencePath(command), envelope.token, fetcher,
      { method: 'POST', body: JSON.stringify(command.body) }, envelope.sid);
    if (!result) return unknown;
    const expectedStatuses = [200,201];
    if (!expectedStatuses.includes(result.status)) {
      const denied: Record<number, string> = { 401: 'session_required', 403: 'submission_forbidden', 422: 'invalid_request' };
      if (denied[result.status]) return { status: result.status, value: { error: denied[result.status] } };
      if (result.status === 409) {
        const detail = result.value && typeof result.value === 'object' ? (result.value as Record<string, unknown>).detail : null;
        const error = typeof detail === 'string' && /^(request_id already used|assignment request conflict)/.test(detail) ? 'request_conflict'  : 'submission_conflict';
        return { status: 409, value: { error } };
      }
      return unknown;
    }
  }
  // No query of current object status can prove this original command's result.
  const audit = await privateRequest(config, '/api/v1/activity/' + evidenceEvent(command),
    envelope.token, fetcher, {}, envelope.sid);
  if (!audit || audit.status !== 200) return unknown;
  const receipt = await projectEvidenceAudit(audit.value, command, identity.principal.id);
  return receipt ? { status: 200, value: receipt } : unknown;
}

export async function executeAcceptanceCorrectionCommand(config: SessionConfig, cookie: string | undefined,
  input: AcceptanceCorrectionCommand, mode: 'submit' | 'recover', fetcher: typeof fetch = fetch): Promise<{ status: number; value: unknown }> {
  const command = parseAcceptanceCorrectionCommand(input);
  if (!command || !['submit', 'recover'].includes(mode)) return { status: 400, value: { error: 'invalid_request' } };
  const identity = await resolveSession(config, cookie, fetcher);
  if (!identity) return { status: 401, value: { error: 'session_required' } };
  // A read-only switch does not erase an already committed own-operation receipt.
  if (mode === 'submit' && identity.read_only_mode) return { status: 403, value: { error: 'read_only_mode' } };
  const envelope = await openCookie(config, SESSION_COOKIE, cookie) as Envelope;
  const unknown = { status: 502, value: { error: 'outcome_unknown' } };
  if (mode === 'submit') {
    const result = await privateRequest(config, acceptanceCorrectionPath(command), envelope.token, fetcher,
      { method: 'POST', body: JSON.stringify(command.body) }, envelope.sid);
    if (!result) return unknown;
    const expectedStatuses = [200,201];
    if (!expectedStatuses.includes(result.status)) {
      const denied: Record<number, string> = { 401: 'session_required', 403: 'submission_forbidden', 422: 'invalid_request' };
      if (denied[result.status]) return { status: result.status, value: { error: denied[result.status] } };
      if (result.status === 409) {
        const detail = result.value && typeof result.value === 'object' ? (result.value as Record<string, unknown>).detail : null;
        const error = typeof detail === 'string' && /^(request_id already used|assignment request conflict)/.test(detail) ? 'request_conflict'  : 'submission_conflict';
        return { status: 409, value: { error } };
      }
      return unknown;
    }
  }
  // No query of current object status can prove this original command's result.
  const audit = await privateRequest(config, '/api/v1/activity/' + acceptanceCorrectionEvent(command),
    envelope.token, fetcher, {}, envelope.sid);
  if (!audit || audit.status !== 200) return unknown;
  const receipt = await projectAcceptanceCorrectionAudit(audit.value, command, identity.principal.id);
  return receipt ? { status: 200, value: receipt } : unknown;
}


// Server-only session helpers; OIDC routes opt in with explicit operator configuration.

