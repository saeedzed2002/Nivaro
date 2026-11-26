'use client';

import Link from 'next/link';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { listStaffRefunds, type RefundFilters } from '@/lib/checkout-client';
import { checkoutTime } from '@/lib/checkout-copy';
import { formatCommerceMoney, isUuid, text, type Locale } from '@/lib/content';
import { useAdminSession } from './admin-shared';
import { accessLost, PaymentProblem, PaymentViews, refundLabels } from './payment-admin-shared';

export function RefundQueue({ locale }: { locale: Locale }) {
  const actor = useAdminSession();
  return actor ? <RefundQueueContent key={actor.profile.id} locale={locale} actorId={actor.profile.id}/> : null;
}

function RefundQueueContent({ locale, actorId }: { locale: Locale; actorId: string }) {
  const [filters, setFilters] = useState<RefundFilters>({ state: 'open' });
  const [invalid, setInvalid] = useState(false);
  const queue = useInfiniteQuery({
    queryKey: ['staff-payments', actorId, 'refunds', filters],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => listStaffRefunds(filters, pageParam, signal),
    getNextPageParam: page => page.next_before ?? undefined,
    retry: false, gcTime: 0,
  });
  const rows = [...new Map(queue.data?.pages.flatMap(page => page.refunds.map(refund => [refund.refund_id, refund] as const))).values()];
  const stateLabel = text(locale, 'وضعیت', 'State');
  const marketLabel = text(locale, 'بازار', 'Market');
  const capturedLabel = text(locale, 'مبلغ وصول‌شده', 'Captured');
  const refundedLabel = text(locale, 'بازپرداخت تأییدشده', 'Confirmed refunded');
  const retryLabel = text(locale, 'تلاش بعدی', 'Next retry');

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const orderId = String(fields.get('order') ?? '').trim();
    if (orderId && !isUuid(orderId)) { setInvalid(true); return; }
    setInvalid(false);
    setFilters({
      state: fields.get('state') as RefundFilters['state'],
      market: (fields.get('market') || undefined) as RefundFilters['market'],
      order_id: orderId || undefined,
    });
  }

  return <>
    <header className="admin-heading"><h1>{text(locale, 'صف بازپرداخت', 'Refund queue')}</h1></header>
    <PaymentViews locale={locale} current="refunds"/>
    {accessLost(queue.error) ? <PaymentProblem locale={locale} error={queue.error}/> : <>
      <form className="admin-panel admin-filter-row payment-filters" onSubmit={apply} onReset={() => { setFilters({ state: 'open' }); setInvalid(false); }}>
        <label><span id="refund-state-label">{stateLabel}</span><select aria-labelledby="refund-state-label" name="state" defaultValue="open">
          <option value="open">{text(locale, 'بازپرداخت‌های باز', 'Open refunds')}</option>
          <option value="all">{text(locale, 'همهٔ وضعیت‌ها', 'All states')}</option>
          {Object.entries(refundLabels).map(([state, [fa, en]]) => <option key={state} value={state}>{text(locale, fa, en)}</option>)}
        </select></label>
        <label><span id="refund-market-label">{marketLabel}</span><select aria-labelledby="refund-market-label" name="market">
          <option value="">{text(locale, 'همهٔ بازارها', 'All markets')}</option>
          <option value="ir">{text(locale, 'ایران', 'Iran')}</option>
          <option value="international">{text(locale, 'بین‌المللی', 'International')}</option>
        </select></label>
        <label className="payment-order-filter">{text(locale, 'شناسهٔ سفارش', 'Order reference')}
          <input name="order" dir="ltr" autoComplete="off" spellCheck={false} aria-invalid={invalid} aria-describedby={invalid ? 'refund-filter-error' : undefined} onChange={() => setInvalid(false)}/>
        </label>
        <div className="payment-filter-actions">
          <button type="submit" className="button primary">{text(locale, 'اعمال فیلترها', 'Apply filters')}</button>
          <button type="reset" className="button secondary">{text(locale, 'پاک‌کردن فیلترها', 'Clear filters')}</button>
        </div>
        {invalid && <p id="refund-filter-error" className="admin-notice error" role="alert">{text(locale, 'شناسهٔ کامل سفارش را وارد کنید.', 'Enter the full order reference.')}</p>}
      </form>
      <div className="refund-results">
        {queue.isPending && <p role="status">{text(locale, 'در حال دریافت صف بازپرداخت…', 'Loading refund queue…')}</p>}
        {queue.isError && <PaymentProblem locale={locale} error={queue.error} retry={() => void queue.refetch()}/>}
        {queue.isSuccess && !rows.length && <p className="admin-panel" role="status">{text(locale, 'بازپرداختی با این فیلترها پیدا نشد.', 'No refunds match these filters.')}</p>}
        {rows.length > 0 && <div className="admin-table-wrap">
          <table className="admin-table refund-table" aria-label={text(locale, 'فهرست بازپرداخت‌ها', 'Refund list')}>
            <thead><tr>
              <th scope="col">{text(locale, 'بازپرداخت و سفارش', 'Refund and order')}</th><th scope="col">{stateLabel}</th>
              <th scope="col">{capturedLabel}</th><th scope="col">{refundedLabel}</th><th scope="col">{retryLabel}</th>
              <th scope="col"><span className="sr-only">{text(locale, 'جزئیات', 'Details')}</span></th>
            </tr></thead>
            <tbody>{rows.map(row => <tr key={row.refund_id}>
              <td className="refund-reference"><bdi dir="ltr">{row.refund_id}</bdi>
                <small>{text(locale, 'سفارش', 'Order')} <bdi dir="ltr">{row.order_id}</bdi></small>
                <small><bdi>{row.reason}</bdi></small>
              </td>
              <td data-label={stateLabel}>
                <span className="payment-status" data-status={row.state}>{text(locale, refundLabels[row.state][0], refundLabels[row.state][1])}</span>
                {row.last_error && <small><bdi>{row.last_error}</bdi></small>}
              </td>
              <td data-label={capturedLabel}><bdi>{formatCommerceMoney(row.captured_minor, row.currency, locale)}</bdi></td>
              <td data-label={refundedLabel}><bdi>{formatCommerceMoney(row.confirmed_refund_minor, row.currency, locale)}</bdi></td>
              <td data-label={retryLabel}>{row.retry_at ? <time dateTime={row.retry_at}>{checkoutTime(row.retry_at, locale)}</time> : '—'}</td>
              <td><Link className="text-link" href={`/${locale}/admin/payments?attempt=${row.attempt_id}`}>{text(locale, 'مشاهدهٔ پرداخت', 'View payment')}</Link></td>
            </tr>)}</tbody>
          </table>
        </div>}
        {queue.hasNextPage && <button type="button" className="button secondary payment-more" disabled={queue.isFetching} onClick={() => void queue.fetchNextPage()}>{text(locale, 'نمایش موارد بیشتر', 'Load more refunds')}</button>}
      </div>
    </>}
  </>;
}
