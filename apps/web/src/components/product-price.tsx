'use client';
import { usePreferences } from './preferences';
import { formatMoney, text, type Locale, type Product } from '@/lib/content';

export function ProductPrice({ product, locale, detailed = false }: { product: Product; locale: Locale; detailed?: boolean }) {
  const { market } = usePreferences();
  const otherMarket = market === 'ir' ? 'international' : 'ir';
  const reference = product.offers[market] ?? product.offers[otherMarket];
  const marketLabel = product.offers[market] ? null : otherMarket === 'ir' ? text(locale, 'ایران', 'Iran') : text(locale, 'بین‌المللی', 'International');
  return <div className={`price-block ${detailed ? 'detailed' : ''}`}>
    <span className="price-label">{text(locale, 'قیمت مرجع بازار', 'RETAIL REFERENCE')}{reference && marketLabel ? ` · ${marketLabel}` : null}</span>
    <strong className="price">{reference ? <bdi>{formatMoney(reference, locale)}</bdi> : text(locale, 'قیمت تأیید نشده', 'Price not verified')}</strong>
    {detailed ? <>
      <p>{reference?.packaging[locale] || text(locale, 'برای این بازار، قیمت مستند نداریم.', 'No documented price for this market.')}</p>
      {reference ? <p className="source-line"><a href={reference.source} target="_blank" rel="noopener noreferrer">{text(locale, 'منبع', 'Source')}: <bdi>{reference.seller}</bdi> ↗</a><span><bdi>{reference.checkedOn}</bdi></span></p> : null}
      <p className="reference-note">{marketLabel && reference ? text(locale, 'برای دیدن امکان افزودن این محصول، بازار را عوض کن.', 'Switch to this market to check whether you can add this product.') : text(locale, 'قیمت از مرجع خرده‌فروشی ثبت شده است. جمع سفارش، ارسال و مالیات در مرحلهٔ تسویه محاسبه می‌شوند.', 'The price is based on the cited retailer. The order total, shipping and taxes are calculated at checkout.')}</p>
    </> : null}
  </div>;
}
