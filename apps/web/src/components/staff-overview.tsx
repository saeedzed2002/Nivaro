'use client';

import Link from 'next/link';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { checkoutTime } from '@/lib/checkout-copy';
import { readOrderOverview, readRefundOverview, type OverviewDays } from '@/lib/checkout-client';
import { formatCommerceMoney, text, type Locale } from '@/lib/content';
import { listCatalogMediaQueue, readReviewOverview } from '@/lib/reviews-client';
import { listUnansweredSupport } from '@/lib/support-client';
import { useAdminSession } from './admin-shared';

export function StaffOverview({ locale }: { locale: Locale }) {
  const session = useAdminSession();
  return session ? <OverviewContent key={session.profile.id} locale={locale} actorId={session.profile.id} permissions={session.permissions}/> : null;
}

function OverviewContent({ locale, actorId, permissions }: { locale: Locale; actorId: string; permissions: string[] }) {
  const [days, setDays] = useState<OverviewDays>('7');
  const ordersAllowed = permissions.includes('orders.read');
  const refundsAllowed = permissions.includes('payments.read');
  const reviewsAllowed = permissions.includes('reviews.moderate');
  const supportAllowed = permissions.includes('support.reply');
  const mediaAllowed = permissions.includes('catalog.write');
  const scope = ['staff-overview', actorId] as const;
  const orders = useQuery({ queryKey: [...scope, 'orders', days], queryFn: ({ signal }) => readOrderOverview(days, signal), enabled: ordersAllowed, retry: false, gcTime: 0 });
  const refunds = useQuery({ queryKey: [...scope, 'refunds'], queryFn: ({ signal }) => readRefundOverview(signal), enabled: refundsAllowed, retry: false, gcTime: 0 });
  const reviews = useQuery({ queryKey: [...scope, 'reviews'], queryFn: ({ signal }) => readReviewOverview(signal), enabled: reviewsAllowed, retry: false, gcTime: 0 });
  const support = useQuery({ queryKey: [...scope, 'support'], queryFn: ({ signal }) => listUnansweredSupport(signal, undefined, 1), enabled: supportAllowed, retry: false, gcTime: 0 });
  const number = new Intl.NumberFormat(locale === 'fa' ? 'fa-IR' : 'en-US');
  const base = `/${locale}/admin`;
  const paidOrders = text(locale, 'سفارش‌های پرداخت‌شده', 'Paid orders');
  const gross = text(locale, 'فروش ناخالص', 'Gross sales');
  const refunded = text(locale, 'بازپرداخت تأییدشده', 'Confirmed refunds');
  const net = text(locale, 'فروش خالص', 'Net sales');
  return <>
    <header className="admin-heading"><h1>{text(locale, 'نمای کلی مدیریت', 'Staff overview')}</h1></header>
    {ordersAllowed && <section className="admin-panel overview-panel" aria-labelledby="overview-sales">
      <header className="overview-heading">
        <h2 id="overview-sales">{text(locale, 'خلاصهٔ فروش', 'Sales summary')}</h2>
        <label className="admin-filter-row overview-period"><span id="overview-period-label">{text(locale, 'بازهٔ گزارش', 'Reporting period')}</span>
          <select aria-labelledby="overview-period-label" value={days} onChange={event => setDays(event.target.value as OverviewDays)}>
            {(['7', '30', '90'] as const).map(value => <option key={value} value={value}>{text(locale, `${number.format(Number(value))} روز اخیر`, `Last ${value} days`)}</option>)}
          </select>
        </label>
      </header>
      {orders.isPending && <p role="status" className="overview-note">{text(locale, 'در حال دریافت گزارش…', 'Loading sales…')}</p>}
      {orders.isError && <QueueStatus locale={locale} error retry={() => void orders.refetch()}/>}
      {orders.isSuccess && <>
        <table className="admin-table overview-sales" aria-labelledby="overview-sales">
          <thead><tr><th scope="col">{text(locale, 'بازار', 'Market')}</th><th scope="col">{paidOrders}</th><th scope="col">{gross}</th><th scope="col">{refunded}</th><th scope="col">{net}</th></tr></thead>
          <tbody>{orders.data.sales.map(row => <tr key={row.currency}>
            <td>{row.market === 'ir' ? text(locale, 'ایران', 'Iran') : text(locale, 'بین‌المللی', 'International')}</td>
            <td data-label={paidOrders}>{number.format(row.paid_orders)}</td>
            <td data-label={gross}><bdi>{formatCommerceMoney(row.gross_minor, row.currency, locale)}</bdi></td>
            <td data-label={refunded}><bdi>{formatCommerceMoney(row.confirmed_refund_minor, row.currency, locale)}</bdi></td>
            <td data-label={net}><bdi>{formatCommerceMoney(row.net_minor, row.currency, locale)}</bdi></td>
          </tr>)}</tbody>
        </table>
        <p className="overview-note">{text(locale, 'بازپرداخت‌های تأییدشدهٔ سفارش‌های همین بازه تا زمان گزارش از فروش کم شده‌اند.', 'Net sales deduct confirmed refunds for orders paid in this period, as of the report time.')} <time dateTime={orders.data.paid_before}>{checkoutTime(orders.data.paid_before, locale)}</time></p>
      </>}
    </section>}
    {(ordersAllowed || refundsAllowed || reviewsAllowed || supportAllowed || mediaAllowed) && <section className="admin-panel overview-panel" aria-labelledby="overview-work">
      <header className="overview-heading"><h2 id="overview-work">{text(locale, 'صف‌های عملیاتی', 'Operational queues')}</h2></header>
      <ul className="overview-queues">
        {ordersAllowed && <>
          <QueueRow label={text(locale, 'آماده‌سازی و ارسال', 'Fulfillment')}>
            <QueueStatus locale={locale} error={orders.isError} retry={() => void orders.refetch()} loading={orders.isPending}/>
            <Link href={`${base}/orders?status=paid`}>{text(locale, 'در انتظار آماده‌سازی', 'Awaiting preparation')}{orders.isSuccess && ` (${number.format(orders.data.paid)})`}</Link>
            <Link href={`${base}/orders?status=processing`}>{text(locale, 'در انتظار ارسال', 'Awaiting shipment')}{orders.isSuccess && ` (${number.format(orders.data.processing)})`}</Link>
            <Link href={`${base}/orders?status=shipped`}>{text(locale, 'در انتظار تحویل', 'Awaiting delivery')}{orders.isSuccess && ` (${number.format(orders.data.shipped)})`}</Link>
          </QueueRow>
          <QueueRow label={text(locale, 'سفارش‌های نیازمند بررسی پرداخت', 'Orders in payment review')}>
            <QueueStatus locale={locale} error={orders.isError} loading={orders.isPending} count={orders.isSuccess ? number.format(orders.data.payment_review) : undefined}/>
            <Link href={`${base}/orders?status=payment_review`}>{text(locale, 'مشاهدهٔ سفارش‌ها', 'Open orders')}</Link>
          </QueueRow>
        </>}
        {refundsAllowed && <QueueRow label={text(locale, 'بازپرداخت‌های نیازمند بررسی دستی', 'Refunds needing manual review')}>
          <QueueStatus locale={locale} error={refunds.isError} loading={refunds.isPending} count={refunds.isSuccess ? number.format(refunds.data.manual_review) : undefined} retry={() => void refunds.refetch()}/>
          <Link href={`${base}/payments?view=refunds&state=manual_review`}>{text(locale, 'مشاهدهٔ بازپرداخت‌ها', 'Open refunds')}</Link>
          <Link href={`${base}/payments`}>{text(locale, 'تلاش‌های پرداخت', 'Payment attempts')}</Link>
        </QueueRow>}
        {reviewsAllowed && <QueueRow label={text(locale, 'دیدگاه‌های در انتظار بررسی', 'Pending reviews')}>
          <QueueStatus locale={locale} error={reviews.isError} loading={reviews.isPending} count={reviews.isSuccess ? number.format(reviews.data.pending) : undefined} retry={() => void reviews.refetch()}/>
          <Link href={`${base}/reviews`}>{text(locale, 'مشاهدهٔ دیدگاه‌ها', 'Open reviews')}</Link>
        </QueueRow>}
        {mediaAllowed && <QueueRow label={text(locale, 'پردازش تصاویر محصولات', 'Product image jobs')}><a href="#overview-images">{text(locale, 'مشاهدهٔ پردازش‌ها', 'View image jobs')}</a></QueueRow>}
        {supportAllowed && <QueueRow label={text(locale, 'گفت‌وگوهای بی‌پاسخ', 'Unanswered support')}>
          <QueueStatus locale={locale} error={support.isError} loading={support.isPending} count={support.isSuccess ? number.format(support.data.total) : undefined} retry={() => void support.refetch()}/>
          <Link href={`${base}/support?unanswered=1`}>{text(locale, 'مشاهدهٔ گفت‌وگوهای بی‌پاسخ', 'Open unanswered inbox')}</Link>
        </QueueRow>}
      </ul>
    </section>}
    {mediaAllowed && <ImageQueue locale={locale} actorId={actorId}/>}
  </>;
}

function QueueRow({ label, children }: { label: string; children: ReactNode }) {
  return <li><strong>{label}</strong><div>{children}</div></li>;
}

function QueueStatus({ locale, error, loading, count, retry }: { locale: Locale; error?: boolean; loading?: boolean; count?: string; retry?: () => void }) {
  if (error) return <span className="overview-status" role="status">{text(locale, 'دریافت داده ممکن نشد.', 'Data unavailable.')} {retry && <button type="button" className="text-link" onClick={retry}>{text(locale, 'تلاش دوباره', 'Retry')}</button>}</span>;
  if (loading) return <span className="overview-status" role="status">{text(locale, 'در حال دریافت…', 'Loading…')}</span>;
  return count === undefined ? null : <bdi className="overview-count">{count}</bdi>;
}

function ImageQueue({ locale, actorId }: { locale: Locale; actorId: string }) {
  const jobs = useInfiniteQuery({
    queryKey: ['staff-overview', actorId, 'image-jobs'], initialPageParam: undefined as string | undefined,
    queryFn: ({ signal, pageParam }) => listCatalogMediaQueue(pageParam, signal), getNextPageParam: page => page.next_before ?? undefined,
    gcTime: 0, retry: false,
  });
  const rows = [...new Map(jobs.data?.pages.flatMap(page => page.jobs.map(job => [job.id, job] as const))).values()];
  const labels = { uploaded: ['در صف', 'Queued'], processing: ['در حال پردازش', 'Processing'], ready: ['آماده', 'Ready'], failed: ['ناموفق', 'Failed'] } as const;
  return <section className="admin-panel overview-panel" id="overview-images" aria-labelledby="overview-images-heading">
    <header className="overview-heading"><h2 id="overview-images-heading">{text(locale, 'پردازش تصاویر محصولات', 'Product image jobs')}</h2></header>
    <div className="overview-image-content">
      <QueueStatus locale={locale} error={jobs.isError} loading={jobs.isPending} retry={() => void jobs.refetch()}/>
      {jobs.isSuccess && !rows.length && <p>{text(locale, 'تصویری در صف، در حال پردازش یا ناموفق نیست.', 'No queued, processing or failed images.')}</p>}
      {jobs.isSuccess && rows.length > 0 && <ul className="overview-queues">{rows.map(job => <QueueRow key={job.id} label={text(locale, labels[job.state][0], labels[job.state][1])}>
        {job.error_code && <bdi>{job.error_code}</bdi>}
        <time dateTime={job.created_at}>{checkoutTime(job.created_at, locale)}</time>
        <Link href={`/${locale}/admin/products/${job.product_id}`} title={job.product_id}>{text(locale, 'باز کردن محصول', 'Open product')}</Link>
      </QueueRow>)}</ul>}
      {jobs.hasNextPage && <button type="button" className="button secondary" disabled={jobs.isFetching} onClick={() => void jobs.fetchNextPage()}>{text(locale, 'پردازش‌های بیشتر', 'Load more jobs')}</button>}
    </div>
  </section>;
}
