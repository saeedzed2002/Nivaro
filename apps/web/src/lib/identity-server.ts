import { cookies } from 'next/headers';
import createClient from 'openapi-fetch';
import type { paths, components } from './api/identity-schema';

export type InitialIdentity = { session: components['schemas']['SessionResponse'] | null; unavailable: boolean };
export async function serverIdentity(scope: 'customer' | 'admin' = 'customer'): Promise<InitialIdentity> {
  const cookie = (await cookies()).get(`nivaro_${scope}_access`);
  if (!cookie) return { session: null, unavailable: false };
  const client = createClient<paths>({ baseUrl: process.env.IDENTITY_URL || 'http://127.0.0.1:8001' });
  try {
    const result = await client.GET(scope === 'admin' ? '/api/v1/admin/auth/session' : '/api/v1/auth/session', {
      headers: { Cookie: `${cookie.name}=${cookie.value}` }, cache: 'no-store', signal: AbortSignal.timeout(5000),
    });
    return { session: result.data || null, unavailable: !result.response.ok && result.response.status !== 401 };
  } catch { return { session: null, unavailable: true }; }
}
