'use client';

import Image from 'next/image';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { CheckCircle2, ImagePlus, LoaderCircle, Plus, Star, UploadCloud } from 'lucide-react';
import { changeProductImage, getAdminProduct, getProductImages, uploadProductImage, type AdminDetail, type MediaGallery } from '@/lib/admin-catalog-client';
import { IdentityError } from '@/lib/identity-client';
import { text, type Locale } from '@/lib/content';
import { CatalogNotice } from './admin-shared';
import { ConfirmAction } from './identity-shared';

export function AdminProductGallery({ product, locale, onDirty, onProduct }: { product: AdminDetail; locale: Locale; onDirty: (dirty: boolean) => void; onProduct: (product: AdminDetail) => void }) {
  const [gallery, setGallery] = useState<MediaGallery | null>(null);
  const [position, setPosition] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [alt, setAlt] = useState({ fa: '', en: '' });
  const [kind, setKind] = useState<'illustration' | 'exact_sku'>('illustration');
  const [draftVersion, setDraftVersion] = useState(product.version);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const dirty = !!file || !!alt.fa || !!alt.en;
  const dirtyCallback = useRef(onDirty);
  useEffect(() => { dirtyCallback.current = onDirty; }, [onDirty]);
  useEffect(() => { dirtyCallback.current(dirty || busy); }, [dirty, busy]);
  const processing = gallery?.items.some(item => ['uploaded', 'processing'].includes(item.pending?.state || ''));
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const data = await getProductImages(product.id);
        if (!alive) return;
        setGallery(data);
        if (data.items.some(item => ['uploaded', 'processing'].includes(item.pending?.state || ''))) timer = setTimeout(load, 2500);
      } catch (e) { if (alive) setError(e); }
    }
    void load();
    return () => { alive = false; clearTimeout(timer); };
  }, [product.id, reload]);
  // Activation can finish after the upload request; refresh readiness without
  // replacing a file/alternative-text draft or rebasing its expected revision.
  useEffect(() => {
    if (!gallery || processing || gallery.version === product.version) return;
    let alive = true;
    getAdminProduct(product.id).then(row => { if (alive) onProduct(row); }).catch(e => { if (alive) setError(e); });
    return () => { alive = false; };
  }, [gallery, processing, product.id, product.version, onProduct]);
  const selected = gallery?.items.find(item => item.position === position);
  const occupied = gallery?.items.filter(item => item.active || item.pending) || [];
  const free = Array.from({ length: 8 }, (_, i) => i).find(i => !occupied.some(item => item.position === i));
  function discard() {
    setFile(null); setAlt({ fa: '', en: '' }); setKind('illustration');
    if (input.current) input.current.value = '';
  }
  function pick(file: File | null) {
    setError(null); setNotice('');
    if (file && file.size > 8 * 1024 * 1024) { setError(new IdentityError('media.too_large')); if (input.current) input.current.value = ''; return; }
    if (!dirty) setDraftVersion(gallery?.version ?? product.version);
    setFile(file);
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!file || !gallery) return;
    setBusy(true); setError(null); setNotice('');
    try {
      await uploadProductImage(product.id, position, draftVersion, file, alt, kind);
      discard(); setReload(n => n + 1);
      setNotice(text(locale, 'تصویر دریافت شد؛ پس از پردازش موفق فعال می‌شود.', 'Image received. It becomes active after successful processing.'));
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function change(destination: number | null) {
    if (!gallery) return;
    setBusy(true); setError(null);
    try {
      await changeProductImage(product.id, position, gallery.version, destination);
      if (destination !== null) setPosition(destination);
      setGallery(await getProductImages(product.id)); onProduct(await getAdminProduct(product.id));
      setNotice(text(locale, 'گالری به‌روزرسانی شد.', 'Gallery updated.'));
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  const stateLabels = { uploaded: ['در صف پردازش', 'Queued'], processing: ['در حال پردازش', 'Processing'], ready: ['آماده', 'Ready'], failed: ['جایگزینی ناموفق', 'Replacement failed'] } as const;
  return <div className="admin-editor-layout">
    <section className="admin-panel admin-gallery">
      <div className="admin-panel-heading"><h2>{text(locale, 'تصاویر محصول', 'Product images')}</h2><span>{text(locale, `${occupied.length} از ۸ تصویر`, `${occupied.length} of 8 images`)}</span></div>
      <p className="admin-notice">{text(locale, 'تصویر قبلی تا آماده‌شدن تصویر جایگزین حفظ می‌شود.', 'The previous image stays active until its replacement is ready.')}</p>
      <CatalogNotice error={error} locale={locale}/>
      {!!error && <button type="button" className="button secondary" disabled={busy} onClick={async () => {
        if (dirty && !window.confirm(text(locale, 'نسخهٔ جدید بارگیری شود؟ فایل و متن شما حفظ می‌شوند؛ پیش از ارسال دوباره، تصویر فعلی را بررسی کنید.', 'Load the latest revision? Your file and text stay intact. Review the current image before submitting again.'))) return;
        try { const data = await getProductImages(product.id); setGallery(data); setDraftVersion(data.version); setError(null); setReload(n => n + 1); } catch (e) { setError(e); }
      }}>{text(locale, 'بارگیری وضعیت فعلی', 'Reload current status')}</button>}
      {notice && <p role="status" className="admin-notice success"><CheckCircle2 size={18}/>{notice}</p>}
      {!gallery ? <p role="status">{text(locale, 'در حال دریافت گالری…', 'Loading gallery…')}</p> : <>
        <div className="admin-gallery-grid" aria-label={text(locale, 'انتخاب تصویر', 'Choose image')}>
          {occupied.map(item => {
            const widths = Object.keys(item.urls).map(Number).sort((a, b) => a - b);
            const url = item.urls[String(widths.find(width => width >= 320) ?? widths.at(-1))];
            const state = item.pending?.state || item.active?.state;
            return <button type="button" className="admin-gallery-tile" key={item.position} disabled={busy || (dirty && position !== item.position)} aria-pressed={position === item.position} onClick={() => { setPosition(item.position); setNotice(''); }}>
              <span className="admin-gallery-art">{url ? <Image src={url} unoptimized fill sizes="180px" alt={item.alt[locale] || ''}/> : <ImagePlus size={38}/>}</span>
              <strong>{text(locale, `تصویر ${item.position + 1}`, `Image ${item.position + 1}`)}</strong>
              {state && <span className={`media-state ${state}`}>{['uploaded', 'processing'].includes(state) && <LoaderCircle size={15} className="media-spinner"/>}{text(locale, stateLabels[state][0], stateLabels[state][1])}</span>}
              {item.active && product.image.includes(item.active.id) && <span className="admin-gallery-cover"><Star size={13}/>{text(locale, 'تصویر اصلی', 'Cover image')}</span>}
            </button>;
          })}
          {free !== undefined && <button type="button" className="admin-gallery-add" disabled={busy || dirty} aria-pressed={position === free} onClick={() => { setPosition(free); setNotice(''); input.current?.focus(); }}><Plus size={25}/>{text(locale, 'افزودن تصویر', 'Add image')}</button>}
        </div>
        {selected?.pending?.state === 'failed' && <p className="admin-notice error" role="alert">{text(locale, 'پردازش این فایل موفق نبود. تصویر قبلی حفظ شده است؛ یک فایل ثابت و معتبر با حداکثر ۲۴ میلیون پیکسل انتخاب کنید و دوباره بفرستید.', 'This file could not be processed. The previous image is preserved. Choose a valid static image up to 24 million pixels and upload again.')}</p>}
        <form className="admin-form" onSubmit={submit}>
          <fieldset disabled={busy || !gallery}>
            <h3>{text(locale, `بارگذاری برای جایگاه ${position + 1}`, `Upload to slot ${position + 1}`)}</h3>
            <label className="admin-upload-zone"><UploadCloud size={32}/><span>{text(locale, 'انتخاب فایل تصویر', 'Choose image file')}</span><input ref={input} aria-label={text(locale, 'فایل تصویر', 'Image file')} type="file" accept="image/jpeg,image/png,image/webp" onChange={e => pick(e.target.files?.[0] || null)} required/><small>{text(locale, 'JPEG، PNG یا WebP ثابت · حداکثر ۸ مِبی‌بایت و ۲۴ میلیون پیکسل', 'Static JPEG, PNG or WebP · up to 8 MiB and 24 million pixels')}</small></label>
            <div className="admin-form-grid">
              <label>{text(locale, 'متن جایگزین فارسی', 'Persian alternative text')}<input value={alt.fa} required maxLength={240} dir="rtl" onChange={e => { if (!dirty) setDraftVersion(gallery.version); setAlt(v => ({ ...v, fa: e.target.value })); }}/></label>
              <label>{text(locale, 'متن جایگزین انگلیسی', 'English alternative text')}<input value={alt.en} required maxLength={240} dir="ltr" onChange={e => { if (!dirty) setDraftVersion(gallery.version); setAlt(v => ({ ...v, en: e.target.value })); }}/></label>
            </div>
            <label>{text(locale, 'نوع تصویر', 'Image type')}<select value={kind} onChange={e => setKind(e.target.value as typeof kind)}><option value="illustration">{text(locale, 'تصویر مفهومی یا تصویر عمومی دسته', 'Illustration or generic category image')}</option><option value="exact_sku">{text(locale, 'تصویر دقیق همین مدل محصول', 'Exact photograph of this product model')}</option></select></label>
            <p className="admin-hint">{text(locale, 'فقط تصاویر دارای مجوز استفاده را بارگذاری کنید. متن جایگزین باید ظاهر تصویر را توضیح بدهد.', 'Upload only images you have permission to use. Alternative text should describe what the image shows.')}</p>
            <div className="admin-actions"><button className="button primary" disabled={!file || busy}><UploadCloud size={18}/>{busy ? text(locale, 'در حال ارسال…', 'Uploading…') : text(locale, 'ارسال برای پردازش', 'Upload for processing')}</button>{dirty && <button type="button" className="button secondary" onClick={discard}>{text(locale, 'کنارگذاشتن فایل و متن', 'Discard file and text')}</button>}</div>
          </fieldset>
        </form>
        {selected && (selected.active || selected.pending) && <div className="admin-gallery-actions">
          {selected.active && position !== 0 && <button className="button secondary" disabled={busy || dirty || processing} onClick={() => void change(0)}><Star size={17}/>{text(locale, 'انتخاب به‌عنوان تصویر اصلی', 'Use as cover image')}</button>}
          <ConfirmAction locale={locale} label={text(locale, 'حذف این تصویر', 'Remove this image')} title={text(locale, 'تصویر از گالری حذف شود؟', 'Remove this image from the gallery?')} busy={busy || dirty} onConfirm={() => change(null)}>{text(locale, 'این جایگاه خالی می‌شود و جایگزینی در حال پردازش آن نیز فعال نخواهد شد.', 'This slot will be cleared. Its pending replacement will not become active.')}</ConfirmAction>
        </div>}
      </>}
    </section>
    <aside className="admin-editor-aside"><section className="admin-panel"><ImagePlus size={28}/><h2>{text(locale, 'تصویری روشن از محصول', 'A clear view of the product')}</h2><p>{text(locale, 'نمای اصلی و جزئیات مهم محصول را در تصویرهای جداگانه نشان دهید. اولین تصویر آماده، تصویر اصلی فروشگاه است.', 'Show the main view and important details in separate images. The first ready image is the storefront cover.')}</p><p className="admin-hint">{text(locale, 'تصاویر مفهومی به‌عنوان تصویر دقیق مدل نمایش داده نمی‌شوند.', 'Illustrations are not presented as exact model photographs.')}</p></section></aside>
  </div>;
}
