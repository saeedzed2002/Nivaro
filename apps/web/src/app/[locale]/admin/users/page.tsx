import { notFound } from 'next/navigation';
import { AccountManagement } from '@/components/account-management';
import { AdminShell } from '@/components/admin-shared';
import { isLocale, text } from '@/lib/content';
import { serverIdentity } from '@/lib/identity-server';

type Props = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: Props) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return { title: text(locale, 'حساب‌ها و ممیزی', 'Accounts & audit'), robots: { index: false, follow: false } };
}

export default async function Page({ params }: Props) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return <AdminShell locale={locale} initial={await serverIdentity('admin')} workspace="accounts">
    <AccountManagement locale={locale}/>
  </AdminShell>;
}
