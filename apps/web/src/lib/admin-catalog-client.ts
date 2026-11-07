'use client';

import createClient from 'openapi-fetch';
import type { paths, components, operations } from './api/catalog-schema';
import { authorized, IdentityError } from './identity-client';

export type AdminProduct = components['schemas']['AdminProduct'];
export type AdminDetail = components['schemas']['AdminProductDetail'];
export type AdminPage = components['schemas']['AdminProductPage'];
export type AdminCategory = components['schemas']['Category'];
export type ProductContent = components['schemas']['ProductContent'];
export type StockChange = components['schemas']['StockChange'];
export type AuditPage = components['schemas']['AuditPage'];
export type VariantContent = components['schemas']['VariantContent'];
export type OfferChange = components['schemas']['OfferChange'];
export type AdminVariant = AdminDetail['variants'][number];
export type Evidence = components['schemas']['Evidence'];
export type ManagedCategory = components['schemas']['AdminCategory'];
export type CategoryContent = components['schemas']['CategoryContent'];
export type Filters = NonNullable<operations['listAdminProducts']['parameters']['query']>;
const client = createClient<paths>({ baseUrl: '', credentials: 'same-origin', cache: 'no-store',
  fetch: async request => {
    try { return await fetch(request, { signal: AbortSignal.timeout(10000) }); }
    catch { throw new IdentityError('catalog.unavailable'); }
  },
});
function unwrap<T>({ data, response, error }: { data?: T; response: Response; error?: unknown }): T {
  if (!response.ok) throw new IdentityError(
    (error as components['schemas']['ErrorEnvelope'] | undefined)?.error?.code || 'catalog.unavailable', response.status,
  );
  return data as T;
}
export const listAdminProducts = (query: Filters) => authorized(async () => unwrap(await client.GET('/api/v1/admin/catalog/products', { params: { query } })), 'admin');
export const adminCategories = async () => unwrap(await client.GET('/api/v1/catalog/categories'));
export const getAdminProduct = (id: string) => authorized(async () => unwrap(await client.GET('/api/v1/admin/catalog/products/{product_id}', { params: { path: { product_id: id } } })), 'admin');
export const createAdminProduct = (body: ProductContent) => authorized(async csrf => unwrap(await client.POST('/api/v1/admin/catalog/products', { body, headers: { 'X-CSRF-Token': csrf } })), 'admin');
export const saveAdminProduct = (id: string, body: ProductContent & { expected_version: number }) => authorized(async csrf => unwrap(await client.PUT('/api/v1/admin/catalog/products/{product_id}', { params: { path: { product_id: id } }, body, headers: { 'X-CSRF-Token': csrf } })), 'admin');
export const setProductStatus = (product: AdminDetail, status: AdminProduct['status']) => authorized(async csrf => unwrap(await client.PUT('/api/v1/admin/catalog/products/{product_id}/status', { params: { path: { product_id: product.id } }, body: { expected_version: product.version, status }, headers: { 'X-CSRF-Token': csrf } })), 'admin');
export const saveAdminStock = (productId: string, variantId: string, body: StockChange) => authorized(async csrf => unwrap(await client.PUT('/api/v1/admin/catalog/products/{product_id}/variants/{variant_id}/stock', { params: { path: { product_id: productId, variant_id: variantId } }, body, headers: { 'X-CSRF-Token': csrf } })), 'admin');
export const productAudit = (id: string, page = 1) => authorized(async () => unwrap(await client.GET('/api/v1/admin/catalog/products/{product_id}/audit', { params: { path: { product_id: id }, query: { page, page_size: 10 } } })), 'admin');
export const saveAdminVariant = (productId: string, variantId: string | undefined, body: VariantContent) => authorized(async csrf => unwrap(variantId
  ? await client.PUT('/api/v1/admin/catalog/products/{product_id}/variants/{variant_id}', { params: { path: { product_id: productId, variant_id: variantId } }, body, headers: { 'X-CSRF-Token': csrf } })
  : await client.POST('/api/v1/admin/catalog/products/{product_id}/variants', { params: { path: { product_id: productId } }, body, headers: { 'X-CSRF-Token': csrf } })), 'admin');
export const saveAdminOffer = (productId: string, variantId: string, body: OfferChange) => authorized(async csrf => unwrap(await client.PUT('/api/v1/admin/catalog/products/{product_id}/variants/{variant_id}/offers', { params: { path: { product_id: productId, variant_id: variantId } }, body, headers: { 'X-CSRF-Token': csrf } })), 'admin');
export const listManagedCategories = () => authorized(async () => unwrap(await client.GET('/api/v1/admin/catalog/categories')), 'admin');
export const saveManagedCategory = (body: CategoryContent, category?: ManagedCategory) => authorized(async csrf => unwrap(category
  ? await client.PUT('/api/v1/admin/catalog/categories/{category_id}', { params: { path: { category_id: category.id } }, body: { ...body, expected_version: category.version }, headers: { 'X-CSRF-Token': csrf } })
  : await client.POST('/api/v1/admin/catalog/categories', { body, headers: { 'X-CSRF-Token': csrf } })), 'admin');
