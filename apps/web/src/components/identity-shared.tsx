'use client';
import { useId, useRef, type ReactNode } from 'react';
import { AlertCircle, X } from 'lucide-react';
import { IdentityError } from '@/lib/identity-client';
import { text, type Locale } from '@/lib/content';

export function errorText(error: unknown, locale: Locale): string {
  const code = error instanceof IdentityError ? error.code : 'identity.unavailable';
  const messages: Record<string, [string, string]> = {
    'login.invalid': ['کد یا اطلاعات ورود درست نیست یا اعتبار آن پایان یافته است.', 'The code or credentials are invalid or have expired.'],
    'login.rate_limited': ['تعداد تلاش‌ها بیش از حد مجاز است. پس از زمان اعلام‌شده دوباره تلاش کنید.', 'Too many attempts. Try again after the indicated wait.'],
    'session.invalid': ['نشست شما پایان یافته است. دوباره وارد شوید؛ اطلاعات ذخیره‌نشده را پیش از خروج کپی کنید.', 'Your session has ended. Sign in again; copy any unsaved information before leaving.'],
    'session.refresh_race': ['نشست در پنجرهٔ دیگری تازه شد. دوباره تلاش کنید.', 'Another tab refreshed the session. Please try again.'],
    'avatar.changed': ['تصویر تغییر کرده است. وضعیت فعلی را دریافت کنید.', 'The photo changed. Reload its status before trying again.'],
    'avatar.invalid_size': ['تصویر باید بین یک بایت تا هشت مگابایت باشد.', 'Select a non-empty file up to 8 MiB.'],
    'address.changed': ['این نشانی در پنجرهٔ دیگری تغییر کرده است. فهرست را تازه کنید و دوباره ویرایش کنید.', 'This address changed in another tab. Reload the list before editing again.'],
    'address.limit': ['حداکثر بیست نشانی قابل ذخیره است.', 'You can save up to twenty addresses.'],
    'request.invalid': ['اطلاعات فرم را بررسی کنید؛ شماره باید معتبر و کد پستی ایران ده رقم باشد.', 'Check the form values, phone number and postal code. Iranian postal codes require ten digits.'],
    'csrf.invalid': ['اعتبار درخواست تغییر کرده است. دوباره تلاش کنید.', 'Request verification changed. Please try again.'],
    'identity.unavailable': ['ارتباط با سرویس حساب برقرار نشد. اطلاعات فرم حفظ شده است؛ دوباره تلاش کنید.', 'The account service is unavailable. Your form is preserved; please try again.'],
    'delivery.unavailable': ['ارسال کد در حال حاضر در دسترس نیست.', 'Code delivery is currently unavailable.'],
  };
  const message = messages[code] || messages['identity.unavailable'];
  return text(locale, ...message);
}
export function IdentityNotice({ error, locale }: { error: unknown; locale: Locale }) {
  return error ? <div className="identity-notice error" role="alert"><AlertCircle size={20}/><span>{errorText(error, locale)}</span></div> : null;
}
export function ConfirmAction({ locale, label, title, children, onConfirm, busy }: { locale: Locale; label: string; title: string; children: ReactNode; onConfirm: () => Promise<void>; busy?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  return <><button type="button" className="button danger" disabled={busy} onClick={() => ref.current?.showModal()}>{label}</button><dialog className="feature-dialog" ref={ref} aria-labelledby={id}>
    <div className="dialog-content"><form method="dialog"><button className="icon-button close" aria-label={text(locale, 'بستن', 'Close')} disabled={busy}><X size={20}/></button></form><h2 id={id}>{title}</h2><p>{children}</p><div className="identity-actions"><button type="button" className="button secondary" disabled={busy} onClick={() => ref.current?.close()}>{text(locale, 'انصراف', 'Cancel')}</button><button type="button" className="button danger" disabled={busy} onClick={async () => { await onConfirm(); ref.current?.close(); }}>{text(locale, 'تأیید', 'Confirm')}</button></div></div>
  </dialog></>;
}
