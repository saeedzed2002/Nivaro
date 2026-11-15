'use client';

import Link from 'next/link';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { changeOrderFulfillment, readOrderFulfillment, type FulfillmentCommand } from '@/lib/checkout-client';
import { checkoutTime } from '@/lib/checkout-copy';
import { formatCommerceMoney, text, type Locale } from '@/lib/content';
import { IdentityError } from '@/lib/identity-client';
import { useAdminSession } from './admin-shared';
import { OrderDeliveryAddress, OrderPurchasedItems } from './order-details';
import { OrderStateLabel } from './order-history';
import { StaffOrderError } from './staff-orders';

const actions: Record<FulfillmentCommand['action'], [string, string]> = {
  prepare: ['شروع آماده‌سازی', 'Start preparation'],
  ship: ['ثبت ارسال', 'Record shipment'],
  deliver: ['ثبت تحویل', 'Record delivery'],
};

export function StaffOrderDetails({ id, locale }: { id: string; locale: Locale }) {
  const session = useAdminSession();
  const client = useQueryClient();
  const queryKey = ['staff', session?.profile.id, 'fulfillment', id] as const;
  const query = useQuery({
    queryKey, queryFn: ({ signal }) => readOrderFulfillment(id, signal),
    retry: false, gcTime: 0, refetchOnWindowFocus: false,
  });
  const [tracking, setTracking] = useState('');
  const [validation, setValidation] = useState(false);
  const command = useMutation({
    mutationFn: (body: FulfillmentCommand) => changeOrderFulfillment(id, body),
    onMutate: async () => { await client.cancelQueries({ queryKey }); },
    onSuccess: view => {
      client.setQueryData(queryKey, (previous: typeof query.data) => previous && ({ ...previous, ...view }));
      void client.invalidateQueries({ queryKey: ['staff', session?.profile.id, 'orders'] });
      setTracking('');
    },
  });
  const order = query.data;
  const action = session?.permissions.includes('orders.fulfill') ? order?.allowed_actions[0] : undefined;
  const conflict = command.error instanceof IdentityError && command.error.status === 409;
  const denied = command.error instanceof IdentityError && [401, 403].includes(command.error.status);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!order || !action || command.isPending || conflict || denied) return;
    const reference = tracking.trim();
    if (action === 'ship' && !/^[A-Za-z0-9][A-Za-z0-9._ -]{0,79}$/.test(reference)) {
      setValidation(true);
      return;
    }
    const expected_version = order.version;
    command.mutate(action === 'ship' ? { action, expected_version, tracking_reference: reference } : { action, expected_version });
  }

  async function reload() {
    const result = await query.refetch();
    if (result.isSuccess) command.reset();
  }

  return <>
    <header className="admin-heading staff-order-heading"><div>
      <h1>{text(locale, 'جزئیات سفارش', 'Order details')}</h1>
      <Link className="text-link order-open" href={`/${locale}/admin/orders`}>{text(locale, 'بازگشت به سفارش‌ها', 'Back to orders')}</Link>
    </div></header>
    {query.isPending ? <p role="status">{text(locale, 'در حال دریافت سفارش…', 'Loading order…')}</p>
      : query.isError ? <StaffOrderError locale={locale} error={query.error} reload={() => void reload()}/>
      : <>
        <dl className="admin-panel order-snapshot-header staff-order-summary">
          <div><dt>{text(locale, 'شناسهٔ سفارش', 'Order reference')}</dt><dd><bdi dir="ltr" className="order-reference">{query.data.id}</bdi></dd></div>
          <div><dt>{text(locale, 'تاریخ ثبت', 'Placed')}</dt><dd><time dateTime={query.data.snapshot.created_at}>{checkoutTime(query.data.snapshot.created_at, locale)}</time></dd></div>
          <div><dt>{text(locale, 'وضعیت', 'Status')}</dt><dd><OrderStateLabel locale={locale} status={query.data.status}/></dd></div>
        </dl>
        <div className="order-detail-grid">
          <div className="order-detail-side">
            <section className="admin-panel order-detail-card">
              <h2>{text(locale, 'اقلام خریداری‌شده', 'Purchased items')}</h2>
              <OrderPurchasedItems order={query.data.snapshot} locale={locale}/>
              <dl className="checkout-totals order-price-summary"><div className="order-total">
                <dt>{text(locale, 'مبلغ ثبت‌شده', 'Original total')}</dt>
                <dd><bdi>{formatCommerceMoney(query.data.snapshot.total_minor, query.data.snapshot.currency, locale)}</bdi></dd>
              </div></dl>
            </section>
            <section className="admin-panel order-detail-card" aria-labelledby="staff-order-audit">
              <h2 id="staff-order-audit">{text(locale, 'تاریخچهٔ ثبت وضعیت', 'Order audit timeline')}</h2>
              <ol className="order-timeline staff-order-timeline" aria-labelledby="staff-order-audit">{query.data.timeline.map(change => <li key={change.version}>
                <OrderStateLabel locale={locale} status={change.status}/>
                <time dateTime={change.occurred_at}>{checkoutTime(change.occurred_at, locale)}</time>
                {change.staff_actor_id && <small>{text(locale, 'شناسهٔ کارمند ', 'Staff ID ')}<bdi dir="ltr">{change.staff_actor_id}</bdi></small>}
              </li>)}</ol>
            </section>
          </div>
          <div className="order-detail-side">
            <section className="admin-panel order-detail-card">
              <h2>{text(locale, 'نشانی ارسال', 'Delivery address')}</h2>
              <OrderDeliveryAddress address={query.data.snapshot.address} locale={locale}/>
            </section>
            <section className="admin-panel order-detail-card" aria-labelledby="staff-order-fulfillment">
              <h2 id="staff-order-fulfillment">{text(locale, 'عملیات ارسال و تحویل', 'Fulfillment')}</h2>
              <p className="staff-order-current">{text(locale, 'وضعیت فعلی', 'Current status')} <OrderStateLabel locale={locale} status={query.data.status}/></p>
              {query.data.tracking_reference && <p className="order-tracking">{text(locale, 'شناسهٔ رهگیری ', 'Tracking reference ')}<bdi dir="ltr">{query.data.tracking_reference}</bdi></p>}
              {command.isSuccess && <p role="status">{text(locale, 'وضعیت سفارش ثبت شد.', 'Order status saved.')}</p>}
              {command.isError && <StaffOrderError locale={locale} error={command.error} reload={() => void reload()}/>}
              {action && <form className="admin-form staff-fulfillment-form" onSubmit={submit}>
                {action === 'ship' && <label>{text(locale, 'شناسهٔ رهگیری', 'Tracking reference')}
                  <input dir="ltr" autoComplete="off" aria-invalid={validation} aria-describedby="tracking-help" required maxLength={80} disabled={command.isPending} value={tracking} onChange={event => { setTracking(event.target.value); setValidation(false); }}/>
                  <small id="tracking-help" role={validation ? 'alert' : undefined}>{text(locale, 'حروف لاتین، رقم، فاصله، نقطه، خط تیره و زیرخط. با حرف یا رقم شروع شود.', 'Use Latin letters, digits, spaces, periods, hyphens or underscores. Start with a letter or digit.')}</small>
                </label>}
                <button className="button primary" disabled={command.isPending || query.isFetching || conflict || denied}>{text(locale, ...actions[action])}</button>
              </form>}
            </section>
          </div>
        </div>
      </>}
  </>;
}
