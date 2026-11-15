import { notFound } from 'next/navigation';
import { IdentityAccount } from '@/components/identity-account';
import { isLocale, isUuid } from '@/lib/content';
import { serverIdentity } from '@/lib/identity-server';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Order details | Nivaro Gaming', robots: { index: false, follow: false } };

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  const { locale, id } = await params;
  if (!isLocale(locale) || !isUuid(id)) notFound();
  return <IdentityAccount locale={locale} view="orders" orderId={id} initial={await serverIdentity()}/>;
}
