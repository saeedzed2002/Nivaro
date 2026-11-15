'use client';

import Link from 'next/link';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { listStaffOrders, type OrderStatus } from '@/lib/checkout-client';
import { checkoutTime } from '@/lib/checkout-copy';
import { formatCommerceMoney, text, type Locale } from '@/lib/content';
import { IdentityError } from '@/lib/identity-client';
import { useAdminSession } from './admin-shared';
import { OrderStateLabel, orderStates, orderStateText } from './order-history';

export function StaffOrderError({ error, locale, reload }: { error: unknown; locale: Locale; reload?: () => void }) {
  const issue = error instanceof IdentityError ? error : null;
  const message = issue?.status === 401 ? text(locale, 'نشست کارکنان پایان یافته است.', 'Your staff session has ended.')
    : issue?.status === 403 ? text(locale, 'مجوز انجام این عملیات را ندارید.', 'You do not have permission for this operation.')
    : issue?.status === 404 ? text(locale, 'سفارش پیدا نشد.', 'Order not found.')
    : issue?.status === 409 ? text(locale, 'وضعیت سفارش تغییر کرده است. پیش از اقدام دوباره، سفارش را بارگیری کنید.', 'The order changed. Reload the order before trying again.')
    : issue?.status === 422 ? text(locale, 'مقادیر واردشده را بررسی کنید.', 'Check the values entered.')
    : text(locale, 'پاسخ دریافت نشد. دوباره تلاش کنید یا وضعیت فعلی را بارگیری کنید.', 'No response received. Try again or reload the current state.');
  return <div className="admin-notice error" role="alert"><div>{message}
    {issue?.status === 401 && <Link className="text-link" href={`/${locale}/admin/login`}>{text(locale, 'ورود مدیران', 'Administrator sign-in')}</Link>}
    {reload && issue?.status !== 401 && issue?.status !== 403 && <button className="button secondary" onClick={reload}>{text(locale, 'بارگیری دوباره', 'Reload')}</button>}
  </div></div>;
}

export function StaffOrders({ locale }: { locale: Locale }) {
  const session = useAdminSession();
  const [status, setStatus] = useState<OrderStatus['status'] | ''>('');
  const history = useInfiniteQuery({
    queryKey: ['staff', session?.profile.id, 'orders', status],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => listStaffOrders(status || undefined, pageParam, signal),
    getNextPageParam: last => last.next_before ?? undefined,
    retry: false, gcTime: 0,
  });
  const placed = text(locale, 'تاریخ ثبت', 'Placed');
  const market = text(locale, 'بازار', 'Market');
  const total = text(locale, 'مبلغ نهایی', 'Total');
  const state = text(locale, 'وضعیت', 'Status');
  const denied = history.error instanceof IdentityError && [401, 403].includes(history.error.status);
  const orders = new Map(denied ? [] : history.data?.pages.flatMap(page => page.orders.map(order => [order.id, order] as const)));
  return <>
    <header className="admin-heading"><h1>{text(locale, 'سفارش‌ها', 'Orders')}</h1></header>
    <div className="admin-filter-row staff-order-filter">
      <label><span id="staff-order-status-label">{state}</span><select aria-labelledby="staff-order-status-label" value={status} onChange={event => setStatus(event.target.value as typeof status)}>
        <option value="">{text(locale, 'همهٔ وضعیت‌ها', 'All statuses')}</option>
        {orderStates.map(value => <option key={value} value={value}>{orderStateText(locale, value)}</option>)}
      </select></label>
    </div>
    {history.isPending && <p role="status">{text(locale, 'در حال دریافت سفارش‌ها…', 'Loading orders…')}</p>}
    {history.isError && <StaffOrderError locale={locale} error={history.error} reload={() => void history.refetch()}/>}
    {history.isSuccess && !orders.size && <p className="admin-panel">{text(locale, 'سفارشی در این وضعیت پیدا نشد.', 'No orders match this filter.')}</p>}
    {!!orders.size && <div className="admin-table-wrap">
      <table className="admin-table staff-order-table" aria-label={text(locale, 'فهرست سفارش‌ها', 'Order list')}>
        <thead><tr><th scope="col">{text(locale, 'شناسهٔ سفارش', 'Order reference')}</th><th scope="col">{placed}</th><th scope="col">{market}</th><th scope="col">{total}</th><th scope="col">{state}</th><th scope="col"><span className="sr-only">{text(locale, 'جزئیات', 'Details')}</span></th></tr></thead>
        <tbody>{[...orders.values()].map(order => <tr key={order.id}>
          <td><bdi dir="ltr" className="order-reference">{order.id}</bdi></td>
          <td data-label={placed}><time dateTime={order.created_at}>{checkoutTime(order.created_at, locale)}</time></td>
          <td data-label={market}>{order.market === 'ir' ? text(locale, 'ایران', 'Iran') : text(locale, 'بین‌المللی', 'International')}</td>
          <td data-label={total}><bdi>{formatCommerceMoney(order.total_minor, order.currency, locale)}</bdi></td>
          <td data-label={state}><OrderStateLabel locale={locale} status={order.status}/></td>
          <td><Link className="text-link order-open" href={`/${locale}/admin/orders/${order.id}`}>{text(locale, 'مشاهدهٔ سفارش', 'View order')}</Link></td>
        </tr>)}</tbody>
      </table>
    </div>}
    {!denied && history.hasNextPage && <div className="staff-order-pagination"><button className="button secondary" disabled={history.isFetching} onClick={() => void history.fetchNextPage()}>{history.isFetchingNextPage ? text(locale, 'در حال دریافت…', 'Loading…') : text(locale, 'نمایش سفارش‌های بیشتر', 'Load more')}</button></div>}
  </>;
}
