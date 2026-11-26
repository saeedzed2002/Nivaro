import { notFound } from 'next/navigation';
import { AdminShell } from '@/components/admin-shared';
import { StaffOrders } from '@/components/staff-orders';
import { isLocale, text } from '@/lib/content';
import { serverIdentity } from '@/lib/identity-server';

type Props = { params: Promise<{ locale: string }>; searchParams: Promise<{ status?: string }> };

export async function generateMetadata({ params }: Props) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return { title: text(locale, 'مدیریت سفارش‌ها', 'Order administration'), robots: { index: false, follow: false } };
}

export default async function Page({ params, searchParams }: Props) {
  const [{ locale }, { status }] = await Promise.all([params, searchParams]);
  if (!isLocale(locale)) notFound();
  return <AdminShell locale={locale} initial={await serverIdentity('admin')} workspace="orders"><StaffOrders key={status ?? 'all'} locale={locale} preset={status}/></AdminShell>;
}
