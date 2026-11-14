import { notFound } from 'next/navigation';
import { SavedBuilds } from '@/components/saved-builds';
import { isLocale } from '@/lib/content';

export default async function SavedBuildsPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return <main id="main-content" className="container workspace-page"><SavedBuilds locale={locale} /></main>;
}
