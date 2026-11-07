import { cache } from 'react';
import createClient from 'openapi-fetch';
import type { paths, components } from './api/catalog-schema';
import type { Product, Reference } from './content';

export type CatalogProduct = components['schemas']['Product'];
export type CatalogVariant = components['schemas']['Variant'];
export type PublicImage = components['schemas']['PublicImage'];
const client = createClient<paths>({ baseUrl: process.env.CATALOG_URL || 'http://127.0.0.1:8000' });
export class CatalogUnavailable extends Error {}

export function productView(item: CatalogProduct): Product {
  const offers: Product['offers'] = {};
  for (const variant of item.variants) for (const offer of variant.offers ?? []) {
    const reference: Reference = { amountMinor: offer.amount_minor, currency: offer.currency,
      source: offer.source.url, seller: offer.seller, packaging: variant.packaging,
      checkedOn: offer.source.checked_on };
    if (!offers[offer.market]) offers[offer.market] = reference;
  }
  return { slug: item.slug, name: item.name, category: item.category, brand: item.brand,
    image: item.image, imageKind: item.image_kind, description: item.description, highlights: item.highlights ?? [], offers };
}

export type CatalogQuery = NonNullable<paths['/api/v1/catalog/products']['get']['parameters']['query']>;
export async function listCatalog(query: CatalogQuery = {}) {
  try {
    const { data, error } = await client.GET('/api/v1/catalog/products', {
      params: { query }, cache: 'no-store', signal: AbortSignal.timeout(6000),
    });
    if (error || !data) throw new CatalogUnavailable();
    return data;
  } catch { throw new CatalogUnavailable(); }
}
export const getCatalogProduct = cache(async (slug: string) => {
  try {
    const { data, response } = await client.GET('/api/v1/catalog/products/{slug}', {
      params: { path: { slug } }, cache: 'no-store', signal: AbortSignal.timeout(6000),
    });
    if (response.status === 404) return null;
    if (!response.ok || !data) throw new CatalogUnavailable();
    return data;
  } catch { throw new CatalogUnavailable(); }
});
export const listCategories = cache(async () => {
  try {
    const { data, error } = await client.GET('/api/v1/catalog/categories', { cache: 'no-store', signal: AbortSignal.timeout(6000) });
    if (error || !data) throw new CatalogUnavailable();
    return data.map(c => ({ id: c.slug, ...c.name, image: c.image }));
  } catch { throw new CatalogUnavailable(); }
});

export async function getProductGallery(id: string): Promise<PublicImage[]> {
  const { data, response } = await client.GET('/api/v1/catalog/products/{product_id}/images', {
    params: { path: { product_id: id } }, cache: 'no-store', signal: AbortSignal.timeout(6000),
  });
  if (!response.ok || !data) throw new CatalogUnavailable();
  return data;
}
