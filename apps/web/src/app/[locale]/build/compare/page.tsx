import { notFound } from 'next/navigation';
import { SavedBuildComparison } from '@/components/saved-builds';
import { isLocale } from '@/lib/content';

export default async function SystemComparisonPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return <main id="main-content" className="container workspace-page"><SavedBuildComparison locale={locale} /></main>;
}
