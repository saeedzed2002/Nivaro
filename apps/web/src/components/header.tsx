'use client';

import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { Search, Sun, Moon, Monitor, ShoppingBag, UserRound, ArrowUpRight, Cpu, SlidersHorizontal } from 'lucide-react';
import { usePreferences } from './preferences';
import { AvailabilityDialog } from './availability-dialog';
import { text, type Locale, type Market, type Theme } from '@/lib/content';

export function Header({ locale }: { locale: Locale }) {
  const { market, theme, setMarket, setTheme } = usePreferences();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const nextLocale = locale === 'fa' ? 'en' : 'fa';
  const languagePath = pathname.replace(/^\/(fa|en)(?=\/|$)/, `/${nextLocale}`);
  const query = searchParams.toString();
  const themeIcon = theme === 'light' ? <Sun size={18} /> : theme === 'dark' ? <Moon size={18} /> : <Monitor size={18} />;
  return <header className="site-header">
    <div className="utility-bar"><div className="container utility-inner"><span>{text(locale, 'نیوارو؛ از اولین قطعه تا ستاپ کامل', 'NIVARO — FROM YOUR FIRST COMPONENT TO YOUR COMPLETE SETUP')}</span><span className="preview-indicator"><span />{text(locale, 'پیش‌نمایش فروشگاه', 'STOREFRONT PREVIEW')}</span></div></div>
    <div className="container header-main">
      <Link href={`/${locale}`} className="brand" aria-label={text(locale, 'نیوارو گیمینگ؛ صفحهٔ اصلی', 'Nivaro Gaming home')}>
        <svg viewBox="0 0 40 44" width="37" height="42" aria-hidden="true"><path d="M3 38V5l11 8v25z" fill="#2671ff"/><path d="M8 4l29 25v12L8 17z" fill="#36c3ed"/><path d="M26 3l11 8v13l-11-9z" fill="#5871ff"/><path d="M3 38l11-10v10L3 44z" fill="#8b5cf6"/></svg>
        <span dir="ltr"><strong>NIVARO</strong><small>G A M I N G</small></span>
      </Link>
      <form className="search-box" action={`/${locale}/products`} role="search">
        <Search size={21} aria-hidden="true" />
        <input name="q" aria-label={text(locale, 'جست‌وجوی محصولات', 'Search products')} placeholder={text(locale, 'جست‌وجوی قطعه، مدل یا برند…', 'Search components, models or brands…')} defaultValue={searchParams.get('q') || ''} key={searchParams.get('q') || ''} maxLength={100}/>
        <button type="submit" aria-label={text(locale, 'جست‌وجو', 'Search')}><ArrowUpRight size={18} /></button>
      </form>
      <div className="header-actions">
        <a href={`${languagePath}${query ? `?${query}` : ''}`} hrefLang={nextLocale} className="language-control" onClick={() => setMarket(market)} aria-label={text(locale, 'تغییر زبان به انگلیسی', 'Switch language to Persian')}>{locale === 'fa' ? 'EN' : 'فارسی'}</a>
        <label className="select-control"><span className="sr-only">{text(locale, 'بازار فروش', 'Sales market')}</span><select value={market} onChange={e => setMarket(e.target.value as Market)} aria-label={text(locale, 'بازار فروش', 'Sales market')}><option value="ir">{text(locale, 'ایران · تومان', 'Iran · toman')}</option><option value="international">{text(locale, 'بین‌المللی · دلار', 'International · USD')}</option></select></label>
        <label className="theme-control" title={text(locale, 'حالت نمایش', 'Appearance')}>{themeIcon}<span className="sr-only">{text(locale, 'حالت نمایش', 'Appearance')}</span><select value={theme} onChange={e => setTheme(e.target.value as Theme)} aria-label={text(locale, 'حالت نمایش', 'Appearance')}><option value="system">{text(locale, 'سیستم', 'System')}</option><option value="dark">{text(locale, 'تاریک', 'Dark')}</option><option value="light">{text(locale, 'روشن', 'Light')}</option></select></label>
        <AvailabilityDialog locale={locale} title={text(locale, 'حساب کاربری', 'Your account')} className="icon-button account-action" label={text(locale, 'حساب کاربری', 'Your account')}><UserRound size={22} /></AvailabilityDialog>
        <AvailabilityDialog locale={locale} title={text(locale, 'سبد خرید', 'Shopping bag')} className="icon-button" label={text(locale, 'سبد خرید؛ هنوز فعال نیست', 'Shopping bag; not active yet')}><ShoppingBag size={22} /></AvailabilityDialog>
      </div>
    </div>
    <nav className="container main-nav" aria-label={text(locale, 'ناوبری اصلی', 'Main navigation')}>
      <Link className={pathname.includes('/products') ? 'active' : ''} href={`/${locale}/products`}><Cpu size={17}/>{text(locale, 'قطعات کامپیوتر', 'Components')}</Link>
      <Link href={`/${locale}/build`} className={pathname.includes("/build") ? "active" : ""}>{text(locale, "اسمبل سیستم", "Build your PC")}</Link>
      <Link href={`/${locale}/products?category=pc`}>{text(locale, 'سیستم‌های آماده', 'Gaming PCs')}</Link>
      <Link href={`/${locale}/products?category=keyboard`}>{text(locale, 'تجهیزات گیمینگ', 'Peripherals')}</Link>
      <Link href={`/${locale}/compare`} className={pathname.includes("/compare") ? "active" : ""}><SlidersHorizontal size={16}/>{text(locale, "مقایسه", "Compare")}</Link>
    </nav>
  </header>;
}
