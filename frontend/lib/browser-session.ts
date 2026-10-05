import 'server-only';

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
type Envelope = { v: 1; binding: string; issued: number; expires: number; principal: string; token: string };

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
async function currentIdentity(config: SessionConfig, token: string, fetcher: typeof fetch): Promise<Identity | null> {
  try {
    const response = await fetcher(`${config.apiBase}/api/v1/security/me`, {
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
      cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(5000),
    });
    if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) return null;
    // Bound both declared and streamed size; never parse arbitrary provider bodies.
    if (Number(response.headers.get('content-length') || '0') > 16384) { await response.body?.cancel(); return null; }
    const reader = response.body?.getReader();
    if (!reader) return null;
    const chunks: Uint8Array[] = []; let size = 0;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > 16384) { await reader.cancel(); return null; }
        chunks.push(value);
      }
    } finally { reader.releaseLock(); }
    const bytes = new Uint8Array(size); let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
    return parseIdentity(JSON.parse(decoder.decode(bytes)));
  } catch { return null; }
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
  const envelope: Envelope = { v: 1, binding: config.binding, issued: now, expires, principal: identity.principal.id, token };
  const value = await sealCookie(config, SESSION_COOKIE, envelope);
  if (!value) return null;
  return { cookie: sessionCookie(value, expires - now), identity };
}

export async function resolveSession(config: SessionConfig, value: string | undefined,
  fetcher: typeof fetch = fetch, now = Math.floor(Date.now() / 1000)): Promise<Identity | null> {
  if (!value || value.length > MAX_COOKIE || !Number.isSafeInteger(now)) return null;
  try {
    const envelope = await openCookie(config, SESSION_COOKIE, value) as Envelope | null;
    if (!envelope || envelope.v !== 1 || envelope.binding !== config.binding || !Number.isSafeInteger(envelope.issued) ||
        !Number.isSafeInteger(envelope.expires) || envelope.issued > now || envelope.expires <= now ||
        envelope.expires <= envelope.issued || envelope.expires - envelope.issued > MAX_AGE ||
        typeof envelope.principal !== 'string' || !uuid.test(envelope.principal) || !validToken(envelope.token)) return null;
    const identity = await currentIdentity(config, envelope.token, fetcher);
    return identity?.principal.id === envelope.principal && identity.principal.principal_type === 'USER' ? identity : null;
  } catch { return null; }
}
