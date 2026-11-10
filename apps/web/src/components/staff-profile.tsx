'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { readStaffProfile, saveStaffName } from '@/lib/identity-client';
import { text, type Locale } from '@/lib/content';
import { AvatarEditor } from './avatar-editor';
import { IdentityNotice } from './identity-shared';

export function StaffProfile({ locale }: { locale: Locale }) {
  const [profile, setProfile] = useState<Awaited<ReturnType<typeof readStaffProfile>>>();
  const [name, setName] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let alive = true;
    readStaffProfile().then(value => {
      if (alive) { setProfile(value); setName(value.name); setError(null); }
    }).catch(e => { if (alive) setError(e); });
    return () => { alive = false; };
  }, [attempt]);
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setSaved(false); setError(null);
    try { const result = await saveStaffName(name); setProfile(result); setName(result.name); setSaved(true); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  const roles: Record<string, [string, string]> = {
    super_admin: ['مدیر کل', 'Super administrator'], catalog_manager: ['مدیر کاتالوگ', 'Catalog manager'],
    support_agent: ['کارشناس پشتیبانی', 'Support agent'], sales_manager: ['مدیر فروش', 'Sales manager'],
  };
  return <><h1>{text(locale, 'پروفایل کارکنان', 'Staff profile')}</h1><div className="profile-workspace">
    <AvatarEditor locale={locale} scope="admin"/>
    <form className="identity-panel identity-form" onSubmit={submit} data-unsaved={Boolean(profile && name !== profile.name)}>
      <h2>{text(locale, 'اطلاعات کارکنان', 'Staff details')}</h2>
      <IdentityNotice error={error} locale={locale}/>
      {!profile && Boolean(error) && <button type="button" className="button secondary" onClick={() => setAttempt(v => v + 1)}>{text(locale, 'تلاش دوباره', 'Try again')}</button>}
      <fieldset disabled={!profile || busy}>
        <label className="field">{text(locale, 'نام نمایشی', 'Display name')}<input autoComplete="name" maxLength={80} value={name} onChange={e => { setName(e.target.value); setSaved(false); }}/></label>
        <label className="field">{text(locale, 'ایمیل کارکنان', 'Staff email')}<input dir="ltr" readOnly value={profile?.email ?? ''}/></label>
        <label className="field">{text(locale, 'نقش', 'Role')}<input readOnly value={profile && roles[profile.role] ? text(locale, ...roles[profile.role]) : profile?.role ?? ''}/></label>
        <button className="button primary" disabled={profile?.name === name}>{text(locale, 'ذخیرهٔ نام نمایشی', 'Save display name')}</button>
      </fieldset>
      {saved && <p role="status">{text(locale, 'نام نمایشی ذخیره شد.', 'Display name saved.')}</p>}
    </form></div></>;
}
