'use client';

import createClient from 'openapi-fetch';
import type { components, paths } from './api/orders-schema';
import { authorized, IdentityError } from './identity-client';

export type CheckoutIntent = components['schemas']['CheckoutIntent'];
export type CheckoutPreview = components['schemas']['PreviewResponse'];
export type OrderStatus = components['schemas']['OrderStatus'];
export type OrderHistory = components['schemas']['OrderHistory'];
export type OrderDetails = components['schemas']['OrderDetails'];

const client = createClient<paths>({ credentials: 'same-origin', cache: 'no-store',
  fetch: async request => {
    try { return await fetch(request, { signal: AbortSignal.any([request.signal, AbortSignal.timeout(25_000)]) }); }
    catch (error) { if (request.signal.aborted) throw error; throw new IdentityError('checkout.unavailable'); }
  },
});

function unwrap<T>({ data, error, response }: { data?: T; error?: unknown; response: Response }): T {
  if (!response.ok || !data) {
    const envelope = error as components['schemas']['ErrorResponse'] | undefined;
    throw new IdentityError(envelope?.error?.code || 'checkout.unavailable', response.status);
  }
  return data;
}

export const previewCheckout = (intent: CheckoutIntent, key: string) => authorized(async csrf =>
  unwrap(await client.POST('/api/v1/orders/checkout/preview', {
    params: { header: { 'Idempotency-Key': key } }, body: intent, headers: { 'X-CSRF-Token': csrf },
  })));

export const confirmCheckout = (operationId: string, confirmation: string) => authorized(async csrf =>
  unwrap(await client.POST('/api/v1/orders/checkout/{operation_id}/confirm', {
    params: { path: { operation_id: operationId } }, body: { confirmation }, headers: { 'X-CSRF-Token': csrf },
  })));

export const orderStatus = (id: string, signal?: AbortSignal) => authorized(async () =>
  unwrap(await client.GET('/api/v1/orders/{order_id}', { params: { path: { order_id: id } }, signal })));

export const startSimulatedPayment = (id: string, version: number) => authorized(async csrf =>
  unwrap(await client.POST('/api/v1/orders/{order_id}/payment', {
    params: { path: { order_id: id }, header: { 'Idempotency-Key': id } },
    body: { order_version: version }, headers: { 'X-CSRF-Token': csrf },
  })));

export const listCustomerOrders = (before: string | undefined, signal?: AbortSignal) => authorized(async () =>
  unwrap(await client.GET('/api/v1/orders/history', { params: { query: { before } }, signal })));

export const readCustomerOrderDetails = (id: string, signal?: AbortSignal) => authorized(async () =>
  unwrap(await client.GET('/api/v1/orders/{order_id}/details', { params: { path: { order_id: id } }, signal })));
