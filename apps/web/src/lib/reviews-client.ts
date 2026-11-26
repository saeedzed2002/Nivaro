'use client';

import createClient from 'openapi-fetch';
import type { components, paths } from './api/catalog-schema';
import { authorized, IdentityError } from './identity-client';

export type SavedReview = components['schemas']['SavedReview'];
export type ReviewInput = components['schemas']['ReviewInput'];
export type ReviewDecision = components['schemas']['ReviewDecision'];

const client = createClient<paths>({ credentials: 'same-origin', cache: 'no-store',
  fetch: async request => {
    try { return await fetch(request, { signal: AbortSignal.any([request.signal, AbortSignal.timeout(10_000)]) }); }
    catch (error) { if (request.signal.aborted) throw error; throw new IdentityError('catalog.unavailable'); }
  },
});

function unwrap<T>({ data, response, error }: { data?: T; response: Response; error?: unknown }) {
  if (!response.ok || !data) throw new IdentityError(
    (error as components['schemas']['ErrorEnvelope'] | undefined)?.error?.code ?? 'catalog.unavailable', response.status,
  );
  return data;
}

export const listProductReviews = async (productId: string, before?: string, signal?: AbortSignal) =>
  unwrap(await client.GET('/api/v1/catalog/products/{product_id}/reviews', { params: { path: { product_id: productId }, query: { before } }, signal }));

export const readOwnReview = (productId: string, signal?: AbortSignal) => authorized(async () =>
  unwrap(await client.GET('/api/v1/catalog/products/{product_id}/reviews/mine', { params: { path: { product_id: productId } }, signal })));

export const saveOwnReview = (productId: string, body: ReviewInput) => authorized(async csrf =>
  unwrap(await client.PUT('/api/v1/catalog/products/{product_id}/reviews/mine', {
    params: { path: { product_id: productId } }, headers: { 'X-CSRF-Token': csrf }, body,
  })));

export const listModerationQueue = (status: SavedReview['status'], before?: string, signal?: AbortSignal) => authorized(async () =>
  unwrap(await client.GET('/api/v1/admin/catalog/reviews', { params: { query: { status, before } }, signal })), 'admin');

export const readReviewOverview = (signal?: AbortSignal) => authorized(async () =>
  unwrap(await client.GET('/api/v1/admin/catalog/reviews/overview', { signal })), 'admin');

export const listCatalogMediaQueue = (before?: string, signal?: AbortSignal) => authorized(async () =>
  unwrap(await client.GET('/api/v1/admin/catalog/media/queue', { params: { query: { before } }, signal })), 'admin');

export const decideReview = (reviewId: string, body: ReviewDecision) => authorized(async csrf =>
  unwrap(await client.POST('/api/v1/admin/catalog/reviews/{review_id}/decision', {
    params: { path: { review_id: reviewId } }, headers: { 'X-CSRF-Token': csrf }, body,
  })), 'admin');
