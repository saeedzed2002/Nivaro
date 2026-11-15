import { notFound } from 'next/navigation';
import { isLocale, isUuid } from '@/lib/content';
import { serverIdentity } from '@/lib/identity-server';
import { IdentityLogin } from '@/components/identity-login';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Sign in | Nivaro Gaming', robots: { index: false, follow: false } };
export default async function Page({ params, searchParams }: { params: Promise<{ locale: string }>; searchParams: Promise<{ next?: string | string[]; order?: string | string[] }> }) {
  const [{ locale }, { next, order }] = await Promise.all([params, searchParams]);
  if (!isLocale(locale)) notFound();
  const destination = next === 'checkout' ? `/${locale}/checkout`
    : next === 'orders' ? `/${locale}/account/orders`
    : next === 'order' && typeof order === 'string' && isUuid(order) ? `/${locale}/account/orders/${order}`
    : next === 'result' && typeof order === 'string' && isUuid(order) ? `/${locale}/checkout/result?order=${order}` : undefined;
  return <IdentityLogin locale={locale} initial={await serverIdentity()} mock={process.env.IDENTITY_LOCAL_MOCK === 'true'} destination={destination} />;
}
