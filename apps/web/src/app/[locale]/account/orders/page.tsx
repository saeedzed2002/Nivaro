import { notFound } from 'next/navigation';
import { IdentityAccount } from '@/components/identity-account';
import { isLocale } from '@/lib/content';
import { serverIdentity } from '@/lib/identity-server';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Order history | Nivaro Gaming', robots: { index: false, follow: false } };

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return <IdentityAccount locale={locale} view="orders" initial={await serverIdentity()}/>;
}
