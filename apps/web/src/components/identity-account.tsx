'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';
import { ArrowRight, CheckCircle2, Home, LogOut, MapPin, Plus, ShieldCheck, UserRound } from 'lucide-react';
import { deleteAddress, IdentityError, listAddresses, logout, readSession, saveAddress, saveProfile, type Address, type AddressInput, type IdentitySession } from '@/lib/identity-client';
import type { InitialIdentity } from '@/lib/identity-server';
import { text, type Locale } from '@/lib/content';
import { ConfirmAction, IdentityNotice } from './identity-shared';

import { AvatarEditor } from './avatar-editor';

export type AccountView = 'overview' | 'profile' | 'addresses';
export function IdentityAccount({ locale, initial, view }: { locale: Locale; initial: InitialIdentity; view: AccountView }) {
  const [session, setSession] = useState(initial.session);
  const [error, setError] = useState<unknown>(initial.unavailable ? new IdentityError('identity.unavailable') : null);
  const [checking, setChecking] = useState(!initial.session && !initial.unavailable);
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  async function recover() {
    setChecking(true); setError(null);
    try { setSession(await readSession()); } catch (e) { setError(e); } finally { setChecking(false); }
  }
  useEffect(() => {
    let alive = true;
    if (!initial.session && !initial.unavailable) readSession().then(value => { if (alive) setSession(value); }).catch(e => { if (alive) setError(e); }).finally(() => { if (alive) setChecking(false); });
    return () => { alive = false; };
  }, [initial]);
  async function signOut(all: boolean) {
    setBusy(true); setError(null);
    try { await logout('customer', all); setSession(null); router.replace(`/${locale}/login`); router.refresh(); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  const title = view === 'profile' ? text(locale, 'اطلاعات حساب', 'Account details') : view === 'addresses' ? text(locale, 'نشانی‌های من', 'My addresses') : text(locale, 'حساب من', 'My account');
  if (!session) return <main id="main-content" className="container account-page"><section className="identity-panel account-guard"><ShieldCheck size={36}/><h1>{title}</h1>{checking ? <p role="status">{text(locale, 'در حال بررسی نشست…', 'Checking your session…')}</p> : <><IdentityNotice error={error} locale={locale}/><div className="identity-actions"><Link className="button primary" href={`/${locale}/login`}>{text(locale, 'ورود به حساب', 'Sign in')}</Link><button className="button secondary" onClick={() => void recover()}>{text(locale, 'تلاش مجدد', 'Retry')}</button></div></>}</section></main>;
  return <main id="main-content" className="container account-page">
    <div className="breadcrumb"><Link href={`/${locale}`}>{text(locale, 'خانه', 'Home')}</Link><span>/</span><Link href={`/${locale}/account`}>{text(locale, 'حساب من', 'My account')}</Link>{view !== 'overview' && <><span>/</span><span>{title}</span></>}</div>
    <div className="account-layout"><aside className="account-sidebar identity-panel"><div className="account-person"><UserRound size={30}/><strong>{session.profile.name || text(locale, 'حساب نیوارو', 'Nivaro account')}</strong><bdi dir="ltr">{session.profile.phone}</bdi></div><nav aria-label={text(locale, 'ناوبری حساب', 'Account navigation')}>
      {([{ id: 'overview', path: '', fa: 'نمای کلی', en: 'Overview', icon: Home }, { id: 'profile', path: '/profile', fa: 'اطلاعات حساب', en: 'Account details', icon: UserRound }, { id: 'addresses', path: '/addresses', fa: 'نشانی‌ها', en: 'Addresses', icon: MapPin }] as const).map(item => <Link key={item.id} aria-current={view === item.id ? 'page' : undefined} href={`/${locale}/account${item.path}`}><item.icon size={20}/>{text(locale, item.fa, item.en)}</Link>)}
      <button disabled={busy} onClick={() => void signOut(false)}><LogOut size={20}/>{text(locale, 'خروج از حساب', 'Sign out')}</button>
    </nav></aside>
    <section className="account-content"><h1>{title}</h1><IdentityNotice error={error} locale={locale}/>
      {view === 'overview' ? <>
        <p className="muted">{session.profile.name ? text(locale, `سلام ${session.profile.name}،`, `Hello ${session.profile.name},`) : text(locale, 'خوش آمدید.', 'Welcome.')} {text(locale, 'اطلاعات حساب و نشانی‌های خود را اینجا مدیریت کنید.', 'Manage your account and addresses here.')}</p>
        <div className="account-shortcuts"><Link className="identity-panel" href={`/${locale}/account/profile`}><UserRound size={30}/><span><strong>{text(locale, 'اطلاعات حساب', 'Account details')}</strong><small>{text(locale, 'مشاهده و ویرایش اطلاعات شخصی', 'View and edit personal information')}</small></span><ArrowRight size={19}/></Link><Link className="identity-panel" href={`/${locale}/account/addresses`}><MapPin size={30}/><span><strong>{text(locale, 'نشانی‌ها', 'Addresses')}</strong><small>{text(locale, 'مدیریت نشانی‌های ذخیره‌شده', 'Manage your saved addresses')}</small></span><ArrowRight size={19}/></Link></div>
        <div className="account-promo"><Image src="/images/showroom.webp" alt="" fill sizes="(max-width: 760px) 100vw, 70vw"/><div><h2>{text(locale, 'برای ستاپ بعدی آماده شو', 'Ready for your next setup?')}</h2><p>{text(locale, 'قطعات و تجهیزات گیمینگ را بررسی کن.', 'Explore gaming hardware and peripherals.')}</p><Link className="button primary" href={`/${locale}/products`}>{text(locale, 'مشاهدهٔ قطعات', 'Explore components')}<ArrowRight size={18}/></Link></div></div>
        <div className="identity-panel account-security"><ShieldCheck size={30}/><div><h2>{text(locale, 'امنیت حساب', 'Account security')}</h2><p className="muted">{text(locale, 'نشست‌های خرید خود را در همهٔ دستگاه‌ها، شامل همین دستگاه، ببندید.', 'End your shopping sessions on every device, including this one.')}</p></div><ConfirmAction locale={locale} label={text(locale, 'خروج از همهٔ دستگاه‌ها', 'Sign out everywhere')} title={text(locale, 'از همهٔ دستگاه‌ها خارج شوید؟', 'Sign out on every device?')} busy={busy} onConfirm={() => signOut(true)}>{text(locale, 'این دستگاه نیز خارج می‌شود. نشست‌های مدیریتی جداگانه باقی می‌مانند.', 'This device will also be signed out. Separate staff sessions are unaffected.')}</ConfirmAction></div>
      </> : view === 'profile' ? <div className="profile-workspace"><AvatarEditor locale={locale} scope="customer"/><ProfileForm locale={locale} session={session} onSaved={profile => setSession({ ...session, profile })}/></div> : <Addresses locale={locale} phone={session.profile.phone}/>}
    </section></div>
  </main>;
}
function ProfileForm({ locale, session, onSaved }: { locale: Locale; session: IdentitySession; onSaved: (profile: IdentitySession['profile']) => void }) {
  const [name, setName] = useState(session.profile.name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  async function submit(e: FormEvent) { e.preventDefault(); setBusy(true); setError(null); setSaved(false); try { onSaved(await saveProfile(name)); setSaved(true); } catch (e) { setError(e); } finally { setBusy(false); } }
  return <form className="identity-panel identity-form profile-form" onSubmit={submit}><div className="profile-intro"><span className="identity-avatar"><UserRound size={40}/></span><div><h2>{text(locale, 'اطلاعات شخصی', 'Personal information')}</h2><p className="muted">{text(locale, 'نام شما برای نمایش در حساب استفاده می‌شود.', 'Your name is used to personalize your account.')}</p></div></div><fieldset disabled={busy}><label className="field">{text(locale, 'نام و نام خانوادگی', 'Full name')}<input autoComplete="name" value={name} onChange={e => { setName(e.target.value); setSaved(false); }} maxLength={80}/></label><label className="field">{text(locale, 'شمارهٔ تأییدشده', 'Verified mobile number')}<input dir="ltr" readOnly value={session.profile.phone}/><small>{text(locale, 'تغییر شماره در این نسخه در دسترس نیست.', 'Changing your mobile number is not available in this version.')}</small></label><IdentityNotice error={error} locale={locale}/>{saved && <p className="identity-notice success" role="status"><CheckCircle2 size={20}/>{text(locale, 'اطلاعات حساب ذخیره شد.', 'Account details saved.')}</p>}<div className="identity-actions"><button className="button primary">{busy ? text(locale, 'در حال ذخیره…', 'Saving…') : text(locale, 'ذخیرهٔ تغییرات', 'Save changes')}</button><Link className="text-link" href={`/${locale}/account`}>{text(locale, 'بازگشت به حساب', 'Back to account')}</Link></div></fieldset>{error instanceof IdentityError && error.status === 401 && <Link className="text-link" href={`/${locale}/login`}>{text(locale, 'ورود مجدد', 'Sign in again')}</Link>}</form>;
}
function Addresses({ locale, phone }: { locale: Locale; phone: string }) {
  const [items, setItems] = useState<Address[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<{ item?: Address } | null>(null);
  const [notice, setNotice] = useState('');
  async function reload() { setLoading(true); setError(null); try { setItems(await listAddresses()); } catch (e) { setError(e); } finally { setLoading(false); } }
  useEffect(() => { let alive = true; listAddresses().then(values => { if (alive) setItems(values); }).catch(e => { if (alive) setError(e); }).finally(() => { if (alive) setLoading(false); }); return () => { alive = false; }; }, []);
  async function remove(item: Address) { setBusy(true); setError(null); try { await deleteAddress(item); setItems(items.filter(value => value.id !== item.id)); setNotice(text(locale, 'نشانی حذف شد.', 'Address deleted.')); } catch (e) { setError(e); } finally { setBusy(false); } }
  return <div className="addresses-workspace"><p className="muted">{text(locale, 'نشانی‌های ذخیره‌شدهٔ شما؛ ثبت نشانی به معنی فعال بودن ارسال به آن کشور نیست.', 'Your saved addresses. Saving an address does not confirm delivery to that country.')}</p><IdentityNotice error={error} locale={locale}/>{Boolean(error) && <button className="button secondary" onClick={() => void reload()} disabled={loading}>{text(locale, 'تازه کردن فهرست', 'Reload addresses')}</button>}{notice && <p className="identity-notice success" role="status">{notice}</p>}
    {loading ? <p role="status">{text(locale, 'در حال دریافت نشانی‌ها…', 'Loading addresses…')}</p> : !error && !items.length ? <div className="identity-panel address-empty"><MapPin size={52}/><h2>{text(locale, 'هنوز نشانی ثبت نکرده‌اید', 'No addresses yet')}</h2><p className="muted">{text(locale, 'نخستین نشانی خود را اینجا اضافه کنید.', 'Add your first address here.')}</p>{!form && <button className="button primary" onClick={() => setForm({})}><Plus size={18}/>{text(locale, 'افزودن نشانی', 'Add address')}</button>}</div> : <div className="address-list">{items.map(item => <article className="identity-panel" key={item.id}><div className="address-title"><MapPin size={24}/><h2>{item.label}</h2></div><p>{item.recipient}</p><p>{item.street}</p><p>{item.city} · <bdi>{item.country}</bdi></p><p><bdi>{item.postal_code}</bdi> · <bdi dir="ltr">{item.phone}</bdi></p><div className="identity-actions"><button className="button secondary" disabled={busy} onClick={() => { setForm({ item }); setNotice(''); }}>{text(locale, 'ویرایش', 'Edit')}</button><ConfirmAction locale={locale} label={text(locale, 'حذف', 'Delete')} title={text(locale, 'نشانی حذف شود؟', 'Delete this address?')} busy={busy} onConfirm={() => remove(item)}>{item.label}</ConfirmAction></div></article>)}</div>}
    {!form && items.length > 0 && <button className="button primary" onClick={() => { setForm({}); setNotice(''); }}><Plus size={18}/>{text(locale, 'افزودن نشانی', 'Add address')}</button>}
    {form && <AddressForm key={`${form.item?.id || 'new'}-${form.item?.version || 0}`} locale={locale} item={form.item} phone={phone} onCancel={() => setForm(null)} onSaved={item => { setItems(previous => [...previous.filter(v => v.id !== item.id), item]); setForm(null); setNotice(text(locale, 'نشانی ذخیره شد.', 'Address saved.')); }}/>}</div>;
}
function AddressForm({ locale, item, phone, onCancel, onSaved }: { locale: Locale; item?: Address; phone: string; onCancel: () => void; onSaved: (item: Address) => void }) {
  const [body, setBody] = useState<AddressInput>(item || { label: '', recipient: '', country: locale === 'fa' ? 'IR' : 'US', city: '', postal_code: '', street: '', phone });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) { e.preventDefault(); setError(null); setBusy(true); try { const { label, recipient, country, city, postal_code, street, phone } = body; onSaved(await saveAddress({ label, recipient, country, city, postal_code, street, phone }, item)); } catch (e) { setError(e); } finally { setBusy(false); } }
  const fields = [
    { key: 'label', fa: 'عنوان نشانی', en: 'Address label', max: 40, auto: 'off' }, { key: 'recipient', fa: 'نام گیرنده', en: 'Recipient name', max: 80, auto: 'name' },
    { key: 'country', fa: 'کد دوحرفی کشور', en: 'Two-letter country code', max: 2, auto: 'country' }, { key: 'city', fa: 'شهر', en: 'City', max: 80, auto: 'address-level2' },
    { key: 'postal_code', fa: 'کد پستی', en: 'Postal code', max: 20, auto: 'postal-code' }, { key: 'phone', fa: 'شمارهٔ تماس', en: 'Contact number', max: 40, auto: 'tel' },
  ] as const;
  return <form className="identity-panel identity-form address-form" onSubmit={submit}><h2>{item ? text(locale, 'ویرایش نشانی', 'Edit address') : text(locale, 'نشانی جدید', 'New address')}</h2><fieldset disabled={busy}><div className="address-fields">{fields.map(field => <label className="field" key={field.key}>{text(locale, field.fa, field.en)}<input aria-label={text(locale, field.fa, field.en)} name={field.key} dir={['country', 'postal_code', 'phone'].includes(field.key) ? 'ltr' : undefined} autoComplete={field.auto} type={field.key === 'phone' ? 'tel' : 'text'} required maxLength={field.max} pattern={field.key === 'country' ? '[A-Z]{2}' : field.key === 'postal_code' && body.country === 'IR' ? '[0-9۰-۹٠-٩]{10}' : undefined} value={body[field.key]} onChange={e => setBody({ ...body, [field.key]: field.key === 'country' ? e.target.value.toUpperCase() : e.target.value })}/>{field.key === 'country' && <small>{text(locale, 'ایران: IR · آمریکا: US · کد استاندارد کشور', 'Iran: IR · United States: US · ISO country code')}</small>}{field.key === 'postal_code' && body.country === 'IR' && <small>{text(locale, 'کد پستی ده‌رقمی ایران', 'Ten-digit Iranian postal code')}</small>}</label>)}</div><label className="field">{text(locale, 'نشانی کامل', 'Street address')}<textarea autoComplete="street-address" required minLength={5} maxLength={500} rows={3} value={body.street} onChange={e => setBody({ ...body, street: e.target.value })}/></label><IdentityNotice error={error} locale={locale}/><div className="identity-actions"><button className="button primary">{busy ? text(locale, 'در حال ذخیره…', 'Saving…') : text(locale, 'ذخیرهٔ نشانی', 'Save address')}</button><button className="button secondary" type="button" onClick={onCancel}>{text(locale, 'انصراف', 'Cancel')}</button></div></fieldset></form>;
}
