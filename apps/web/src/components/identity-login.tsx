'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';
import { ArrowRight, CheckCircle2, Eye, EyeOff, Info, LockKeyhole, ShieldCheck } from 'lucide-react';
import { adminLogin, IdentityError, logout, readSession, requestCode, verifyCode, type Challenge, type IdentitySession } from '@/lib/identity-client';
import type { InitialIdentity } from '@/lib/identity-server';
import { text, type Locale } from '@/lib/content';
import { IdentityNotice } from './identity-shared';

const digits = (value: string) => value.replace(/[۰-۹٠-٩]/g, c => String('۰۱۲۳۴۵۶۷۸۹'.includes(c) ? '۰۱۲۳۴۵۶۷۸۹'.indexOf(c) : '٠١٢٣٤٥٦٧٨٩'.indexOf(c)));
const permissionLabels: Record<string, [string, string]> = {
  'catalog.write': ['مدیریت کاتالوگ', 'Catalog management'], 'reviews.moderate': ['مدیریت دیدگاه‌ها', 'Review moderation'],
  'orders.read': ['مشاهدهٔ سفارش‌ها', 'Order access'], 'orders.manage': ['مدیریت سفارش‌ها', 'Order management'],
  'payments.refund': ['بازپرداخت', 'Refunds'], 'support.reply': ['پاسخ‌گویی پشتیبانی', 'Support replies'],
  'users.manage': ['مدیریت کاربران', 'User management'], 'roles.manage': ['مدیریت دسترسی‌ها', 'Access management'],
};
export function IdentityLogin({ locale, admin = false, initial, mock = false }: { locale: Locale; admin?: boolean; initial: InitialIdentity; mock?: boolean }) {
  const router = useRouter();
  const [session, setSession] = useState<IdentitySession | null>(initial.session);
  const [phone, setPhone] = useState('');
  const [challenge, setChallenge] = useState<(Challenge & { sentAt: number }) | null>(null);
  const [code, setCode] = useState('');
  const [clock, setClock] = useState(0);
  const [waitUntil, setWaitUntil] = useState(0);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(initial.unavailable ? new IdentityError('identity.unavailable') : null);
  useEffect(() => {
    let alive = true;
    if (!initial.session && !initial.unavailable) readSession(admin ? 'admin' : 'customer').then(value => {
      if (!alive) return;
      if (admin) setSession(value); else router.replace(`/${locale}/account`);
    }).catch(e => { if (alive && (!(e instanceof IdentityError) || e.status !== 401)) setError(e); });
    else if (initial.session && !admin) router.replace(`/${locale}/account`);
    return () => { alive = false; };
  }, [admin, initial.session, initial.unavailable, locale, router]);
  useEffect(() => {
    if (!challenge && !waitUntil) return;
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [challenge, waitUntil]);
  const remaining = challenge ? Math.max(0, Math.ceil((challenge.sentAt + (challenge.expires_in ?? 120) * 1000 - clock) / 1000)) : 0;
  const resend = Math.max(0, Math.ceil((Math.max(waitUntil, challenge ? challenge.sentAt + (challenge.resend_after ?? 60) * 1000 : 0) - clock) / 1000));
  async function run(work: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await work(); } catch (e) {
      setError(e);
      if (e instanceof IdentityError && e.retryAfter) { setClock(Date.now()); setWaitUntil(Date.now() + e.retryAfter * 1000); }
    } finally { setBusy(false); }
  }
  async function send() {
    await run(async () => { const result = await requestCode(phone); const sentAt = Date.now(); setClock(sentAt); setChallenge({ ...result, sentAt }); setCode(''); });
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (admin) void run(async () => { setSession(await adminLogin(email, password)); setPassword(''); router.refresh(); });
    else if (!challenge) void send();
    else void run(async () => { await verifyCode(phone, challenge.challenge_id, code); setCode(''); router.replace(`/${locale}/account`); router.refresh(); });
  }
  return <main id="main-content" className={`identity-login-page ${admin ? 'staff-login-page' : ''}`}>
    <div className="container"><div className="identity-login-layout">
      <div className="identity-scene"><Image src="/images/showroom.webp" alt="" fill sizes="(max-width: 760px) 100vw, 50vw" priority/><div className="identity-scene-caption"><span className="eyebrow" dir="ltr">PLAY. BUILD. BELONG.</span><p>{text(locale, 'از اولین قطعه، تا ستاپ خودت.', 'From your first part to your own setup.')}</p></div></div>
      <section className="identity-login-card">
        <span className="identity-symbol">{admin ? <ShieldCheck size={28}/> : <LockKeyhole size={28}/>}</span>
        <p className="eyebrow">{admin ? text(locale, 'نیوارو · کارکنان', 'NIVARO · STAFF ACCESS') : text(locale, 'حساب نیوارو', 'YOUR NIVARO ACCOUNT')}</p>
        <h1>{admin ? session ? text(locale, 'نشست مدیریت', 'Staff session') : text(locale, 'ورود مدیران', 'Administrator sign-in') : challenge ? text(locale, 'تأیید کد ورود', 'Verify your code') : text(locale, 'به نیوارو وارد شوید', 'Welcome to Nivaro')}</h1>
        {admin && session ? <>
          <div className="identity-notice success"><CheckCircle2 size={20}/><span>{text(locale, 'ورود مدیر تأیید شد. دسترسی‌های این نشست:', 'Administrator verified. This session has access to:')}</span></div>
          <ul className="permission-list">{session.permissions.map(permission => <li key={permission}><ShieldCheck size={17}/>{permissionLabels[permission] ? text(locale, ...permissionLabels[permission]) : permission}</li>)}</ul>
          <p className="muted">{text(locale, 'این نشست از حساب خرید شما جداست.', 'This session is separate from your shopping account.')}</p>
          {session.permissions.includes('catalog.write') && <Link className="button primary" href={`/${locale}/admin/products`}>{text(locale, 'مدیریت محصولات', 'Manage products')}</Link>}
          <IdentityNotice error={error} locale={locale}/><button className="button secondary" disabled={busy} onClick={() => void run(async () => { await logout('admin', false); setSession(null); router.refresh(); })}>{text(locale, 'خروج از نشست مدیریت', 'Sign out of staff session')}</button>
        </> : <>
          <p className="muted">{admin ? text(locale, 'ویژهٔ کارکنان مجاز؛ با ایمیل و رمز عبور خود وارد شوید.', 'For authorized staff. Sign in with your email and password.') : challenge ? <>{text(locale, 'کد شش‌رقمی مربوط به این شماره را وارد کنید:', 'Enter the six-digit code for:')} <bdi dir="ltr">{phone}</bdi></> : text(locale, 'برای دسترسی به حساب، شمارهٔ موبایل خود را وارد کنید.', 'Enter your mobile number to access your account.')}</p>
          <form onSubmit={submit} className="identity-form">
            <fieldset disabled={busy}>
              {admin ? <><label className="field">{text(locale, 'ایمیل', 'Email')}<input type="email" dir="ltr" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required maxLength={254}/></label><label className="field">{text(locale, 'رمز عبور', 'Password')}<span className="password-field"><input type={visible ? 'text' : 'password'} dir="ltr" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required maxLength={256}/><button type="button" className="icon-button" aria-label={visible ? text(locale, 'پنهان کردن رمز', 'Hide password') : text(locale, 'نمایش رمز', 'Show password')} aria-pressed={visible} onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={18}/> : <Eye size={18}/>}</button></span></label></>
              : challenge ? <><label className="field">{text(locale, 'کد ورود', 'Sign-in code')}<input className="otp-input" dir="ltr" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={e => setCode(digits(e.target.value).replace(/\D/g, ''))} required autoFocus/></label><div className="identity-actions"><button type="button" className="text-link" onClick={() => { setChallenge(null); setCode(''); setError(null); }}>{text(locale, 'تغییر شماره', 'Change number')}</button><span className="muted">{remaining ? text(locale, `اعتبار: ${remaining} ثانیه`, `Valid for ${remaining}s`) : text(locale, 'اعتبار کد پایان یافت', 'Code expired')}</span></div>{challenge.development_code && <p className="mock-code">{text(locale, 'کد آزمایشی محلی:', 'Local test code:')} <strong dir="ltr" data-testid="development-code">{challenge.development_code}</strong></p>}</>
              : <label className="field">{text(locale, 'شمارهٔ موبایل', 'Mobile number')}<input aria-label={text(locale, 'شمارهٔ موبایل', 'Mobile number')} type="tel" dir="ltr" autoComplete="tel" placeholder={locale === 'fa' ? '0912… / +98…' : '+1… / +98…'} value={phone} onChange={e => setPhone(digits(e.target.value))} maxLength={40} required aria-describedby="phone-help"/><small id="phone-help">{text(locale, 'شمارهٔ ایران با صفر یا شمارهٔ بین‌المللی با پیش‌شمارهٔ کشور.', 'Iranian local format or an international number including country code.')}</small></label>}
              <IdentityNotice error={error} locale={locale}/>
              <button className="button primary" disabled={busy || (admin ? resend > 0 : challenge ? !remaining : resend > 0)}>{busy ? text(locale, 'در حال بررسی…', 'Please wait…') : admin ? text(locale, 'ورود به مدیریت', 'Sign in as administrator') : challenge ? text(locale, 'تأیید و ورود', 'Verify and sign in') : text(locale, 'دریافت کد ورود', 'Get sign-in code')}<ArrowRight size={18}/></button>
              {challenge && <button className="button secondary" type="button" disabled={resend > 0} onClick={() => void send()}>{resend ? text(locale, `دریافت مجدد پس از ${resend} ثانیه`, `Request again in ${resend}s`) : text(locale, 'دریافت کد جدید', 'Request a new code')}</button>}
              {!challenge && resend > 0 && <p role="status">{text(locale, `تلاش مجدد پس از ${resend} ثانیه`, `Try again in ${resend}s`)}</p>}
            </fieldset>
          </form>
          {!admin && mock && <div className="identity-notice"><Info size={20}/><p>{text(locale, 'محیط آزمایشی؛ پیامک واقعی ارسال نمی‌شود. فقط این شماره‌ها فعال‌اند:', 'Local test environment; no SMS is sent. Only these numbers are enabled:')} <bdi dir="ltr">+12025550100</bdi> · <bdi dir="ltr">+12025550101</bdi></p></div>}
        </>}
        <Link className="text-link identity-back" href={`/${locale}`}>{text(locale, 'بازگشت به فروشگاه', 'Back to the storefront')}</Link>
      </section>
    </div></div>
  </main>;
}
