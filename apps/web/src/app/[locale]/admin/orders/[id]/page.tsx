import { notFound } from 'next/navigation';
import { AdminShell } from '@/components/admin-shared';
import { StaffOrderDetails } from '@/components/staff-order-details';
import { isLocale, text } from '@/lib/content';
import { serverIdentity } from '@/lib/identity-server';

type Props = { params: Promise<{ locale: string; id: string }> };

export async function generateMetadata({ params }: Props) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return { title: text(locale, 'جزئیات سفارش', 'Order details'), robots: { index: false, follow: false } };
}

export default async function Page({ params }: Props) {
  const { locale, id } = await params;
  if (!isLocale(locale) || !/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id)) notFound();
  return <AdminShell locale={locale} initial={await serverIdentity('admin')} workspace="orders"><StaffOrderDetails id={id} locale={locale}/></AdminShell>;
}
