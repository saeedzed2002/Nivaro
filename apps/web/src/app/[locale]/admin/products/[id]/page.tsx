import { notFound } from 'next/navigation';
import { isLocale } from '@/lib/content';
import { serverIdentity } from '@/lib/identity-server';
import { AdminShell } from '@/components/admin-shared';
import { AdminProductEditor } from '@/components/admin-product-editor';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Product editor', robots: { index: false, follow: false } };
export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  const { locale, id } = await params;
  if (!isLocale(locale) || (id !== 'new' && !/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id))) notFound();
  return <AdminShell locale={locale} initial={await serverIdentity('admin')}><AdminProductEditor key={id} id={id} locale={locale}/></AdminShell>;
}
