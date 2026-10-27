import Link from 'next/link';
import { CloudOff } from 'lucide-react';
import { text, type Locale } from '@/lib/content';

export function CatalogUnavailableState({ locale }: { locale: Locale }) {
  return <section className="empty-state" role="status"><CloudOff size={38}/>
    <h2>{text(locale, 'کاتالوگ موقتاً در دسترس نیست', 'Catalog temporarily unavailable')}</h2>
    <p>{text(locale, 'دریافت محصولات انجام نشد. کمی بعد دوباره تلاش کن.', 'Products could not be loaded. Please try again shortly.')}</p>
    <a className="button primary" href="">{text(locale, 'تلاش دوباره', 'Try again')}</a>
    <Link className="text-link" href={`/${locale}`}>{text(locale, 'خانه', 'Home')}</Link>
  </section>;
}
