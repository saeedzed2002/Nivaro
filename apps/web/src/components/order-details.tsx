'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { readCustomerOrderDetails, type OrderDetails } from '@/lib/checkout-client';
import { checkoutTime } from '@/lib/checkout-copy';
import { formatCommerceMoney, text, type Locale } from '@/lib/content';
import { OrderLoadError, OrderStateLabel } from './order-history';

function PurchasedItems({ items, currency, locale }: { items: OrderDetails['standalone']; currency: OrderDetails['currency']; locale: Locale }) {
  const number = new Intl.NumberFormat(locale);
  return <ul className="purchased-items">{items.map(item => <li key={item.source_line_id}>
    <div><strong><bdi>{item.name}</bdi></strong><small className="muted"><bdi dir="ltr">{item.sku}</bdi></small></div>
    <div className="order-item-price"><bdi>{formatCommerceMoney(item.unit_price_minor, currency, locale)}</bdi>
      <small>{text(locale, 'تعداد ', 'Qty ')}<bdi>{number.format(item.quantity)}</bdi></small></div>
  </li>)}</ul>;
}

export function OrderPurchasedItems({ order, locale }: { order: Pick<OrderDetails, 'groups' | 'standalone' | 'currency'>; locale: Locale }) {
  return <>
    {order.groups.map(group => <div className="purchased-group" key={group.id}>
      <h3><bdi>{group.name}</bdi></h3><small className="muted">{group.mode === 'parts_only' ? text(locale, 'فقط قطعات', 'Parts only') : text(locale, 'پیکربندی کامل', 'Complete configuration')}</small>
      <PurchasedItems items={group.items} currency={order.currency} locale={locale}/>
    </div>)}
    {order.standalone.length > 0 && <PurchasedItems items={order.standalone} currency={order.currency} locale={locale}/>}
  </>;
}

export function OrderDeliveryAddress({ address, locale }: { address: OrderDetails['address']; locale: Locale }) {
  const country = new Intl.DisplayNames([locale], { type: 'region' }).of(address.country);
  return <address>
    <strong><bdi>{address.recipient}</bdi></strong>
    <span><bdi>{address.street}</bdi></span>
    <span><bdi>{address.city}</bdi> · {country}</span>
    <span><bdi>{address.postal_code}</bdi></span>
  </address>;
}

export function CustomerOrderDetails({ locale, orderId, customerId }: { locale: Locale; orderId: string; customerId: string }) {
  const query = useQuery({
    queryKey: ['account', 'orders', customerId, 'detail', orderId],
    queryFn: ({ signal }) => readCustomerOrderDetails(orderId, signal),
    retry: false, gcTime: 0,
  });
  return <>
    <Link className="text-link order-open" href={`/${locale}/account/orders`}>{text(locale, 'بازگشت به سفارش‌ها', 'Back to orders')}</Link>
    {query.isPending ? <p role="status">{text(locale, 'در حال دریافت جزئیات…', 'Loading order details…')}</p>
      : query.isError ? <OrderLoadError locale={locale} error={query.error} signIn={`/${locale}/login?next=order&order=${orderId}`} retry={() => void query.refetch()}/>
      : <OrderSnapshot order={query.data} locale={locale}/>}
  </>;
}

function OrderSnapshot({ order, locale }: { order: OrderDetails; locale: Locale }) {
  const { address, totals } = order;
  const amounts: [string, string, number][] = [
    ['جمع اقلام', 'Subtotal', totals.subtotal_minor], ['تخفیف', 'Discount', totals.discount_minor],
    ['ارسال', 'Shipping', totals.shipping_minor],
    totals.tax_included ? ['مالیات لحاظ‌شده', 'Included tax', totals.tax_minor] : ['مالیات', 'Tax', totals.tax_minor],
    ['مبلغ نهایی', 'Total', totals.total_minor],
  ];
  return <>
    <dl className="identity-panel order-snapshot-header">
      <div><dt>{text(locale, 'شناسهٔ سفارش', 'Order reference')}</dt><dd><bdi dir="ltr" className="order-reference">{order.id}</bdi></dd></div>
      <div><dt>{text(locale, 'تاریخ ثبت', 'Placed')}</dt><dd><time dateTime={order.created_at}>{checkoutTime(order.created_at, locale)}</time></dd></div>
      <div><dt>{text(locale, 'وضعیت', 'Status')}</dt><dd><OrderStateLabel locale={locale} status={order.status}/></dd></div>
    </dl>
    <div className="order-detail-grid">
      <section className="identity-panel order-detail-card" aria-labelledby="purchased-heading">
        <h2 id="purchased-heading">{text(locale, 'اقلام خریداری‌شده', 'Purchased items')}</h2>
        <OrderPurchasedItems order={order} locale={locale}/>
        <dl className="checkout-totals order-price-summary">{amounts.map(([fa, en, amount]) => <div key={en} className={en === 'Total' ? 'order-total' : undefined}>
          <dt>{text(locale, fa, en)}</dt><dd><bdi>{en === 'Discount' && amount > 0 && '−'}{formatCommerceMoney(amount, order.currency, locale)}</bdi></dd>
        </div>)}</dl>
      </section>
      <div className="order-detail-side">
        <section className="identity-panel order-detail-card">
          <h2>{text(locale, 'نشانی ارسال', 'Delivery address')}</h2>
          <OrderDeliveryAddress address={address} locale={locale}/>
          {order.tracking_reference && <p className="order-tracking">{text(locale, 'شناسهٔ رهگیری ', 'Tracking reference ')}<bdi dir="ltr">{order.tracking_reference}</bdi></p>}
        </section>
        <section className="identity-panel order-detail-card" aria-labelledby="order-timeline-heading">
          <h2 id="order-timeline-heading">{text(locale, 'تاریخچهٔ وضعیت', 'Order timeline')}</h2>
          <ol className="order-timeline" aria-labelledby="order-timeline-heading">{order.timeline.map(change => <li key={change.version}>
            <OrderStateLabel locale={locale} status={change.status}/>
            <time dateTime={change.occurred_at}>{checkoutTime(change.occurred_at, locale)}</time>
          </li>)}</ol>
        </section>
      </div>
    </div>
  </>;
}
