import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import { text, type Locale } from '@/lib/content';

export function Footer({ locale }: { locale: Locale }) {
  return <footer className="site-footer"><div className="container footer-top">
    <div><div className="footer-brand" dir="ltr">NIVARO<span> GAMING</span></div><p>{text(locale, 'سیستم تو، با انتخاب تو.', 'Your setup. Your rules.')}</p></div>
    <div><h3>{text(locale, 'کشف کن', 'Explore')}</h3><Link href={`/${locale}/products`}>{text(locale, 'همهٔ محصولات', 'All products')}</Link><Link href={`/${locale}/products?category=pc`}>{text(locale, 'سیستم‌های آماده', 'Gaming PCs')}</Link><Link href={`/${locale}/products?category=keyboard`}>{text(locale, 'تجهیزات گیمینگ', 'Gaming gear')}</Link></div>
    <div className="footer-note"><h3>{text(locale, 'دربارهٔ این نسخه', 'About this preview')}</h3><p>{text(locale, 'محصولات و قیمت‌های مرجع برای بررسی طراحی‌اند. تصاویر مفهومی هستند و خرید هنوز فعال نیست.', 'Products and retail references demonstrate the design. Images are conceptual; purchasing is not active yet.')}</p><Link href={`/${locale}/products`}>{text(locale, 'بررسی محصولات مرجع', 'Explore the reference collection')}<ArrowUpRight size={16}/></Link></div>
  </div><div className="container footer-bottom"><span dir="ltr">© 2026 NIVARO GAMING</span><span>{text(locale, 'طراحی برای انتخاب دقیق‌تر', 'Made for a more considered build')}</span></div></footer>;
}
