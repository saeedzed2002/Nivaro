import { notFound } from 'next/navigation';
import { CartWorkspace } from '@/components/cart-workspace';
import { isLocale, text } from '@/lib/content';

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  return { title: locale === 'fa' ? 'سبد خرید' : 'Shopping cart' };
}

export default async function CartPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return <main id="main-content" className="container cart-page">
    <h1>{text(locale, 'سبد خرید', 'Shopping cart')}</h1>
    <CartWorkspace locale={locale} />
  </main>;
}
