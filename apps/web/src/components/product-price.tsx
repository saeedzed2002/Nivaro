'use client';
import { usePreferences } from './preferences';
import { formatMoney, text, type Locale, type Product } from '@/lib/content';

export function ProductPrice({ product, locale, detailed = false }: { product: Product; locale: Locale; detailed?: boolean }) {
  const { market } = usePreferences();
  const reference = product.offers[market];
  return <div className={`price-block ${detailed ? 'detailed' : ''}`}>
    <span className="price-label">{text(locale, 'قیمت مرجع بازار', 'RETAIL REFERENCE')}</span>
    <strong className="price">{reference ? <bdi>{formatMoney(reference, locale)}</bdi> : text(locale, 'قیمت تأیید نشده', 'Price not verified')}</strong>
    {detailed ? <>
      <p>{reference?.packaging[locale] || text(locale, 'برای این بازار، قیمت مستند نداریم.', 'No documented price for this market.')}</p>
      {reference ? <p className="source-line"><a href={reference.source} target="_blank" rel="noopener noreferrer">{text(locale, 'منبع', 'Source')}: <bdi>{reference.seller}</bdi> ↗</a><span><bdi>{reference.checkedOn}</bdi></span></p> : null}
      <p className="reference-note">{text(locale, 'این مبلغ پیشنهاد فروش نیوارو نیست. قیمت، موجودی و هزینهٔ ارسال برای خرید تأیید نشده‌اند.', 'This is not a Nivaro sales offer. Purchase price, stock and delivery charges are not confirmed.')}</p>
    </> : null}
  </div>;
}
