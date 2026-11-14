'use client';

import createClient from 'openapi-fetch';
import { IdentityError, readSession } from './identity-client';
import type { components, paths } from './api/cart-schema';
import { text, type Locale, type Market } from './content';

export type Cart = components['schemas']['CartView'];
export type CartLine = components['schemas']['LineView'];
export class CartError extends Error {
  constructor(public code: string, public status = 0) { super(code); }
}

export function cartErrorCopy(error: Error, locale: Locale) {
  const code = error instanceof CartError ? error.code : '';
  if (code === 'guest.expired') return text(locale, 'نشست مهمان منقضی شده است. می‌توانی سبد تازه‌ای شروع کنی.', 'Your guest session expired. You can start a new cart.');
  if (code === 'cart.limit') return text(locale, 'تعداد اقلام با سقف سبد سازگار نیست.', 'This would exceed the cart limits.');
  if (code === 'cart.insufficient_stock') return text(locale, 'موجودی برای این تعداد کافی نیست.', 'There is not enough stock for this quantity.');
  if (error instanceof CartError && error.status === 409) return text(locale, 'سبد تغییر کرده است. نسخهٔ تازه را بررسی کن.', 'Your cart changed. Review the latest version.');
  return text(locale, 'دریافت یا تغییر سبد ممکن نشد. دوباره تلاش کن.', 'We couldn’t load or update your cart. Try again.');
}

const client = createClient<paths>({ credentials: 'same-origin', cache: 'no-store',
  fetch: async request => {
    try { return await fetch(request, { signal: AbortSignal.any([request.signal, AbortSignal.timeout(12000)]) }); }
    catch (error) { if (request.signal.aborted) throw error; throw new CartError('cart.unavailable'); }
  },
});

function unwrap<T>({ data, error, response }: { data?: T; error?: unknown; response: Response }): T {
  if (!response.ok) {
    const envelope = error as components['schemas']['ErrorEnvelope'] | undefined;
    throw new CartError(envelope?.error?.code || 'cart.unavailable', response.status);
  }
  return data as T;
}

async function customerSession() {
  try { return await readSession(); }
  catch (error) {
    if (error instanceof IdentityError && error.status === 401) return null;
    throw error;
  }
}

const empty = (market: Market): Cart => ({
  id: '', version: 1, owner_scope: 'guest', market, currency: market === 'ir' ? 'IRR' : 'USD',
  groups: [], lines: [], estimated_total_minor: '0', catalog_status: 'ready', known_subtotal_minor: '0', reserves_stock: false,
});

export async function readCart(market: Market, signal?: AbortSignal) {
  // The access cookie may have expired while the customer refresh cookie
  // remains valid on the identity path. Resolve it before showing guest data.
  const session = await customerSession();
  if (signal?.aborted) throw signal.reason;
  const result = await client.GET('/api/v1/cart', { params: { query: { market } }, signal });
  const error = result.error as components['schemas']['ErrorEnvelope'] | undefined;
  if (!session && result.response.status === 401 && error?.error.code === 'guest.required') return empty(market);
  const cart = unwrap(result);
  if (session && cart.owner_scope !== 'customer') throw new CartError('auth.required', 401);
  return cart;
}

export async function startGuest(recover = false) {
  return unwrap(await client.POST('/api/v1/cart/session', {
    params: { query: { recover_expired: recover } }, headers: { 'X-CSRF-Request': '1' },
  }));
}

export async function cartCsrf(scope: Cart['owner_scope']) {
  const session = await customerSession();
  if (scope === 'customer' && session) return session.csrf_token;
  if (scope === 'guest' && !session) return unwrap(await client.GET('/api/v1/cart/session', {
    headers: { 'X-CSRF-Request': '1' },
  })).csrf_token;
  throw new CartError('cart.session_changed', 409);
}

export async function changeCartLine(cart: Cart, line: CartLine, quantity: number | null) {
  const csrf = await cartCsrf(cart.owner_scope);
  const group = cart.groups.find(group => group.id === line.group_id);
  const versions = { market: cart.market, expected_version: cart.version, expected_group_version: group?.version };
  const headers = { 'X-CSRF-Token': csrf };
  const path = { line_id: line.id };
  return quantity === null
    ? unwrap(await client.DELETE('/api/v1/cart/items/{line_id}', { params: { path, query: versions }, headers }))
    : unwrap(await client.PATCH('/api/v1/cart/items/{line_id}', { params: { path }, body: { ...versions, quantity }, headers }));
}

export async function deleteCartGroup(cart: Cart, group: Cart['groups'][number]) {
  const csrf = await cartCsrf(cart.owner_scope);
  return unwrap(await client.DELETE('/api/v1/cart/groups/{group_id}', {
    params: { path: { group_id: group.id }, query: { market: cart.market, expected_version: cart.version, expected_group_version: group.version } },
    headers: { 'X-CSRF-Token': csrf },
  }));
}

export async function addCartItem(variantId: string, market: Market) {
  let cart = await readCart(market);
  if (!cart.id) {
    const open = async () => {
      const current = await readCart(market);
      if (current.id) return current;
      await startGuest();
      return readCart(market);
    };
    cart = navigator.locks ? await navigator.locks.request('nivaro-guest-cart', open) : await open();
  }
  const csrf = await cartCsrf(cart.owner_scope);
  return unwrap(await client.POST('/api/v1/cart/items', {
    body: { market, expected_version: cart.version, variant_id: variantId, quantity: 1 },
    headers: { 'X-CSRF-Token': csrf },
  }));
}

export async function readMergeSource(market: Market, signal?: AbortSignal) {
  const result = await client.GET('/api/v1/cart/merge', { params: { query: { market } }, signal });
  const error = result.error as components['schemas']['ErrorEnvelope'] | undefined;
  if (result.response.status === 401 && ['guest.expired', 'guest.required'].includes(error?.error.code ?? '')) return null;
  return unwrap(result);
}

export async function mergeGuestCart(cart: Cart, source: components['schemas']['MergeSource'], key: string) {
  return unwrap(await client.POST('/api/v1/cart/merge', {
    params: { header: { 'Idempotency-Key': key } },
    body: { market: cart.market, guest_cart_id: source.cart_id, expected_guest_version: source.version, expected_version: cart.version },
    headers: { 'X-CSRF-Token': await cartCsrf('customer') },
  }));
}
