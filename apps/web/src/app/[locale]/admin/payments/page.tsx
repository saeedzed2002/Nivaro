import { notFound } from 'next/navigation';
import { AdminShell } from '@/components/admin-shared';
import { PaymentOperations } from '@/components/payment-operations';
import { isLocale, text } from '@/lib/content';
import { serverIdentity } from '@/lib/identity-server';

type Props = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: Props) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return { title: text(locale, 'پرداخت‌ها و تطبیق', 'Payments & reconciliation'), robots: { index: false, follow: false } };
}

export default async function Page({ params }: Props) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return <AdminShell locale={locale} initial={await serverIdentity('admin')} workspace="payments">
    <PaymentOperations locale={locale}/>
  </AdminShell>;
}
