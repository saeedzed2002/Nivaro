'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Clock, Package, RefreshCw, ShoppingBag } from 'lucide-react';
import Link from 'next/link';
import { useEffect } from 'react';
import { clearCheckoutAttempt, useCheckoutAttempt } from '@/lib/checkout-attempt';
import { confirmCheckout, orderStatus, startSimulatedPayment, type OrderStatus } from '@/lib/checkout-client';
import { checkoutError, checkoutMessage, checkoutTime, loginRequired } from '@/lib/checkout-copy';
import { formatCommerceMoney, text, type Locale } from '@/lib/content';
import { IdentityError } from '@/lib/identity-client';

const headings: Record<OrderStatus['status'], [string, string]> = {
  pending_reservation: ['سفارش در حال رزرو موجودی', 'Reserving order items'],
  awaiting_payment: ['سفارش در انتظار پرداخت', 'Order awaiting payment'],
  expired: ['مهلت رزرو سفارش تمام شد', 'Order reservation expired'],
  cancelled: ['سفارش لغو شد', 'Order cancelled'],
  payment_processing: ['پرداخت تأیید شد؛ موجودی در حال نهایی‌سازی است', 'Payment verified, confirming stock'],
  payment_review: ['پرداخت نیازمند بررسی است', 'Payment needs review'],
  paid: ['پرداخت و موجودی سفارش تأیید شد', 'Payment and stock confirmed'],
  refund_pending: ['بازپرداخت در حال انجام است', 'Refund in progress'],
  refunded: ['بازپرداخت تأیید شد', 'Refund confirmed'],
  processing: ['سفارش در حال آماده‌سازی است', 'Preparing your order'],
  shipped: ['سفارش ارسال شد', 'Order shipped'],
  delivered: ['سفارش تحویل شد', 'Order delivered'],
};

export function CheckoutResult({ locale, id }: { locale: Locale; id: string | null }) {
  const client = useQueryClient();
  const key = ['cart', 'orders', id] as const;
  const attempt = useCheckoutAttempt();
  const order = useQuery({
    queryKey: key, enabled: id !== null,
    queryFn: ({ signal }) => orderStatus(id!, signal),
    refetchInterval: ({ state }) => {
      const status = state.data?.status;
      if (status === 'pending_reservation' || status === 'payment_processing' || status === 'refund_pending') return 3_000;
      if (status === 'awaiting_payment' && (state.data?.payment_state === 'queued' || state.data?.payment_state === 'submitted')) return 3_000;
      return status === 'awaiting_payment' || status === 'expired' ? 15_000 : false;
    },
  });
  const orderId = order.data?.id;
  useEffect(() => { if (orderId) clearCheckoutAttempt(orderId); }, [orderId]);
  const retry = useMutation({
    mutationFn: (receipt: { orderId: string; confirmation: string }) => confirmCheckout(receipt.orderId, receipt.confirmation),
    onSuccess: data => { client.setQueryData(key, data); },
    onError: (error, receipt) => {
      if (error instanceof IdentityError && error.status === 409) clearCheckoutAttempt(receipt.orderId);
    },
  });
  const payment = useMutation({
    mutationFn: (current: { id: string; version: number }) => startSimulatedPayment(current.id, current.version),
    onSuccess: current => { client.setQueryData<OrderStatus>(key, prior => prior && prior.version > current.version ? prior : current); },
  });
  const data = order.data;
  const error = payment.error ?? retry.error ?? order.error;
  const pendingAttempt = id !== null && attempt?.orderId === id ? attempt : null;
  const missing = order.error instanceof IdentityError && order.error.status === 404;
  const deadline = data?.status === 'awaiting_payment' ? data.reservation_expires_at : null;
  const title = data ? text(locale, ...headings[data.status]) : text(locale, 'وضعیت سفارش', 'Order status');
  const awaiting = deadline && checkoutTime(deadline, locale);
  const payable = data?.status === 'awaiting_payment' && !data.payment_state;
  const paymentInProgress = data?.status === 'awaiting_payment' && (data.payment_state === 'queued' || data.payment_state === 'submitted');

  return <main id="main-content" className="container checkout-result-page">
    <section className="checkout-panel checkout-result-panel" aria-labelledby="checkout-result-heading" aria-busy={id !== null && (order.isFetching || retry.isPending || payment.isPending)}>
      <div className="checkout-result-icon" aria-hidden="true"><Package /><Clock /></div>
      <h1 id="checkout-result-heading">{title}</h1>
      {!id && <p className="checkout-muted">{text(locale, 'شناسهٔ معتبر سفارش در نشانی صفحه نیست.', 'The page URL is missing a valid order reference.')}</p>}
      {id && order.isPending && <p className="checkout-muted" role="status">{text(locale, 'در حال دریافت وضعیت…', 'Checking order status…')}</p>}
      {awaiting && <p className="checkout-muted">{text(locale, 'موجودی تا زمان درج‌شده رزرو است.', 'Stock is reserved until the deadline shown below.')}</p>}
      {paymentInProgress && <p className="checkout-muted" role="status">{text(locale, 'پرداخت آزمایشی در حال بررسی است.', 'The simulated payment is being verified.')}</p>}
      {data?.status === 'awaiting_payment' && data.payment_state === 'blocked' && <p className="checkout-notice">{checkoutMessage(locale, 'payment.not_payable')}</p>}
      {data?.status === 'pending_reservation' && <p className="checkout-muted" role="status">{text(locale, 'رزرو موجودی در حال بررسی است. وضعیت خودکار به‌روز می‌شود.', 'Stock reservation is in progress. This status refreshes automatically.')}</p>}
      {data?.status === 'cancelled' && data.failure_code && <p className="checkout-notice">{checkoutMessage(locale, data.failure_code)}</p>}
      {data && <dl className="checkout-totals checkout-result-details">
        <div><dt>{text(locale, 'شناسهٔ سفارش', 'Order reference')}</dt><dd><bdi dir="ltr">{data.id}</bdi></dd></div>
        <div><dt>{text(locale, 'مبلغ سفارش', 'Total')}</dt><dd><bdi>{formatCommerceMoney(data.totals.total_minor, data.totals.currency, locale)}</bdi></dd></div>
        {deadline && <div><dt>{text(locale, 'مهلت رزرو موجودی', 'Reservation deadline')}</dt><dd><time dateTime={deadline}><bdi>{awaiting}</bdi></time></dd></div>}
      </dl>}
      {error && <p className="checkout-notice" role="alert">{missing && pendingAttempt && !retry.error
        ? text(locale, 'نتیجهٔ ارسال هنوز در دسترس نیست. می‌توانی همان سفارش را دوباره ارسال کنی.', 'Submission hasn’t been confirmed. You can retry the same order.')
        : checkoutError(locale, error)}</p>}
      <div className="checkout-result-actions">
        {payable && <button className="button primary" disabled={payment.isPending} onClick={() => payment.mutate(data)}>{text(locale, 'پرداخت آزمایشی', 'Pay with simulator')}</button>}
        <Link className={`button ${payable ? 'secondary' : 'primary'}`} href={`/${locale}/cart`}><ShoppingBag size={19} aria-hidden="true" />{text(locale, 'بازگشت به سبد خرید', 'Back to cart')}</Link>
        {data && <Link className="button secondary" href={`/${locale}/account/orders/${data.id}`}>{text(locale, 'جزئیات سفارش', 'Order details')}</Link>}
        {id && loginRequired(error) ? <Link className="button secondary" href={`/${locale}/login?next=result&order=${id}`}>{text(locale, 'ورود به حساب', 'Sign in')}</Link>
          : id && <button className="button secondary" disabled={order.isFetching || retry.isPending} onClick={() => void order.refetch()}><RefreshCw size={17} aria-hidden="true" />{text(locale, 'به‌روزرسانی وضعیت', 'Refresh status')}</button>}
        {missing && pendingAttempt && !loginRequired(error) && <button className="button secondary" disabled={retry.isPending || order.isFetching} onClick={() => retry.mutate(pendingAttempt)}>{text(locale, 'تلاش دوباره برای ثبت سفارش', 'Retry order submission')}</button>}
      </div>
    </section>
  </main>;
}
