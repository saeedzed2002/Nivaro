import { notFound } from 'next/navigation';
import { isLocale } from '@/lib/content';
import { serverIdentity } from '@/lib/identity-server';
import { AdminShell } from '@/components/admin-shared';
import { StaffProfile } from '@/components/staff-profile';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Staff profile', robots: { index: false, follow: false } };
export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return <AdminShell selfProfile locale={locale} initial={await serverIdentity('admin')}><StaffProfile locale={locale}/></AdminShell>;
}
