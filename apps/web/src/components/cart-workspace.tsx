'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Calculator, Minus, Package, Plus, ShoppingBag, Trash2 } from 'lucide-react';
import Image from 'next/image';
import Link from 'next/link';
import { useRef } from 'react';
import { CartError, cartErrorCopy, changeCartLine, deleteCartGroup, mergeGuestCart, readMergeSource, startGuest, type Cart, type CartLine } from '@/lib/cart-client';
import { formatCommerceMoney, text, type Locale } from '@/lib/content';
import { cartKey, useCart } from './cart-query';
import { usePreferences } from './preferences';

const statusLabels: Record<CartLine['status'] & string, [string, string]> = {
  available: ['موجود', 'Available'], removed: ['کالا دیگر در کاتالوگ نیست', 'Removed from catalog'],
  unpriced: ['قیمت نامشخص', 'Price unavailable'], reference_only: ['قیمت مرجع', 'Reference price'],
  unavailable: ['فعلاً قابل خرید نیست', 'Unavailable for sale'], stock_unknown: ['موجودی تأیید نشده', 'Stock unverified'],
  insufficient_stock: ['موجودی کافی نیست', 'Insufficient stock'], catalog_unavailable: ['کاتالوگ در دسترس نیست', 'Catalog unavailable'],
};

type Action =
  | { kind: 'line'; cart: Cart; line: CartLine; quantity: number | null }
  | { kind: 'group'; cart: Cart; group: Cart['groups'][number] }
  | { kind: 'merge'; cart: Cart; source: NonNullable<Awaited<ReturnType<typeof readMergeSource>>>; key: string }
  | { kind: 'restart' };

export function CartWorkspace({ locale }: { locale: Locale }) {
  const { market } = usePreferences();
  const queryClient = useQueryClient();
  const query = useCart(market);
  const cart = query.data;
  const merge = useQuery({ queryKey: [...cartKey(market), 'merge', cart?.id], enabled: cart?.owner_scope === 'customer',
    queryFn: ({ signal }) => readMergeSource(market, signal) });
  const mergeAttempt = useRef<{ fingerprint: string; key: string } | null>(null);
  const mutation = useMutation({
    mutationFn: async (action: Action) => {
      if (action.kind === 'line') return changeCartLine(action.cart, action.line, action.quantity);
      if (action.kind === 'group') return deleteCartGroup(action.cart, action.group);
      if (action.kind === 'merge') return mergeGuestCart(action.cart, action.source, action.key);
      return startGuest(true);
    },
    onMutate: async (action) => {
      if (action.kind !== 'line' || action.quantity === null) return;
      const key = cartKey(action.cart.market);
      await queryClient.cancelQueries({ queryKey: key, exact: true });
      const previous = queryClient.getQueryData<Cart>(key);
      if (!previous || previous.id !== action.cart.id || previous.version !== action.cart.version) return;
      const optimistic = queryClient.setQueryData<Cart>(key, {
        ...previous, estimated_total_minor: null,
        lines: previous.lines.map(line => line.id === action.line.id ? { ...line, quantity: action.quantity! } : line),
      });
      return { key, previous, optimistic };
    },
    onError: (_, __, change) => {
      if (change && queryClient.getQueryData(change.key) === change.optimistic) {
        queryClient.setQueryData(change.key, change.previous);
      }
    },
    onSettled: (_, __, action) => queryClient.invalidateQueries({ queryKey: cartKey('cart' in action ? action.cart.market : market) }),
  });
  const busy = mutation.isPending;
  const displayError = mutation.error ?? query.error;
  const expired = query.error instanceof CartError && query.error.code === 'guest.expired';

  if (query.isPending) return <p role="status">{text(locale, 'در حال دریافت سبد…', 'Loading your cart…')}</p>;
  if (query.isError || !cart) return <div className="cart-notice" role="alert">
    <p>{cartErrorCopy(displayError ?? new Error(), locale)}</p>
    <button type="button" className="button secondary" disabled={busy} onClick={() => expired ? mutation.mutate({ kind: 'restart' }) : void query.refetch()}>
      {expired ? text(locale, 'شروع سبد تازه', 'Start a new cart') : text(locale, 'تلاش دوباره', 'Try again')}
    </button>
  </div>;

  const count = new Intl.NumberFormat(locale).format(cart.lines.reduce((sum, line) => sum + line.quantity, 0));
  const lineView = (line: CartLine) => {
    const name = line.summary?.name ?? line.slot_key ?? text(locale, 'کالای بدون اطلاعات', 'Item details unavailable');
    const label = statusLabels[line.status ?? 'catalog_unavailable'];
    const offer = line.summary?.offer;
    const image = line.summary?.image;
    return <li className="cart-line" key={line.id}>
      <span className="cart-image">{image?.startsWith('/') && !image.startsWith('//') ? <Image src={image} width={64} height={64} alt="" /> : <Package aria-hidden="true" />}</span>
      <div className="cart-line-description"><strong><bdi>{name}</bdi></strong>
        <span>{text(locale, ...label)}{line.price_changed ? ` · ${text(locale, 'قیمت تغییر کرده', 'Price changed')}` : ''}</span>
        {offer && <bdi>{formatCommerceMoney(offer.amount_minor, cart.currency, locale)}</bdi>}
      </div>
      <div className="cart-actions">
        <div className="cart-stepper" aria-label={text(locale, 'تعداد', 'Quantity')}>
          <button type="button" aria-label={`${text(locale, 'کاهش تعداد', 'Decrease quantity')}: ${name}`} disabled={busy || line.quantity <= 1} onClick={() => mutation.mutate({ kind: 'line', cart, line, quantity: line.quantity - 1 })}><Minus size={15} /></button>
          <bdi>{new Intl.NumberFormat(locale).format(line.quantity)}</bdi>
          <button type="button" aria-label={`${text(locale, 'افزایش تعداد', 'Increase quantity')}: ${name}`} disabled={busy || line.status !== 'available'} onClick={() => mutation.mutate({ kind: 'line', cart, line, quantity: line.quantity + 1 })}><Plus size={15} /></button>
        </div>
        <button type="button" className="cart-icon" disabled={busy} aria-label={`${text(locale, 'حذف', 'Remove')}: ${name}`} onClick={() => mutation.mutate({ kind: 'line', cart, line, quantity: null })}><Trash2 size={17} /></button>
      </div>
    </li>;
  };

  return <>
    <p className="cart-count">{text(locale, `${count} کالا در سبد`, `${count} items in your cart`)}</p>
    {displayError && <p className="cart-notice" role="alert">{cartErrorCopy(displayError, locale)}</p>}
    {cart.paid_cleanup_needs_review && <p className="cart-notice" role="status">{text(locale, 'بعضی ردیف‌ها پس از ثبت سفارش تغییر کرده‌اند. سبد را پیش از خرید بعدی بررسی کن.', 'Some cart items changed after checkout. Review your cart before the next purchase.')}</p>}
    {merge.data && <div className="cart-notice"><p>{text(locale, 'در سبد مهمان همین بازار اقلامی داری.', 'Your guest cart has items in this market.')}</p>
      <button type="button" className="button secondary" disabled={busy} onClick={() => {
        const source = merge.data;
        if (!source) return;
        const fingerprint = `${cart.id}:${cart.version}:${source.cart_id}:${source.version}`;
        if (mergeAttempt.current?.fingerprint !== fingerprint) mergeAttempt.current = { fingerprint, key: crypto.randomUUID() };
        mutation.mutate({ kind: 'merge', cart, source, key: mergeAttempt.current.key });
      }}>{text(locale, 'ادغام با سبد حساب', 'Merge guest cart')}</button>
    </div>}
    {!cart.lines.length && !cart.groups.length ? <section className="cart-empty">
      <ShoppingBag size={38} aria-hidden="true" /><h2>{text(locale, 'سبد خرید خالی است', 'Your cart is empty')}</h2>
      <Link className="button primary" href={`/${locale}/products`}>{text(locale, 'دیدن محصولات', 'Browse components')}</Link>
    </section> : <div className="cart-layout" aria-busy={busy}>
      <section className="cart-items" aria-label={text(locale, 'اقلام سبد', 'Cart items')}>
        {cart.catalog_status === 'unavailable' && <p className="cart-notice"><AlertTriangle size={18} /> {text(locale, 'قیمت‌ها موقتاً در دسترس نیستند.', 'Prices are temporarily unavailable.')}</p>}
        {cart.groups.map(group => <section key={group.id} className="cart-group">
          <header><div><h2>{group.name}</h2><p>{group.mode === 'parts_only' ? text(locale, 'فقط قطعات', 'Parts only') : text(locale, 'پیکربندی سیستم کامل', 'Complete configuration')}</p></div>
            <div className="cart-actions"><Link className="text-link" href={`/${locale}/build?group=${encodeURIComponent(group.id)}`}>{text(locale, 'ویرایش سیستم', 'Edit system')}</Link>
            <button type="button" className="cart-icon" disabled={busy} aria-label={`${text(locale, 'حذف سیستم', 'Remove system')}: ${group.name}`} onClick={() => mutation.mutate({ kind: 'group', cart, group })}><Trash2 size={17} /></button></div>
          </header>
          <ul>{cart.lines.filter(line => line.group_id === group.id).map(lineView)}</ul>
        </section>)}
        <ul className="cart-standalone">{cart.lines.filter(line => !line.group_id).map(lineView)}</ul>
      </section>
      <aside className="cart-summary">
        <h2><Calculator size={21} />{text(locale, 'خلاصهٔ سبد', 'Cart summary')}</h2>
        <dl><div><dt>{text(locale, 'جمع تخمینی', 'Estimated subtotal')}</dt><dd><bdi>{cart.estimated_total_minor != null ? formatCommerceMoney(cart.estimated_total_minor, cart.currency, locale) : '—'}</bdi></dd></div>
          <div><dt>{text(locale, 'ارسال و مالیات', 'Delivery and tax')}</dt><dd>{text(locale, 'در انتظار محاسبه', 'Pending')}</dd></div></dl>
        {cart.estimated_total_minor == null && <p className="cart-notice">{text(locale, 'قیمت یا موجودی بعضی اقلام نیاز به بررسی دارد.', 'Some items need a price or availability check.')}</p>}
        <p className="cart-stock"><Package size={18} />{text(locale, 'افزودن به سبد، موجودی را رزرو نمی‌کند.', 'Adding items to your cart does not reserve stock.')}</p>
        {cart.lines.length > 0 && <Link className="button primary" href={`/${locale}/checkout`}>{text(locale, 'ادامه به تسویه', 'Continue to checkout')}</Link>}
      </aside>
    </div>}
  </>;
}
