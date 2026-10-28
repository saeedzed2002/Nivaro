'use client';

import createClient from 'openapi-fetch';
import type { paths, components } from './api/identity-schema';

export type IdentitySession = components['schemas']['SessionResponse'];
export type Address = components['schemas']['AddressResponse'];
export type AddressInput = components['schemas']['AddressInput'];
export type Challenge = components['schemas']['ChallengeResponse'];
export type Scope = 'customer' | 'admin';
export class IdentityError extends Error {
  constructor(public code: string, public status = 0, public retryAfter = 0) { super(code); }
}
const client = createClient<paths>({ baseUrl: '', credentials: 'same-origin', cache: 'no-store',
  fetch: async request => {
    try { return await fetch(request, { signal: AbortSignal.timeout(8000) }); }
    catch { throw new IdentityError('identity.unavailable'); }
  },
});
function unwrap<T>({ data, response, error }: { data?: T; response: Response; error?: unknown }): T {
  if (!response.ok) {
    const code = (error as components['schemas']['ErrorEnvelope'] | undefined)?.error?.code;
    throw new IdentityError(code || 'identity.unavailable', response.status, Number(response.headers.get('Retry-After') || 0));
  }
  return data as T;
}
async function current(scope: Scope): Promise<IdentitySession> {
  return unwrap(await client.GET(scope === 'admin' ? '/api/v1/admin/auth/session' : '/api/v1/auth/session'));
}
const pending: Partial<Record<Scope, Promise<IdentitySession>>> = {};
async function renew(scope: Scope): Promise<IdentitySession> {
  if (pending[scope]) return pending[scope];
  const work = async () => {
    // A different tab may have already updated the shared HttpOnly cookies.
    try { return await current(scope); } catch (e) { if (!(e instanceof IdentityError) || e.status !== 401) throw e; }
    const csrf = unwrap(await client.GET(scope === 'admin' ? '/api/v1/admin/auth/refresh/csrf' : '/api/v1/auth/refresh/csrf', { headers: { 'X-CSRF-Request': '1' } }));
    const response = await client.POST(scope === 'admin' ? '/api/v1/admin/auth/refresh' : '/api/v1/auth/refresh', { headers: { 'X-CSRF-Token': csrf.csrf_token } });
    if (response.response.status === 409) {
      // Bounded fallback for browsers without Web Locks. Never replay an old token.
      await new Promise(resolve => setTimeout(resolve, 350));
      return current(scope);
    }
    unwrap(response);
    return current(scope);
  };
  const promise = (async () => typeof navigator !== 'undefined' && navigator.locks
    ? await navigator.locks.request(`nivaro-refresh-${scope}`, work) : await work())();
  pending[scope] = promise;
  try { return await promise; } finally { delete pending[scope]; }
}
export async function readSession(scope: Scope = 'customer'): Promise<IdentitySession> {
  try { return await current(scope); }
  catch (e) { if (e instanceof IdentityError && e.status === 401) return renew(scope); throw e; }
}
async function authorized<T>(operation: (csrf: string) => Promise<T>, scope: Scope = 'customer'): Promise<T> {
  const state = await readSession(scope);
  try { return await operation(state.csrf_token); }
  catch (e) {
    if (!(e instanceof IdentityError) || e.status !== 401) throw e;
    const refreshed = await renew(scope);
    return operation(refreshed.csrf_token);
  }
}
export const requestCode = async (phone: string) => unwrap(await client.POST('/api/v1/auth/otp/request', { body: { phone } }));
export const verifyCode = async (phone: string, challenge_id: string, code: string) => unwrap(await client.POST('/api/v1/auth/otp/verify', { body: { phone, challenge_id, code } }));
export const adminLogin = async (email: string, password: string) => unwrap(await client.POST('/api/v1/admin/auth/login', { body: { email, password } }));
export const logout = (scope: Scope, all_devices: boolean) => authorized(async csrf => unwrap(await client.POST(scope === 'admin' ? '/api/v1/admin/auth/logout' : '/api/v1/auth/logout', { body: { all_devices }, headers: { 'X-CSRF-Token': csrf } })), scope);
export const saveProfile = (name: string) => authorized(async csrf => unwrap(await client.PATCH('/api/v1/me', { body: { name }, headers: { 'X-CSRF-Token': csrf } })));
export const listAddresses = () => authorized(async () => unwrap(await client.GET('/api/v1/me/addresses')));
export const saveAddress = (body: AddressInput, existing?: Address) => authorized(async csrf => existing
  ? unwrap(await client.PUT('/api/v1/me/addresses/{address_id}', { params: { path: { address_id: existing.id } }, body: { ...body, version: existing.version }, headers: { 'X-CSRF-Token': csrf } }))
  : unwrap(await client.POST('/api/v1/me/addresses', { body, headers: { 'X-CSRF-Token': csrf } })));
export const deleteAddress = (address: Address) => authorized(async csrf => unwrap(await client.DELETE('/api/v1/me/addresses/{address_id}', { params: { path: { address_id: address.id }, query: { version: address.version } }, headers: { 'X-CSRF-Token': csrf } })));
