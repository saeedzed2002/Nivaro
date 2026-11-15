import { notFound } from 'next/navigation';
import { AdminShell } from '@/components/admin-shared';
import { SupportInbox } from '@/components/support-workspace';
import { isLocale, text } from '@/lib/content';
import { serverIdentity } from '@/lib/identity-server';

type Props = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: Props) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return { title: text(locale, 'صندوق پشتیبانی', 'Support inbox'), robots: { index: false, follow: false } };
}

export default async function Page({ params }: Props) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return <AdminShell locale={locale} initial={await serverIdentity('admin')} workspace="support">
    <SupportInbox locale={locale}/>
  </AdminShell>;
}
