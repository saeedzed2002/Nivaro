import { notFound } from 'next/navigation';
import { CheckoutResult } from '@/components/checkout-result';
import { isLocale, isUuid } from '@/lib/content';

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  return { title: locale === 'fa' ? 'وضعیت سفارش' : 'Order status', robots: { index: false, follow: false } };
}

export default async function Page({ params, searchParams }: { params: Promise<{ locale: string }>; searchParams: Promise<{ order?: string | string[] }> }) {
  const [{ locale }, { order }] = await Promise.all([params, searchParams]);
  if (!isLocale(locale)) notFound();
  return <CheckoutResult locale={locale} id={typeof order === 'string' && isUuid(order) ? order.toLowerCase() : null} />;
}
