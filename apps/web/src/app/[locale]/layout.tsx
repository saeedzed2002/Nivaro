import { notFound } from 'next/navigation';
import { Header } from '@/components/header';
import { Footer } from '@/components/footer';
import { isLocale, text } from '@/lib/content';

export default async function LocaleLayout({ children, params }: { children: React.ReactNode; params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return <><a className="skip-link" href="#main-content">{text(locale, 'رفتن به محتوای اصلی', 'Skip to content')}</a><Header locale={locale}/>{children}<Footer locale={locale}/></>;
}
