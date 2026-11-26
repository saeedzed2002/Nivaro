import { notFound } from 'next/navigation';
import { AdminShell } from '@/components/admin-shared';
import { PaymentOperations } from '@/components/payment-operations';
import { RefundQueue } from '@/components/refund-queue';
import { isLocale, isUuid, text } from '@/lib/content';
import { serverIdentity } from '@/lib/identity-server';

type Props = { params: Promise<{ locale: string }>; searchParams: Promise<{ attempt?: string | string[]; view?: string | string[]; state?: string }> };

export async function generateMetadata({ params, searchParams }: Props) {
  const [{ locale }, { view }] = await Promise.all([params, searchParams]);
  if (!isLocale(locale)) notFound();
  const title = view === 'refunds' ? text(locale, 'صف بازپرداخت', 'Refund queue') : text(locale, 'پرداخت‌ها و تطبیق', 'Payments & reconciliation');
  return { title, robots: { index: false, follow: false } };
}

export default async function Page({ params, searchParams }: Props) {
  const [{ locale }, { attempt, view, state }] = await Promise.all([params, searchParams]);
  if (!isLocale(locale)) notFound();
  return <AdminShell locale={locale} initial={await serverIdentity('admin')} workspace="payments">
    {view === 'refunds' ? <RefundQueue key={state === 'manual_review' ? 'manual' : 'open'} locale={locale} initialState={state === 'manual_review' ? 'manual_review' : 'open'}/>
      : <PaymentOperations locale={locale} initialAttempt={typeof attempt === 'string' && isUuid(attempt) ? attempt.toLowerCase() : undefined}/>}
  </AdminShell>;
}
