import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ShoppingBag } from 'lucide-react';
import { CheckoutWorkspace } from '@/components/checkout-workspace';
import { isLocale, text } from '@/lib/content';

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  return { title: locale === 'fa' ? 'تسویه سفارش' : 'Checkout', robots: { index: false, follow: false } };
}

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return <main id="main-content" className="container checkout-page">
    <Link className="text-link checkout-back" href={`/${locale}/cart`}><ShoppingBag size={18} aria-hidden="true" />{text(locale, 'بازگشت به سبد خرید', 'Back to cart')}</Link>
    <h1>{text(locale, 'تسویه سفارش', 'Checkout')}</h1>
    <CheckoutWorkspace locale={locale} />
  </main>;
}
