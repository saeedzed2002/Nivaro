import { notFound } from 'next/navigation';
import { isLocale } from '@/lib/content';
import { serverIdentity } from '@/lib/identity-server';
import { AdminShell } from '@/components/admin-shared';
import { AdminCategories } from '@/components/admin-categories';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Category administration', robots: { index: false, follow: false } };
export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return <AdminShell locale={locale} initial={await serverIdentity('admin')}><AdminCategories locale={locale}/></AdminShell>;
}
