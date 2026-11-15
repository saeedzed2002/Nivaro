'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';
import { listCustomerOrders, type OrderStatus } from '@/lib/checkout-client';
import { checkoutError, checkoutTime, loginRequired } from '@/lib/checkout-copy';
import { formatCommerceMoney, text, type Locale } from '@/lib/content';

const labels: Record<OrderStatus['status'], [string, string]> = {
  pending_reservation: ['در حال رزرو', 'Reserving stock'],
  awaiting_payment: ['در انتظار پرداخت', 'Awaiting payment'],
  payment_processing: ['در حال تأیید موجودی', 'Confirming stock'],
  paid: ['پرداخت‌شده', 'Paid'],
  expired: ['منقضی‌شده', 'Expired'],
  cancelled: ['لغوشده', 'Cancelled'],
  payment_review: ['نیازمند بررسی', 'Needs review'],
  refund_pending: ['در حال بازپرداخت', 'Refund in progress'],
  refunded: ['بازپرداخت‌شده', 'Refunded'],
};

export function OrderStateLabel({ locale, status }: { locale: Locale; status: OrderStatus['status'] }) {
  return <span className="order-state" data-status={status}>{text(locale, ...labels[status])}</span>;
}

export function OrderLoadError({ locale, error, signIn, retry }: { locale: Locale; error: Error; signIn: string; retry: () => void }) {
  return <div className="identity-panel order-empty"><p role="alert">{checkoutError(locale, error)}</p>
    {loginRequired(error) ? <Link className="button primary" href={signIn}>{text(locale, 'ورود به حساب', 'Sign in')}</Link>
      : <button className="button secondary" onClick={retry}>{text(locale, 'تلاش مجدد', 'Retry')}</button>}
  </div>;
}

export function OrderHistory({ locale, customerId }: { locale: Locale; customerId: string }) {
  const [pages, setPages] = useState<(string | undefined)[]>([undefined]);
  const before = pages.at(-1);
  const history = useQuery({
    queryKey: ['account', 'orders', customerId, 'history', before],
    queryFn: ({ signal }) => listCustomerOrders(before, signal),
    retry: false, gcTime: 0,
  });
  if (history.isPending) return <p role="status">{text(locale, 'در حال دریافت سفارش‌ها…', 'Loading your orders…')}</p>;
  if (history.isError) return <OrderLoadError locale={locale} error={history.error} signIn={`/${locale}/login?next=orders`} retry={() => void history.refetch()}/>;
  const { orders, next_before: next } = history.data;
  if (!orders.length && pages.length === 1) return <div className="identity-panel order-empty">
    <p>{text(locale, 'هنوز سفارشی ثبت نکرده‌ای.', 'You haven’t placed an order yet.')}</p>
    <Link className="button secondary" href={`/${locale}/products`}>{text(locale, 'مشاهدهٔ کالاها', 'Browse products')}</Link>
  </div>;

  return <>
    <ul className="order-history">
      {orders.map(order => <li key={order.id} className="order-history-entry identity-panel">
        <div><span className="muted">{text(locale, 'شناسهٔ سفارش', 'Order reference')}</span><bdi dir="ltr" className="order-reference">{order.id}</bdi></div>
        <div><span className="muted">{text(locale, 'تاریخ ثبت', 'Placed')}</span><time dateTime={order.created_at}>{checkoutTime(order.created_at, locale)}</time></div>
        <div><span className="muted">{text(locale, 'مبلغ نهایی', 'Total')}</span><bdi>{formatCommerceMoney(order.total_minor, order.currency, locale)}</bdi></div>
        <OrderStateLabel locale={locale} status={order.status}/>
        <Link className="text-link order-open" href={`/${locale}/checkout/result?order=${order.id}`}>{text(locale, 'وضعیت سفارش', 'Order status')}</Link>
      </li>)}
    </ul>
    {(pages.length > 1 || next) && <nav className="order-pages" aria-label={text(locale, 'صفحه‌بندی سفارش‌ها', 'Order history pages')}>
      <button className="button secondary" disabled={pages.length === 1} onClick={() => setPages(items => items.slice(0, -1))}>{text(locale, 'سفارش‌های جدیدتر', 'Newer orders')}</button>
      <button className="button secondary" disabled={!next} onClick={() => { if (next) setPages(items => [...items, next]); }}>{text(locale, 'سفارش‌های قدیمی‌تر', 'Older orders')}</button>
    </nav>}
  </>;
}
