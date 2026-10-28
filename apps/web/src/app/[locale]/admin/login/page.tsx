import { notFound } from 'next/navigation';
import { isLocale } from '@/lib/content';
import { serverIdentity } from '@/lib/identity-server';
import { IdentityLogin } from '@/components/identity-login';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Staff sign in | Nivaro Gaming', robots: { index: false, follow: false } };
export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return <IdentityLogin locale={locale} admin initial={await serverIdentity('admin')}/>;
}
