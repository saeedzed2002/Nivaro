import { notFound } from 'next/navigation';
import { isLocale } from '@/lib/content';
import { serverIdentity } from '@/lib/identity-server';
import { IdentityAccount } from '@/components/identity-account';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Account details | Nivaro Gaming', robots: { index: false, follow: false } };
export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return <IdentityAccount locale={locale} view="profile" initial={await serverIdentity()}/>;
}
