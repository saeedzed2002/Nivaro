'use client';

import { BadgeCheck } from 'lucide-react';
import { IdentityError } from '@/lib/identity-client';
import { text, type Locale } from '@/lib/content';
import type { SavedReview } from '@/lib/reviews-client';

export function reviewStatus(locale: Locale, status: SavedReview['status']) {
  const labels = {
    pending: ['در انتظار بررسی', 'Pending review'],
    approved: ['تأییدشده', 'Approved'],
    rejected: ['ردشده', 'Rejected'],
  } as const;
  const [fa, en] = labels[status];
  return text(locale, fa, en);
}

export function ReviewRating({ locale, value }: { locale: Locale; value: number }) {
  const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 2 });
  return <span className="review-rating">{text(locale, `${number.format(value)} از ${number.format(5)}`, `${number.format(value)} out of 5`)}</span>;
}

export function VerifiedPurchase({ locale }: { locale: Locale }) {
  return <span className="review-verified"><BadgeCheck size={16} aria-hidden="true"/>{text(locale, 'خرید تأییدشده', 'Verified purchase')}</span>;
}

export function ReviewProblem({ locale, error }: { locale: Locale; error: unknown }) {
  const status = error instanceof IdentityError ? error.status : 0;
  const label = status === 401 ? text(locale, 'برای ادامه دوباره وارد شوید.', 'Sign in to continue.')
    : status === 403 ? text(locale, 'این درخواست مجاز نیست.', 'This request is not authorized.')
    : status === 409 ? text(locale, 'دیدگاه تغییر کرده است. پیش از ثبت دوباره، نسخهٔ فعلی را بارگیری کنید.', 'The review changed. Reload the current version before submitting again.')
    : status === 422 ? text(locale, 'مقادیر فرم را بررسی کنید.', 'Check the form values.')
    : text(locale, 'ارتباط با بخش دیدگاه‌ها برقرار نشد.', 'Could not connect to reviews.');
  return <p className="review-error" role="alert">{label}</p>;
}
