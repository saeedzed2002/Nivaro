'use client';

import createClient from 'openapi-fetch';
import type { components, paths } from './api/identity-schema';
import { authorized, IdentityError } from './identity-client';

export type Account = components['schemas']['AccountSummary'];
export type AuditEvent = components['schemas']['AccountAudit'];
export type RoleChange = components['schemas']['RoleChange']['role'];
export type AccountKind = 'customer' | 'staff';

const client = createClient<paths>({
  credentials: 'same-origin',
  cache: 'no-store',
  fetch: async request => {
    try { return await fetch(request, { signal: AbortSignal.any([request.signal, AbortSignal.timeout(8_000)]) }); }
    catch (error) {
      if (request.signal.aborted) throw error;
      throw new IdentityError('identity.unavailable');
    }
  },
});

function unwrap<T>({ response, data, error }: { response: Response; data?: T; error?: unknown }) {
  if (response.ok && data) return data;
  const detail = error as components['schemas']['ErrorEnvelope'] | undefined;
  throw new IdentityError(detail?.error?.code ?? 'identity.unavailable', response.status);
}

export function listAccounts(kind?: AccountKind, disabled?: boolean, before?: string, signal?: AbortSignal) {
  return authorized(async () => unwrap(await client.GET('/api/v1/admin/users', {
    params: { query: { kind, disabled, before } }, signal,
  })), 'admin');
}

export function getAccount(id: string, signal?: AbortSignal) {
  return authorized(async () => unwrap(await client.GET('/api/v1/admin/users/{user_id}', {
    params: { path: { user_id: id } }, signal,
  })), 'admin');
}

export function listAccountAudit(id: string, before?: string, signal?: AbortSignal) {
  return authorized(async () => unwrap(await client.GET('/api/v1/admin/users/audit', {
    params: { query: { target: id, before } }, signal,
  })), 'admin');
}

export function changeAccountRole(account: Account, role: RoleChange) {
  return authorized(async csrf => unwrap(await client.PATCH('/api/v1/admin/users/{user_id}/role', {
    params: { path: { user_id: account.id } },
    headers: { 'X-CSRF-Token': csrf },
    body: { role, expected_version: account.version },
  })), 'admin');
}

export function changeAccountStatus(account: Account, disabled: boolean) {
  return authorized(async csrf => unwrap(await client.PATCH('/api/v1/admin/users/{user_id}/status', {
    params: { path: { user_id: account.id } },
    headers: { 'X-CSRF-Token': csrf },
    body: { disabled, expected_version: account.version },
  })), 'admin');
}
