'use client';

import Link from 'next/link';
import { text, type Locale } from '@/lib/content';
import { IdentityError } from '@/lib/identity-client';

export const refundLabels = {
  pending: ['در صف', 'Pending'],
  awaiting_evidence: ['منتظر تأیید بازپرداخت', 'Awaiting evidence'],
  completed: ['تکمیل‌شده', 'Completed'],
  manual_review: ['نیازمند بررسی دستی', 'Manual review'],
} as const;

export function accessLost(error: unknown) {
  return error instanceof IdentityError && (error.status === 401 || error.status === 403);
}

export function PaymentViews({ locale, current }: { locale: Locale; current: 'attempts' | 'refunds' }) {
  const base = `/${locale}/admin/payments`;
  return <nav className="payment-views" aria-label={text(locale, 'نماهای مدیریت پرداخت', 'Payment operations views')}>
    <Link href={base} aria-current={current === 'attempts' ? 'page' : undefined}>{text(locale, 'تلاش‌های پرداخت', 'Payment attempts')}</Link>
    <Link href={`${base}?view=refunds`} aria-current={current === 'refunds' ? 'page' : undefined}>{text(locale, 'صف بازپرداخت', 'Refund queue')}</Link>
  </nav>;
}

export function PaymentProblem({ locale, error, retry }: { locale: Locale; error: unknown; retry?: () => void }) {
  const issue = error instanceof IdentityError ? error : null;
  const message = issue?.status === 401 ? text(locale, 'نشست مدیریت پایان یافته است.', 'Your staff session has ended.')
    : issue?.status === 403 ? text(locale, 'این حساب مجوز مشاهدهٔ پرداخت‌ها را ندارد.', 'This account does not have permission to view payments.')
    : issue?.code === 'payments.cursor_not_found' || issue?.code === 'checkout.not_found' ? text(locale, 'نقطهٔ ادامهٔ فهرست پیدا نشد. فهرست را تازه کنید.', 'The list cursor is unavailable. Reload the list.')
    : issue?.status === 404 ? text(locale, 'تلاش پرداخت پیدا نشد.', 'Payment attempt not found.')
    : text(locale, 'دریافت اطلاعات پرداخت ممکن نشد.', 'Could not load payment information.');
  return <div className="payment-problem"><p role="alert" className="admin-notice error">{message}</p>
    {issue?.status === 401 && <Link className="text-link" href={`/${locale}/admin/login`}>{text(locale, 'ورود مدیران', 'Administrator sign-in')}</Link>}
    {retry && !accessLost(error) && <button className="button secondary" type="button" onClick={retry}>{text(locale, 'بارگیری دوباره', 'Reload')}</button>}
  </div>;
}
