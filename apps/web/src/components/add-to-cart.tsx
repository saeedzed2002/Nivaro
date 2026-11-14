'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ShoppingBag } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import { addCartItem, cartErrorCopy } from '@/lib/cart-client';
import type { components } from '@/lib/api/catalog-schema';
import { text, type Locale } from '@/lib/content';
import { cartKey } from './cart-query';
import { usePreferences } from './preferences';

type Variant = components['schemas']['Variant'];

export function AddToCart({ variants, locale }: { variants: Variant[]; locale: Locale }) {
  const { market } = usePreferences();
  const cache = useQueryClient();
  const [variantId, setVariant] = useState(variants[0]?.id ?? '');
  const variant = variants.find(item => item.id === variantId);
  const offer = variant?.offers?.find(item => item.market === market);
  const available = Boolean(offer?.available_for_sale && !offer.reference_only && variant?.stock_verified && (variant.on_hand ?? 0) > (variant.reserved ?? 0));
  const add = useMutation({ mutationFn: () => addCartItem(variantId, market),
    onSettled: () => cache.invalidateQueries({ queryKey: cartKey(market) }) });
  return <div className="cart-product-action">
    {variants.length > 1 && <label className="field"><span>{text(locale, 'گونهٔ محصول', 'Variant')}</span>
      <select value={variantId} onChange={event => { setVariant(event.target.value); add.reset(); }} disabled={add.isPending}>
        {variants.map(item => <option key={item.id} value={item.id}>{item.packaging[locale]} · {item.sku}</option>)}
      </select>
    </label>}
    <button type="button" className="button primary" disabled={!available || add.isPending} onClick={() => add.mutate()}>
      <ShoppingBag size={18} />{add.isPending ? text(locale, 'در حال افزودن…', 'Adding…') : text(locale, 'افزودن به سبد', 'Add to cart')}
    </button>
    {!available && <p className="muted">{text(locale, 'این گونه در بازار انتخاب‌شده قابل سفارش نیست.', 'This variant is unavailable to order in the selected market.')}</p>}
    {add.error && <p role="alert">{cartErrorCopy(add.error, locale)}</p>}
    {add.isSuccess && <p role="status">{text(locale, 'به سبد اضافه شد.', 'Added to your cart.')} <Link className="text-link" href={`/${locale}/cart`}>{text(locale, 'دیدن سبد', 'View cart')}</Link></p>}
  </div>;
}
