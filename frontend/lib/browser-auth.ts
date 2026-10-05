import 'server-only';
import { createLocalJWKSet, jwtVerify, type JSONWebKeySet } from 'jose';
import { SESSION_COOKIE, sessionConfig, sessionCookie, clearSessionCookie, sealCookie,
  openCookie, establishSession, resolveSession, revokeSession, type SessionConfig } from './browser-session';

export const LOGIN_COOKIE = '__Host-slc_login';
const LOGIN_AGE = 300;
type Environment = Record<string, string | undefined>;
export type AuthConfig = Readonly<{
  session: SessionConfig; issuer: string; audience: string; clientId: string;
  authorization: string; token: string; jwks: string; scope: string;
  clientAuth: 'none' | 'client_secret_basic'; secret: string;
}>;
type LoginTransaction = { v: 1; binding: string; issued: number; expires: number;
  state: string; nonce: string; verifier: string };
export type AuthOperation = 'login' | 'callback' | 'session' | 'logout';
const encoder = new TextEncoder();
function base64url(bytes: Uint8Array) {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function random() { return base64url(crypto.getRandomValues(new Uint8Array(32))); }
function equal(left: string, right: string) {
  const a = encoder.encode(left), b = encoder.encode(right);
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a[i] || 0) ^ (b[i] || 0);
  return diff === 0;
}
function setting(value: string | undefined, max = 2048): string {
  if (!value || value.length > max || /[\x00-\x20\x7f]/.test(value)) throw new Error('invalid_auth_configuration');
  return value;
}
function https(value: string | undefined): string {
  const raw = setting(value), url = new URL(raw);
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) throw new Error('invalid_auth_endpoint');
  // Issuer matching is exact, including a configured trailing slash.
  if (url.href !== raw && url.origin !== raw) throw new Error('noncanonical_auth_endpoint');
  return raw;
}
export async function authConfig(env: Environment): Promise<AuthConfig | null> {
  if (!env.BROWSER_OIDC_MODE || env.BROWSER_OIDC_MODE === 'disabled') return null;
  if (env.BROWSER_OIDC_MODE !== 'code') throw new Error('invalid_auth_mode');
  const issuer = https(env.OIDC_ISSUER_URL), audience = setting(env.OIDC_AUDIENCE);
  const clientId = setting(env.OIDC_CLIENT_ID, 256);
  const authorization = https(env.OIDC_AUTHORIZATION_URL), token = https(env.OIDC_TOKEN_URL), jwks = https(env.OIDC_JWKS_URL);
  const scope = env.OIDC_SCOPE || 'openid';
  if (scope.length > 1024 || !/^\S+( \S+)*$/.test(scope) || !scope.split(' ').includes('openid') ||
      scope.split(' ').includes('offline_access') || !/^[A-Za-z0-9_:/. -]+$/.test(scope)) throw new Error('invalid_auth_scope');
  const clientAuth = env.OIDC_CLIENT_AUTH || 'none';
  if (clientAuth !== 'none' && clientAuth !== 'client_secret_basic') throw new Error('invalid_client_auth');
  const secret = env.OIDC_CLIENT_SECRET || '';
  if (clientAuth === 'client_secret_basic') setting(secret);
  else if (secret) throw new Error('unexpected_client_secret');
  const binding = JSON.stringify([issuer, audience, clientId, authorization, token, jwks, scope, clientAuth, secret]);
  const session = await sessionConfig(env, binding);
  if (!session) throw new Error('session_configuration_required');
  return Object.freeze({ session, issuer, audience, clientId, authorization, token, jwks, scope, clientAuth, secret });
}
const privateHeaders = {
  'Cache-Control': 'private, no-store', Pragma: 'no-cache', Vary: 'Cookie',
  'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff',
};
function json(error: string, status: number) { return Response.json({ error }, { status, headers: privateHeaders }); }
function redirect(url: string) { return new Response(null, { status: 303, headers: { ...privateHeaders, Location: url } }); }
function setCookie(response: Response, cookie: ReturnType<typeof sessionCookie>) {
  response.headers.append('Set-Cookie', `${cookie.name}=${cookie.value}; Path=/; Max-Age=${cookie.maxAge}; HttpOnly; Secure; SameSite=Lax; Priority=High`);
}
function loginCookie(value = '', maxAge = 0) { return { ...sessionCookie(value, maxAge), name: LOGIN_COOKIE }; }
function readCookie(request: Request, name: string): string | undefined {
  const cookies = (request.headers.get('cookie') || '').split(';').map(part => part.trim());
  const matches = cookies.filter(part => part.startsWith(`${name}=`));
  // Never select one of two conflicting cookie values.
  return matches.length === 1 ? matches[0].slice(name.length + 1) : undefined;
}
function sameOrigin(request: Request, config: AuthConfig): boolean {
  const site = request.headers.get('sec-fetch-site');
  return new URL(request.url).origin === config.session.origin && request.headers.get('origin') === config.session.origin &&
    (!site || site === 'same-origin' || site === 'none');
}
async function fetchJson(fetcher: typeof fetch, url: string, options: RequestInit, limit = 32768): Promise<unknown> {
  const response = await fetcher(url, { ...options, redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(5000) });
  const contentType = response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() || '';
  if (!response.ok || (contentType !== 'application/json' && !contentType.endsWith('+json')) ||
      Number(response.headers.get('content-length') || '0') > limit) {
    await response.body?.cancel(); throw new Error('invalid_auth_response');
  }
  const reader = response.body?.getReader(); if (!reader) throw new Error('missing_auth_response');
  const chunks: Uint8Array[] = []; let size = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read(); if (done) break;
      size += value.length;
      if (size > limit) { await reader.cancel(); throw new Error('auth_response_too_large'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
}
async function readTransaction(config: AuthConfig, value: string | undefined, now: number): Promise<LoginTransaction | null> {
  const tx = await openCookie(config.session, LOGIN_COOKIE, value) as LoginTransaction | null;
  if (!tx || tx.v !== 1 || tx.binding !== config.session.binding || !Number.isSafeInteger(tx.issued) ||
      !Number.isSafeInteger(tx.expires) || tx.issued > now || tx.expires <= now || tx.expires - tx.issued !== LOGIN_AGE ||
      ![tx.state, tx.nonce, tx.verifier].every(value => typeof value === 'string' && /^[A-Za-z0-9_-]{43}$/.test(value))) return null;
  return tx;
}
async function startLogin(config: AuthConfig, now: number): Promise<Response> {
  const tx: LoginTransaction = { v: 1, binding: config.session.binding, issued: now, expires: now + LOGIN_AGE,
    state: random(), nonce: random(), verifier: random() };
  const value = await sealCookie(config.session, LOGIN_COOKIE, tx); if (!value) return json('login_failed', 401);
  const challenge = base64url(new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(tx.verifier))));
  const url = new URL(config.authorization);
  const params = { response_type: 'code', response_mode: 'query', client_id: config.clientId,
    redirect_uri: `${config.session.origin}/auth/callback`, scope: config.scope, state: tx.state,
    nonce: tx.nonce, code_challenge: challenge, code_challenge_method: 'S256' };
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  const response = redirect(url.href); setCookie(response, loginCookie(value, LOGIN_AGE)); return response;
}
async function halfHash(value: string) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(value)));
  return base64url(digest.slice(0, digest.length / 2));
}
function formEncode(value: string) { return new URLSearchParams({ v: value }).toString().slice(2); }
async function completeLogin(request: Request, config: AuthConfig, fetcher: typeof fetch, now: number): Promise<Response> {
  const url = new URL(request.url), query = url.searchParams;
  const allowed = new Set(['code', 'state', 'iss', 'session_state', 'error', 'error_description', 'error_uri']);
  if (request.url.length > 8192 || [...query.keys()].some(key => !allowed.has(key) || query.getAll(key).length !== 1) ||
      url.origin !== config.session.origin) return json('invalid_callback', 400);
  const tx = await readTransaction(config, readCookie(request, LOGIN_COOKIE), now);
  const state = query.get('state'), code = query.get('code');
  if (!tx || !state || state.length !== 43 || !equal(state, tx.state) ||
      (query.has('iss') && query.get('iss') !== config.issuer)) return json('invalid_callback', 400);
  if (query.has('error')) return json('login_failed', 401);
  if (!code || code.length > 4096 || /[\x00-\x20\x7f]/.test(code)) return json('invalid_callback', 400);
  const body = new URLSearchParams({ grant_type: 'authorization_code', code, redirect_uri: `${config.session.origin}/auth/callback`,
    client_id: config.clientId, code_verifier: tx.verifier });
  const headers: Record<string, string> = { Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded' };
  if (config.clientAuth === 'client_secret_basic') headers.Authorization = `Basic ${btoa(`${formEncode(config.clientId)}:${formEncode(config.secret)}`)}`;
  const tokens = await fetchJson(fetcher, config.token, { method: 'POST', headers, body }) as Record<string, unknown>;
  if (!tokens || typeof tokens.access_token !== 'string' || tokens.access_token.length > 2400 ||
      typeof tokens.id_token !== 'string' || tokens.id_token.length > 16384 ||
      typeof tokens.token_type !== 'string' || tokens.token_type.toLowerCase() !== 'bearer' ||
      (tokens.expires_in !== undefined && (!Number.isSafeInteger(tokens.expires_in) || (tokens.expires_in as number) <= 0))) return json('login_failed', 401);
  const jwks = await fetchJson(fetcher, config.jwks, { headers: { Accept: 'application/jwk-set+json, application/json' } }, 65536) as JSONWebKeySet;
  if (!jwks || !Array.isArray(jwks.keys) || jwks.keys.length < 1 || jwks.keys.length > 64) return json('login_failed', 401);
  const keys = createLocalJWKSet(jwks);
  const common = { issuer: config.issuer, algorithms: ['RS256'], currentDate: new Date(now * 1000), clockTolerance: 0,
    requiredClaims: ['iss', 'aud', 'sub', 'iat', 'exp'] };
  const id = (await jwtVerify(tokens.id_token, keys, { ...common, audience: config.clientId, maxTokenAge: 600,
    requiredClaims: [...common.requiredClaims, 'nonce'] })).payload;
  const access = (await jwtVerify(tokens.access_token, keys, { ...common, audience: config.audience })).payload;
  if (typeof id.sub !== 'string' || !id.sub.trim() || id.sub.length > 500 || access.sub !== id.sub ||
      typeof id.nonce !== 'string' || !equal(id.nonce, tx.nonce) ||
      !Number.isSafeInteger(id.iat) || id.iat! < tx.issued - 60 || id.iat! > now ||
      !Number.isSafeInteger(access.iat) || access.iat! > now || !Number.isSafeInteger(access.exp) ||
      (Array.isArray(id.aud) && id.aud.length > 1 && id.azp !== config.clientId) ||
      (id.azp !== undefined && id.azp !== config.clientId) || (access.azp !== undefined && access.azp !== config.clientId) ||
      (id.at_hash !== undefined && (typeof id.at_hash !== 'string' || !equal(id.at_hash, await halfHash(tokens.access_token)))) ||
      (id.c_hash !== undefined && (typeof id.c_hash !== 'string' || !equal(id.c_hash, await halfHash(code))))) return json('login_failed', 401);
  const expires = Math.min(access.exp!, id.exp!, tokens.expires_in === undefined ? Infinity : now + (tokens.expires_in as number));
  // Do not spend network time as usable cookie lifetime.
  const completedAt = Math.max(now, Math.floor(Date.now() / 1000));
  if (completedAt >= tx.expires) return json('login_failed', 401);
  const session = await establishSession(config.session, tokens.access_token, expires, fetcher, completedAt);
  if (!session) return json('login_failed', 401);
  const response = redirect(`${config.session.origin}/account`); setCookie(response, session.cookie); return response;
}
export async function handleAuth(request: Request, operation: AuthOperation, env: Environment,
  fetcher: typeof fetch = fetch): Promise<Response> {
  const expected = operation === 'login' || operation === 'logout' ? 'POST' : 'GET';
  if (request.method !== expected) { const response = json('method_not_allowed', 405); response.headers.set('Allow', expected); return response; }
  let response: Response;
  let configuration: AuthConfig | null = null;
  try {
    const config = configuration = await authConfig(env);
    if (!config) response = json('login_not_configured', 503);
    else if ((operation === 'login' || operation === 'logout') && !sameOrigin(request, config)) response = json('invalid_origin', 403);
    else if (operation === 'login') response = await startLogin(config, Math.floor(Date.now() / 1000));
    else if (operation === 'callback') response = await completeLogin(request, config, fetcher, Math.floor(Date.now() / 1000));
    else if (operation === 'logout') {
      if (!await revokeSession(config.session, readCookie(request, SESSION_COOKIE), fetcher)) response = json('logout_unavailable', 503);
      else { response = redirect(`${config.session.origin}/account`); setCookie(response, clearSessionCookie()); setCookie(response, loginCookie()); }
    } else {
      if (new URL(request.url).origin !== config.session.origin) response = json('invalid_origin', 403);
      else {
        const identity = await resolveSession(config.session, readCookie(request, SESSION_COOKIE), fetcher);
        response = identity ? Response.json(identity, { headers: privateHeaders }) : json('session_required', 401);
        if (!identity) setCookie(response, clearSessionCookie());
      }
    }
  } catch { response = json('login_failed', 401); }
  // Browser errors return to the translated account page without provider text/code.
  if (operation === 'callback' && response.status >= 400 && configuration && request.headers.get('accept')?.includes('text/html')) {
    response = redirect(`${configuration.session.origin}/account?auth=failed`);
  }
  if (operation === 'logout' && response.status === 503 && configuration && request.headers.get('accept')?.includes('text/html')) {
    response = redirect(`${configuration.session.origin}/account?auth=logout_failed`);
  }
  // Consume the browser's pending cookie on every callback, including errors.
  // Authorization code one-use is enforced by the provider; no refresh tokens are retained.
  if (operation === 'callback') setCookie(response, loginCookie());
  return response;
}
