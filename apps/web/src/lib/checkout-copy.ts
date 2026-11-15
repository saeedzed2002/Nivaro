import { text, type Locale } from './content';
import { IdentityError } from './identity-client';

const messages: Record<string, [string, string]> = {
  'checkout.cart_changed': ['سبد تغییر کرده است. مبلغ تازه را بررسی کن.', 'Your cart changed. Review the updated total.'],
  'checkout.address_changed': ['آدرس تغییر کرده است. آدرس و مبلغ تازه را بررسی کن.', 'The address changed. Review the current address and total.'],
  'checkout.confirmation_changed': ['شرایط سفارش تغییر کرده است. مبلغ تازه را بررسی کن.', 'The order terms changed. Review the updated total.'],
  'checkout.delivery_unavailable': ['برای این مقصد در بازار انتخاب‌شده نرخ ارسال تعریف نشده است.', 'Delivery is unavailable for this destination in the selected market.'],
  'checkout.quote_expired': ['مهلت تأیید قیمت تمام شد. مبلغ تازه را دریافت کن.', 'The quote expired. Request an updated total.'],
  'quote.expired': ['مهلت تأیید قیمت تمام شد. مبلغ تازه را دریافت کن.', 'The quote expired. Request an updated total.'],
  'quote.price_changed': ['قیمت تغییر کرده است. مبلغ تازه را بررسی کن.', 'The price changed. Review the updated total.'],
  'quote.eligibility_changed': ['یک یا چند کالا دیگر در این بازار قابل خرید نیست.', 'One or more items are no longer available for sale in this market.'],
  'inventory.insufficient_stock': ['موجودی برای این سفارش کافی نیست.', 'There is not enough stock for this order.'],
  'checkout.cart_empty': ['سبد خرید خالی است.', 'Your cart is empty.'],
  'build.not_compatible': ['پیکربندی سیستم برای خرید نیاز به اصلاح دارد. سبد را بررسی کن.', 'A system configuration needs changes. Review the cart.'],
  'build.invalid_selection': ['قطعات انتخاب‌شده را در سبد بررسی کن.', 'Review the selected parts in the cart.'],
  'build.validation_stale': ['مشخصات یا قواعد سازگاری تغییر کرده‌اند. سبد را بررسی کن.', 'Specifications or compatibility rules changed. Review the cart.'],
  'coupon.unavailable': ['این کد تخفیف برای سفارش قابل استفاده نیست.', 'This promo code cannot be used for this order.'],
  'coupon.quota_exhausted': ['سقف استفاده از این کد تخفیف پر شده است.', 'This promo code has reached its usage limit.'],
  'checkout.not_found': ['سفارش پیدا نشد.', 'Order not found.'],
};

export function checkoutMessage(locale: Locale, code?: string | null) {
  const [fa, en] = (code ? messages[code] : undefined) ?? ['تسویه موقتاً در دسترس نیست. دوباره تلاش کن.', 'Checkout is temporarily unavailable. Try again.'];
  return text(locale, fa, en);
}

export function checkoutError(locale: Locale, error: Error) {
  return error instanceof IdentityError && error.status === 401
    ? text(locale, 'برای ادامه دوباره وارد حساب شو.', 'Sign in again to continue.')
    : checkoutMessage(locale, error instanceof IdentityError ? error.code : null);
}

export const loginRequired = (error: Error | null) => error instanceof IdentityError && error.status === 401;

export function checkoutTime(value: string, locale: Locale) {
  return new Intl.DateTimeFormat(locale === 'fa' ? 'fa-IR' : 'en-US', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value));
}
