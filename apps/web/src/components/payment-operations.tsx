'use client';

import Link from 'next/link';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useRef, useState, type FormEvent } from 'react';
import { listPaymentAttempts, readPaymentAttempt, type PaymentAttempt, type PaymentDetails, type PaymentFilters } from '@/lib/checkout-client';
import { checkoutTime } from '@/lib/checkout-copy';
import { formatCommerceMoney, isUuid, text, type Locale } from '@/lib/content';
import { accessLost, PaymentProblem, PaymentViews, refundLabels } from './payment-admin-shared';
import { useAdminSession } from './admin-shared';
import { OrderStateLabel } from './order-history';

const attemptLabels = {
  pending: ['در انتظار', 'Pending'],
  ambiguous: ['نامشخص', 'Ambiguous'],
  failed: ['ناموفق', 'Failed'],
  succeeded: ['موفق', 'Succeeded'],
  amount_mismatch: ['مغایرت مبلغ', 'Amount mismatch'],
} as const satisfies Record<PaymentAttempt['status'], readonly [string, string]>;

function AttemptStatus({ status, locale }: { status: PaymentAttempt['status']; locale: Locale }) {
  const [fa, en] = attemptLabels[status];
  return <span className="payment-status" data-status={status}>{text(locale, fa, en)}</span>;
}

function TimeValue({ value, locale, empty = '—' }: { value: string | null; locale: Locale; empty?: string }) {
  return value ? <time dateTime={value}>{checkoutTime(value, locale)}</time> : empty;
}

export function PaymentOperations({ locale, initialAttempt }: { locale: Locale; initialAttempt?: string }) {
  const actor = useAdminSession();
  return actor ? <PaymentWorkspace key={`${actor.profile.id}:${initialAttempt ?? ''}`} locale={locale} actorId={actor.profile.id} initialAttempt={initialAttempt}/> : null;
}

function PaymentWorkspace({ locale, actorId, initialAttempt }: { locale: Locale; actorId: string; initialAttempt?: string }) {
  const [filters, setFilters] = useState<PaymentFilters>({});
  const [selected, setSelected] = useState(initialAttempt);
  const [invalid, setInvalid] = useState(false);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const list = useInfiniteQuery({
    queryKey: ['staff-payments', actorId, 'list', filters],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => listPaymentAttempts(filters, pageParam, signal),
    getNextPageParam: page => page.next_before ?? undefined,
    retry: false, gcTime: 0,
  });
  const rows = [...new Map(list.data?.pages.flatMap(page => page.attempts.map(attempt => [attempt.id, attempt] as const))).values()];
  const id = selected ?? rows[0]?.id;
  const detail = useQuery({
    queryKey: ['staff-payments', actorId, 'detail', id],
    queryFn: ({ signal }) => readPaymentAttempt(id!, signal),
    enabled: !!id && !accessLost(list.error), retry: false, gcTime: 0,
  });
  const accessError = [list.error, detail.error].find(accessLost);
  const orderLabel = text(locale, 'شناسهٔ سفارش', 'Order reference');
  const statusLabel = text(locale, 'وضعیت', 'Status');
  const marketLabel = text(locale, 'بازار', 'Market');
  const expectedLabel = text(locale, 'مبلغ مورد انتظار', 'Expected amount');
  const capturedLabel = text(locale, 'مبلغ وصول‌شده', 'Captured amount');

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const orderId = String(fields.get('order') ?? '').trim();
    if (orderId && !isUuid(orderId)) { setInvalid(true); return; }
    setInvalid(false);
    setSelected(undefined);
    setFilters({
      status: (fields.get('status') || undefined) as PaymentFilters['status'],
      market: (fields.get('market') || undefined) as PaymentFilters['market'],
      order_id: orderId || undefined,
    });
  }

  function selectAttempt(attempt: PaymentAttempt) {
    setSelected(attempt.id);
    if (window.matchMedia('(max-width: 1080px)').matches) detailHeading.current?.focus();
  }

  return <>
    <header className="admin-heading"><h1>{text(locale, 'پرداخت‌ها و تطبیق', 'Payments & reconciliation')}</h1></header>
    <PaymentViews locale={locale} current="attempts"/>
    {accessError ? <PaymentProblem locale={locale} error={accessError}/> : <>
      <form className="admin-panel admin-filter-row payment-filters" onSubmit={applyFilters} onReset={() => { setInvalid(false); setSelected(undefined); setFilters({}); }}>
        <label><span id="payment-status-label">{statusLabel}</span><select aria-labelledby="payment-status-label" name="status">
          <option value="">{text(locale, 'همهٔ وضعیت‌ها', 'All statuses')}</option>
          {Object.entries(attemptLabels).map(([status, [fa, en]]) => <option key={status} value={status}>{text(locale, fa, en)}</option>)}
        </select></label>
        <label><span id="payment-market-label">{marketLabel}</span><select aria-labelledby="payment-market-label" name="market">
          <option value="">{text(locale, 'همهٔ بازارها', 'All markets')}</option>
          <option value="ir">{text(locale, 'ایران', 'Iran')}</option>
          <option value="international">{text(locale, 'بین‌المللی', 'International')}</option>
        </select></label>
        <label className="payment-order-filter">{orderLabel}<input name="order" type="text" autoComplete="off" spellCheck={false} dir="ltr" aria-invalid={invalid} aria-describedby={invalid ? 'payment-filter-error' : undefined} onChange={() => setInvalid(false)}/></label>
        <div className="payment-filter-actions">
          <button type="submit" className="button primary">{text(locale, 'اعمال فیلترها', 'Apply filters')}</button>
          <button type="reset" className="button secondary">{text(locale, 'پاک‌کردن فیلترها', 'Clear filters')}</button>
        </div>
        {invalid && <p id="payment-filter-error" role="alert" className="admin-notice error">{text(locale, 'شناسهٔ کامل سفارش را وارد کنید.', 'Enter the full order reference.')}</p>}
      </form>
      <p className="payment-simulator">{text(locale, 'پرداخت‌های این صفحه با شبیه‌ساز ثبت شده‌اند.', 'This workspace shows simulator payments.')}</p>
      <div className="payment-layout">
        <section className="admin-panel payment-panel" aria-labelledby="payment-attempts-heading">
          <h2 id="payment-attempts-heading">{text(locale, 'تلاش‌های پرداخت', 'Payment attempts')}</h2>
          {list.isPending && <p role="status">{text(locale, 'در حال دریافت پرداخت‌ها…', 'Loading payment attempts…')}</p>}
          {list.isError && <PaymentProblem locale={locale} error={list.error} retry={() => void list.refetch()}/>}
          {list.isSuccess && !rows.length && <p role="status">{text(locale, 'پرداختی با این فیلترها پیدا نشد.', 'No payment attempts match these filters.')}</p>}
          {rows.length > 0 && <table className="payment-table" aria-labelledby="payment-attempts-heading">
            <thead><tr><th scope="col">{orderLabel}</th><th scope="col">{expectedLabel}</th><th scope="col">{capturedLabel}</th><th scope="col">{statusLabel}</th></tr></thead>
            <tbody>{rows.map(attempt => <tr key={attempt.id} data-selected={attempt.id === id}>
              <td><button type="button" aria-pressed={attempt.id === id} className="payment-select" onClick={() => selectAttempt(attempt)}>
                <bdi dir="ltr" title={attempt.order_id}>{attempt.order_id.slice(0, 8)}…</bdi>
                <span className="sr-only">{text(locale, 'شناسهٔ تلاش پرداخت', 'Payment attempt')} <bdi>{attempt.id}</bdi></span>
                <small><TimeValue value={attempt.created_at} locale={locale}/><bdi>{attempt.currency}</bdi></small>
              </button></td>
              <td><bdi>{formatCommerceMoney(attempt.amount_minor, attempt.currency, locale)}</bdi></td>
              <td><bdi>{attempt.captured_minor === null ? '—' : formatCommerceMoney(attempt.captured_minor, attempt.currency, locale)}</bdi></td>
              <td><AttemptStatus status={attempt.status} locale={locale}/></td>
            </tr>)}</tbody>
          </table>}
          {list.hasNextPage && <button type="button" className="button secondary payment-more" disabled={list.isFetching} onClick={() => void list.fetchNextPage()}>{text(locale, 'نمایش پرداخت‌های بیشتر', 'Load more attempts')}</button>}
        </section>
        {id && <section className="admin-panel payment-panel" aria-labelledby="payment-detail-heading">
          <h2 id="payment-detail-heading" ref={detailHeading} tabIndex={-1}>{text(locale, 'جزئیات پرداخت', 'Payment detail')}</h2>
          {detail.isPending && <p role="status">{text(locale, 'در حال دریافت جزئیات…', 'Loading payment detail…')}</p>}
          {detail.isError && <PaymentProblem locale={locale} error={detail.error} retry={() => void detail.refetch()}/>}
          {detail.isSuccess && <AttemptSummary attempt={detail.data.attempt} locale={locale}/>}
        </section>}
      </div>
      {detail.isSuccess && <PaymentOutcome details={detail.data} locale={locale}/>}
    </>}
  </>;
}

function AttemptSummary({ attempt, locale }: { attempt: PaymentAttempt; locale: Locale }) {
  const difference = attempt.captured_minor === null ? null : attempt.captured_minor - attempt.amount_minor;
  const money = (amount: number) => formatCommerceMoney(amount, attempt.currency, locale);
  return <dl className="payment-values">
    <div><dt>{text(locale, 'شناسهٔ تلاش', 'Attempt ID')}</dt><dd><bdi dir="ltr">{attempt.id}</bdi></dd></div>
    <div><dt>{text(locale, 'شناسهٔ سفارش', 'Order reference')}</dt><dd><bdi dir="ltr">{attempt.order_id}</bdi></dd></div>
    <div><dt>{text(locale, 'بازار', 'Market')}</dt><dd>{attempt.market === 'ir' ? text(locale, 'ایران', 'Iran') : text(locale, 'بین‌المللی', 'International')} <bdi>({attempt.currency})</bdi></dd></div>
    <div><dt>{text(locale, 'شناسهٔ درگاه', 'Provider reference')}</dt><dd><bdi dir="ltr">{attempt.provider_reference}</bdi></dd></div>
    <div><dt>{text(locale, 'وضعیت پرداخت', 'Payment status')}</dt><dd><AttemptStatus status={attempt.status} locale={locale}/></dd></div>
    <div><dt>{text(locale, 'مبلغ مورد انتظار', 'Expected amount')}</dt><dd><bdi>{money(attempt.amount_minor)}</bdi></dd></div>
    <div><dt>{text(locale, 'مبلغ وصول‌شده', 'Captured amount')}</dt><dd><bdi>{attempt.captured_minor === null ? '—' : money(attempt.captured_minor)}</bdi></dd></div>
    <div><dt>{text(locale, 'اختلاف مبلغ', 'Difference')}</dt><dd data-discrepancy={difference !== null && difference !== 0}>
      <bdi>{difference === null ? '—' : `${difference < 0 ? '−' : difference > 0 ? '+' : ''}${money(Math.abs(difference))}`}</bdi>
    </dd></div>
    <div><dt>{text(locale, 'تاریخ ثبت', 'Created')}</dt><dd><TimeValue value={attempt.created_at} locale={locale}/></dd></div>
    <div><dt>{text(locale, 'تأیید درگاه', 'Verified')}</dt><dd><TimeValue value={attempt.verified_at} locale={locale}/></dd></div>
  </dl>;
}

function PaymentOutcome({ details, locale }: { details: PaymentDetails; locale: Locale }) {
  const { attempt, order } = details;
  const refund = order?.compensation;
  return <div className="payment-outcome">
    <section className="admin-panel payment-panel" aria-labelledby="payment-reconciliation-heading">
      <h2 id="payment-reconciliation-heading">{text(locale, 'تطبیق پرداخت', 'Reconciliation')}</h2>
      <dl className="payment-values">
        <div><dt>{text(locale, 'بررسی بعدی', 'Next check')}</dt><dd><TimeValue locale={locale} value={attempt.reconcile_at} empty={text(locale, 'زمان‌بندی نشده', 'Not scheduled')}/></dd></div>
        <div><dt>{text(locale, 'دفعات بررسی', 'Reconciliation attempts')}</dt><dd>{new Intl.NumberFormat(locale === 'fa' ? 'fa-IR' : 'en-US').format(attempt.reconciliation_attempts)}</dd></div>
      </dl>
    </section>
    <section className="admin-panel payment-panel" aria-labelledby="payment-order-heading">
      <h2 id="payment-order-heading">{text(locale, 'سفارش و بازپرداخت', 'Order & refund')}</h2>
      {order ? <>
        <dl className="payment-values">
          <div><dt>{text(locale, 'وضعیت سفارش', 'Order status')}</dt><dd><OrderStateLabel locale={locale} status={order.status}/> <Link className="text-link" href={`/${locale}/admin/orders/${attempt.order_id}`}>{text(locale, 'مشاهدهٔ سفارش', 'View order')}</Link></dd></div>
          <div><dt>{text(locale, 'مبلغ سفارش', 'Order total')}</dt><dd><bdi>{formatCommerceMoney(order.total_minor, order.currency, locale)}</bdi></dd></div>
          <div><dt>{text(locale, 'نتیجهٔ ثبت‌شده در سفارش', 'Recorded payment outcome')}</dt><dd><bdi>{order.recorded_outcome ?? '—'}</bdi></dd></div>
          {order.disposition && <div><dt>{text(locale, 'نحوهٔ رسیدگی', 'Payment disposition')}</dt><dd><bdi>{order.disposition}</bdi></dd></div>}
          {order.reservation_error && <div><dt>{text(locale, 'خطای ثبت‌شده', 'Recorded error')}</dt><dd><bdi>{order.reservation_error}</bdi></dd></div>}
        </dl>
        {refund ? <dl className="payment-values payment-refund">
          <div><dt>{text(locale, 'شناسهٔ بازپرداخت', 'Refund ID')}</dt><dd><bdi dir="ltr">{refund.refund_id}</bdi></dd></div>
          <div><dt>{text(locale, 'وضعیت بازپرداخت', 'Refund state')}</dt><dd><span className="payment-status" data-status={refund.state}>{text(locale, refundLabels[refund.state][0], refundLabels[refund.state][1])}</span></dd></div>
          <div><dt>{text(locale, 'مبلغ وصول‌شده برای جبران', 'Captured amount to compensate')}</dt><dd><bdi>{formatCommerceMoney(refund.captured_minor, order.currency, locale)}</bdi></dd></div>
          <div><dt>{text(locale, 'دلیل بازپرداخت', 'Refund reason')}</dt><dd><bdi>{refund.reason}</bdi></dd></div>
          {refund.retry_at && <div><dt>{text(locale, 'تلاش بعدی', 'Next retry')}</dt><dd><TimeValue value={refund.retry_at} locale={locale}/></dd></div>}
          {refund.last_error && <div><dt>{text(locale, 'آخرین خطای بازپرداخت', 'Last refund error')}</dt><dd><bdi>{refund.last_error}</bdi></dd></div>}
        </dl> : <p>{text(locale, 'برای این تلاش بازپرداختی ثبت نشده است.', 'No refund is recorded for this attempt.')}</p>}
      </> : <p>{text(locale, 'اطلاعات سفارش برای این تلاش در دسترس نیست.', 'Order information is unavailable for this attempt.')}</p>}
    </section>
  </div>;
}
