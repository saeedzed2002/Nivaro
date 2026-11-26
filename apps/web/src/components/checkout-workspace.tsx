'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import { Calculator, Clock, Info, Layers, List, LockKeyhole, MapPin, Tag } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { cartKey, useCart } from './cart-query';
import { usePreferences } from './preferences';
import { CartError, type Cart } from '@/lib/cart-client';
import { checkoutError, checkoutTime, loginRequired } from '@/lib/checkout-copy';
import { clearCheckoutAttempt, rememberCheckoutAttempt, useCheckoutAttempt } from '@/lib/checkout-attempt';
import { confirmCheckout, previewCheckout, type CheckoutIntent, type CheckoutPreview } from '@/lib/checkout-client';
import { formatCommerceMoney, text, type Locale } from '@/lib/content';
import { IdentityError, listAddresses, type Address } from '@/lib/identity-client';

export function CheckoutWorkspace({ locale }: { locale: Locale }) {
  const { market } = usePreferences();
  const cart = useCart(market);
  const addresses = useQuery({
    queryKey: [...cartKey(market), 'checkout-addresses', cart.data?.id],
    queryFn: listAddresses,
    enabled: cart.data?.owner_scope === 'customer' && cart.data.lines.length > 0,
  });
  if (cart.isPending) return <p role="status">{text(locale, 'در حال دریافت سبد…', 'Loading your cart…')}</p>;
  const error = cart.error ?? addresses.error;
  if (cart.data?.owner_scope === 'guest' || loginRequired(error) || (error instanceof CartError && error.status === 401)) return <div className="checkout-panel checkout-state">
    <p>{text(locale, 'برای تسویه وارد حساب شو. اقلام مهمان را می‌توانی در سبد حسابت ادغام کنی.', 'Sign in to check out. You can merge guest items into your account cart.')}</p>
    <Link className="button primary" href={`/${locale}/login?next=checkout`}>{text(locale, 'ورود به حساب', 'Sign in')}</Link>
  </div>;
  if (error) return <div className="checkout-panel checkout-state" role="alert">
    <p>{checkoutError(locale, error)}</p>
    <button className="button secondary" onClick={() => void (cart.error ? cart.refetch() : addresses.refetch())}>{text(locale, 'تلاش دوباره', 'Try again')}</button>
  </div>;
  if (!cart.data?.lines.length) return <div className="checkout-panel checkout-state">
    <p>{text(locale, 'سبد حساب خالی است.', 'Your account cart is empty.')}</p>
    <Link className="button primary" href={`/${locale}/cart`}>{text(locale, 'بازگشت به سبد خرید', 'Back to cart')}</Link>
  </div>;
  if (addresses.isPending) return <p role="status">{text(locale, 'در حال دریافت آدرس‌ها…', 'Loading addresses…')}</p>;
  return <CheckoutForm key={cart.data.id} locale={locale} cart={cart.data} addresses={addresses.data ?? []} reload={() => Promise.all([cart.refetch(), addresses.refetch()])} />;
}

function CheckoutForm({ locale, cart, addresses, reload }: { locale: Locale; cart: Cart; addresses: Address[]; reload: () => Promise<unknown> }) {
  const router = useRouter();
  const [selected, setSelected] = useState('');
  const [coupon, setCoupon] = useState('');
  const [review, setReview] = useState<{ intent: string; receipt: CheckoutPreview } | null>(null);
  const [expiredId, setExpiredId] = useState('');
  const [busy, setBusy] = useState(false);
  const previewKey = useRef<{ intent: string; key: string } | null>(null);
  const inFlight = useRef(false);
  const pending = useCheckoutAttempt();
  const address = addresses.find(item => item.id === selected) ?? addresses[0];
  const intent: CheckoutIntent | null = address ? {
    market: cart.market, currency: cart.currency, cart_version: cart.version,
    address_id: address.id, address_version: address.version, coupon_code: coupon.trim().toUpperCase() || null,
  } : null;
  const signature = JSON.stringify(intent);
  const receipt = review?.intent === signature ? review.receipt : null;
  const expired = receipt !== null && expiredId === receipt.operation_id;
  useEffect(() => {
    if (!receipt) return;
    const id = window.setTimeout(() => setExpiredId(receipt.operation_id), Math.max(0, Date.parse(receipt.expires_at) - Date.now()));
    return () => window.clearTimeout(id);
  }, [receipt]);

  const preview = useMutation({ mutationFn: ({ body, key }: { body: CheckoutIntent; key: string }) => previewCheckout(body, key) });
  const confirmation = useMutation({ mutationFn: ({ operation_id, confirmation }: CheckoutPreview) => confirmCheckout(operation_id, confirmation) });
  const error = confirmation.error ?? preview.error;

  async function reviewTotal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!intent || inFlight.current || pending?.cartId === cart.id) return;
    inFlight.current = true;
    setBusy(true);
    if (previewKey.current?.intent !== signature || expired) previewKey.current = { intent: signature, key: crypto.randomUUID() };
    confirmation.reset();
    setReview(null);
    try {
      const receipt = await preview.mutateAsync({ body: intent, key: previewKey.current.key });
      setReview({ intent: signature, receipt });
    } catch (err) {
      if (err instanceof IdentityError && ['checkout.address_changed', 'checkout.cart_changed'].includes(err.code)) await reload();
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function submitOrder() {
    if (!receipt || expired || inFlight.current || pending?.cartId === cart.id) return;
    inFlight.current = true;
    setBusy(true);
    const id = receipt.operation_id;
    const destination = `/${locale}/checkout/result?order=${id}`;
    rememberCheckoutAttempt({ cartId: cart.id, orderId: id, confirmation: receipt.confirmation });
    try {
      await confirmation.mutateAsync(receipt);
      clearCheckoutAttempt(id);
      router.replace(destination);
    } catch (err) {
      if (err instanceof IdentityError && err.status >= 400 && err.status < 500) {
        clearCheckoutAttempt(id);
        setReview(null);
        previewKey.current = null;
        if (['checkout.address_changed', 'checkout.cart_changed'].includes(err.code)) await reload();
      } else router.replace(destination);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  if (pending?.cartId === cart.id && !busy) return <div className="checkout-panel checkout-state">
    <p>{text(locale, 'وضعیت آخرین ارسال سفارش را بررسی کن.', 'Check the status of your last order submission.')}</p>
    <Link className="button primary" href={`/${locale}/checkout/result?order=${pending.orderId}`}>{text(locale, 'مشاهدهٔ وضعیت سفارش', 'Check order status')}</Link>
  </div>;

  const addressLink = `/${locale}/account/addresses?from=checkout`;
  return <form className="checkout-layout" onSubmit={reviewTotal} aria-busy={busy}>
    <div className="checkout-main">
      <section className="checkout-panel" aria-labelledby="checkout-delivery">
        <header className="checkout-panel-heading"><h2 id="checkout-delivery"><MapPin size={19} aria-hidden="true" />{text(locale, 'آدرس ارسال', 'Delivery address')}</h2>
          <Link className="text-link" href={addressLink}>{text(locale, 'مدیریت آدرس‌ها', 'Manage addresses')}</Link></header>
        {address ? <fieldset className="checkout-addresses">
          <legend className="sr-only">{text(locale, 'انتخاب آدرس ارسال', 'Select delivery address')}</legend>
          {addresses.map(item => <label className="checkout-address" key={item.id}>
            <input type="radio" name="address" value={item.id} checked={item.id === address.id} disabled={busy} onChange={() => { setSelected(item.id); setReview(null); preview.reset(); confirmation.reset(); }} />
            <strong><bdi>{item.label}</bdi></strong>
            <span><bdi>{item.recipient}</bdi><small><bdi>{item.street}{locale === 'fa' ? '، ' : ', '}{item.city}</bdi> · <bdi>{item.country}</bdi> · <bdi>{item.postal_code}</bdi></small></span>
          </label>)}
        </fieldset> : <p className="checkout-muted">{text(locale, 'برای ادامه یک آدرس ارسال اضافه کن.', 'Add a delivery address to continue.')}</p>}
      </section>
      <section className="checkout-panel" aria-labelledby="checkout-coupon">
        <header className="checkout-panel-heading"><h2 id="checkout-coupon"><Tag size={18} aria-hidden="true" /><label htmlFor="checkout-code">{text(locale, 'کد تخفیف', 'Promo code')}</label></h2></header>
        <div className="checkout-coupon">
          <input id="checkout-code" value={coupon} dir="ltr" maxLength={40} pattern={String.raw`[A-Za-z0-9][A-Za-z0-9_\-]{0,39}`} autoComplete="off" disabled={busy} onChange={event => { setCoupon(event.target.value); setReview(null); preview.reset(); confirmation.reset(); }} />
          <button className="button secondary" type="submit" disabled={!intent || !intent.coupon_code || busy}>{text(locale, 'اعمال کد', 'Apply code')}</button>
        </div>
      </section>
      <CheckoutItems locale={locale} cart={cart} receipt={receipt} />
    </div>
    <aside className="checkout-panel checkout-summary" aria-labelledby="checkout-summary">
      <header className="checkout-panel-heading"><h2 id="checkout-summary"><Calculator size={19} aria-hidden="true" />{text(locale, 'خلاصه سفارش', 'Order summary')}</h2></header>
      <CheckoutTotals locale={locale} receipt={receipt} />
      {receipt && <p className="checkout-muted checkout-hint"><Clock size={17} aria-hidden="true" />{expired ? text(locale, 'مهلت تأیید قیمت تمام شد.', 'The quote expired.') : <span>{text(locale, 'مهلت تأیید قیمت', 'Quote valid until')} <time dateTime={receipt.expires_at}><bdi>{checkoutTime(receipt.expires_at, locale)}</bdi></time></span>}</p>}
      {error && <div className="checkout-notice" role="alert"><p>{checkoutError(locale, error)}</p>{loginRequired(error) && <Link className="text-link" href={`/${locale}/login?next=checkout`}>{text(locale, 'ورود به حساب', 'Sign in')}</Link>}</div>}
      {receipt && !expired ? <button type="button" className="button primary" disabled={busy} onClick={() => void submitOrder()}><LockKeyhole size={17} aria-hidden="true" />{confirmation.isPending ? text(locale, 'در حال ثبت سفارش…', 'Submitting your order…') : text(locale, 'تأیید و ثبت سفارش', 'Confirm order')}</button>
        : <button type="submit" className="button primary" disabled={!intent || busy}>{preview.isPending ? text(locale, 'در حال محاسبه…', 'Checking the total…') : text(locale, 'محاسبهٔ مبلغ نهایی', 'Review final total')}</button>}
      <p className="checkout-notice checkout-hint"><Info size={18} aria-hidden="true" />{text(locale, 'رزرو موجودی هنگام ثبت سفارش انجام می‌شود. پرداخت مرحلهٔ جداگانه‌ای است.', 'Stock is reserved when the order is submitted. Payment is a separate step.')}</p>
    </aside>
  </form>;
}

function CheckoutTotals({ locale, receipt }: { locale: Locale; receipt: CheckoutPreview | null }) {
  const totals = receipt?.totals;
  const rows = [
    [text(locale, 'جمع جزء', 'Subtotal'), totals?.subtotal_minor],
    [text(locale, 'تخفیف', 'Discount'), totals?.discount_minor],
    [text(locale, 'هزینهٔ ارسال', 'Shipping'), totals?.shipping_minor],
    [totals?.tax_included ? text(locale, 'مالیات منظورشده در قیمت', 'Tax included in price') : text(locale, 'مالیات', 'Tax'), totals?.tax_minor],
    [text(locale, 'مبلغ نهایی', 'Final total'), totals?.total_minor],
  ] as const;
  return <dl className="checkout-totals" aria-live="polite">{rows.map(([label, value], index) => <div key={label} className={index === 4 ? 'checkout-grand-total' : undefined}>
    <dt>{label}</dt><dd><bdi>{totals && value !== undefined ? `${index === 1 && value > 0 ? '−' : ''}${formatCommerceMoney(value, totals.currency, locale)}` : text(locale, 'در انتظار محاسبه', 'Pending')}</bdi></dd>
  </div>)}</dl>;
}

function CheckoutItems({ locale, cart, receipt }: { locale: Locale; cart: Cart; receipt: CheckoutPreview | null }) {
  const groups = receipt?.groups ?? cart.groups;
  const lines = receipt?.lines ?? cart.lines.map(line => ({
    id: line.id, group_id: line.group_id, quantity: line.quantity, unit_price_minor: null,
    name: line.summary?.name ?? text(locale, 'اطلاعات کالا در دسترس نیست', 'Item details unavailable'),
  }));
  const quantities = new Intl.NumberFormat(locale);
  const byGroup = new Map<string | null, (typeof lines)[number][]>();
  for (const line of lines) {
    const id = line.group_id ?? null;
    const existing = byGroup.get(id);
    if (existing) existing.push(line);
    else byGroup.set(id, [line]);
  }
  const rows = (group: string | null) => (byGroup.get(group) ?? []).map(line => <li key={line.id}>
    <strong><bdi>{line.name}</bdi></strong><span>{text(locale, 'تعداد', 'Qty')} <bdi>{quantities.format(line.quantity)}</bdi></span>
    {line.unit_price_minor !== null && <bdi>{formatCommerceMoney(line.unit_price_minor * line.quantity, cart.currency, locale)}</bdi>}
  </li>);
  return <section className="checkout-panel checkout-items" aria-labelledby="checkout-items">
    <header className="checkout-panel-heading"><h2 id="checkout-items"><List size={20} aria-hidden="true" />{text(locale, 'اقلام سفارش', 'Order items')}</h2></header>
    {groups.map(group => <div className="checkout-group" key={group.id}>
      <h3><Layers size={18} aria-hidden="true" /><bdi>{group.name}</bdi></h3>
      <p>{group.mode === 'parts_only' ? text(locale, 'فقط قطعات', 'Parts only') : text(locale, 'پیکربندی سیستم کامل', 'Complete configuration')}</p>
      {'status' in group && group.mode === 'parts_only' && group.status !== 'compatible' && <p className="checkout-notice">{text(locale, 'سازگاری کامل این قطعات تأیید نشده است.', 'Full compatibility for these parts has not been confirmed.')}</p>}
      <ul className="checkout-lines">{rows(group.id)}</ul>
    </div>)}
    {byGroup.has(null) && <ul className="checkout-lines">{rows(null)}</ul>}
  </section>;
}
