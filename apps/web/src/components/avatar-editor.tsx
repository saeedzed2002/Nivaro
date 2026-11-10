'use client';

import Image from 'next/image';
import { useEffect, useRef, useState } from 'react';
import { UserRound } from 'lucide-react';
import { avatarPath, changeAvatar, IdentityError, readAvatar, type AvatarStatus, type Scope } from '@/lib/identity-client';
import { text, type Locale } from '@/lib/content';
import { ConfirmAction, IdentityNotice } from './identity-shared';

export function AvatarEditor({ locale, scope }: { locale: Locale; scope: Scope }) {
  const [avatar, setAvatar] = useState<AvatarStatus>();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [refresh, setRefresh] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const pending = avatar?.state === 'uploaded' || avatar?.state === 'processing';
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await readAvatar(scope);
        if (!alive) return;
        setAvatar(current => current && current.version > value.version ? current : value);
        if (value.state === 'uploaded' || value.state === 'processing') timer = setTimeout(load, 1800);
      } catch (e) { if (alive) setError(e); }
    }
    void load();
    return () => { alive = false; clearTimeout(timer); };
  }, [scope, refresh]);
  async function submit(value: File | null) {
    if (!avatar) return;
    setError(null); setBusy(true);
    try {
      if (value && (value.size === 0 || value.size > 8 * 1024 * 1024)) throw new IdentityError('avatar.invalid_size');
      setAvatar(await changeAvatar(scope, avatar.version, value));
      setFile(null);
      if (input.current) input.current.value = '';
      setRefresh(count => count + 1);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <section className="identity-panel avatar-editor" aria-label={text(locale, 'تصویر پروفایل', 'Profile photo')}>
    <span className="avatar-portrait">{avatar?.active
      ? <Image unoptimized width={128} height={128} src={avatarPath(scope) + '/' + avatar.active + '/128'} alt={text(locale, 'تصویر فعلی پروفایل', 'Current profile photo')}/>
      : <UserRound size={48} aria-hidden/>}</span>
    <h2>{text(locale, 'تصویر پروفایل', 'Profile photo')}</h2>
    <div className="field"><label className="avatar-picker button secondary">{text(locale, 'انتخاب تصویر', 'Choose image')}
      <input type="file" ref={input} accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={e => setFile(e.target.files?.[0] || null)}/></label>{file && <bdi>{file.name}</bdi>}
      <small>{text(locale, 'یک تصویر ثابت تا ۸ مگابایت انتخاب کنید. تصویر به شکل مربع برش می‌خورد.', 'Choose a still image up to 8 MiB. It will be cropped to a square.')}</small>
    </div>
    <div className="identity-actions"><button type="button" className="button primary" disabled={!file || !avatar || busy} onClick={() => void submit(file)}>{text(locale, 'بارگذاری تصویر', 'Upload photo')}</button>
      {(avatar?.active || avatar?.candidate) && <ConfirmAction busy={busy} onConfirm={() => submit(null)} locale={locale} label={text(locale, 'حذف تصویر', 'Remove photo')} title={text(locale, 'تصویر حذف شود؟', 'Remove profile photo?')}>{text(locale, 'تصویر فعلی و درخواست جایگزینی از پروفایل حذف می‌شوند.', 'This clears the photo and any pending replacement.')}</ConfirmAction>}</div>
    {pending && <p role="status">{text(locale, 'در حال پردازش تصویر…', 'Processing photo…')}</p>}
    {avatar?.state === 'failed' && <p role="alert">{text(locale, 'پردازش تصویر انجام نشد. تصویر دیگری انتخاب کنید.', 'Photo processing failed. Choose another image.')}</p>}
    <IdentityNotice locale={locale} error={error}/>
    {Boolean(error) && <button type="button" className="text-link" onClick={() => { setError(null); setRefresh(count => count + 1); }}>{text(locale, 'دریافت وضعیت فعلی', 'Reload photo status')}</button>}
  </section>;
}
