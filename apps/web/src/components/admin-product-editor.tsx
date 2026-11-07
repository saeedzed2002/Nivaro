'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { AlertCircle, Box, CheckCircle2, ChevronLeft, ChevronRight, Save } from 'lucide-react';
import { adminCategories, createAdminProduct, getAdminProduct, productAudit, saveAdminProduct, saveAdminStock, setProductStatus, type AdminCategory, type AdminDetail, type AuditPage, type ProductContent } from '@/lib/admin-catalog-client';
import { text, type Locale } from '@/lib/content';
import { CatalogNotice, Readiness, StatusBadge } from './admin-shared';
import { ConfirmAction } from './identity-shared';
import { AdminVariantEditor } from './admin-variant-editor';
import { AdminOfferEditor } from './admin-offer-editor';
import { AdminProductGallery } from './admin-product-gallery';

const empty: ProductContent = { slug: '', name: '', description: { fa: '', en: '' }, category_id: '', brand: '', highlights: [] };
function SnapshotFields({ value, locale }: { value: Record<string, unknown>; locale: Locale }) {
  const labels: Record<string, [string, string]> = { name: ['نام محصول', 'Product name'], slug: ['نامک', 'URL slug'], description: ['توضیحات', 'Description'], category_id: ['شناسهٔ دسته', 'Category ID'], brand: ['برند', 'Brand'], highlights: ['ویژگی‌ها', 'Highlights'], status: ['وضعیت', 'Status'], version: ['نسخه', 'Revision'], on_hand: ['موجودی کل', 'Physical stock'], reserved: ['رزروشده', 'Reserved'], stock_verified: ['تأیید موجودی', 'Stock verified'], fa: ['فارسی', 'Persian'], en: ['انگلیسی', 'English'] };
  function display(item: unknown): string {
    if (item === null || item === undefined) return '—';
    if (typeof item === 'boolean') return item ? text(locale, 'بله', 'Yes') : text(locale, 'خیر', 'No');
    if (Array.isArray(item)) return item.map(display).join(' · ') || '—';
    if (typeof item === 'object') return Object.entries(item).map(([key, child]) => `${labels[key] ? text(locale, ...labels[key]) : key}: ${display(child)}`).join('\n');
    return String(item);
  }
  return <dl className="admin-snapshot">{Object.entries(value).map(([key, item]) => <div key={key}><dt>{labels[key] ? text(locale, ...labels[key]) : key}</dt><dd dir="auto">{display(item)}</dd></div>)}</dl>;
}
function content(product: AdminDetail): ProductContent {
  return { slug: product.slug, name: product.name, description: product.description, category_id: product.category_id, brand: product.brand, highlights: product.highlights };
}

export function AdminProductEditor({ id, locale }: { id: string; locale: Locale }) {
  const router = useRouter();
  const [product, setProduct] = useState<AdminDetail | null>(null);
  const [draft, setDraft] = useState<ProductContent>(empty);
  const [baseline, setBaseline] = useState<ProductContent>(empty);
  const [categories, setCategories] = useState<AdminCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const [stockDirty, setStockDirty] = useState(false);
  const [selectedVariant, setSelectedVariant] = useState('');
  const [selectedMarket, setSelectedMarket] = useState<'ir' | 'international'>('ir');
  const [editorEpoch, setEditorEpoch] = useState(0);
  const [comparison, setComparison] = useState<AdminDetail | null>(null);
  const [tab, setTab] = useState('content');
  const [attempt, setAttempt] = useState(0);
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  useEffect(() => {
    let alive = true;
    Promise.all([adminCategories(), id === 'new' ? Promise.resolve(null) : getAdminProduct(id)]).then(([groups, row]) => {
      if (!alive) return;
      setCategories(groups); setProduct(row); setDraft(row ? content(row) : empty); setBaseline(row ? content(row) : empty); setError(null);
    }).catch(e => { if (alive) setError(e); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [id, attempt]);
  useEffect(() => {
    if (!dirty && !stockDirty) return;
    const before = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    const navigation = (event: MouseEvent) => {
      const anchor = (event.target as Element).closest('a');
      if (!anchor || event.defaultPrevented || anchor.target === '_blank' || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      if (!window.confirm(text(locale, 'تغییرات ذخیره‌نشده کنار گذاشته شوند؟', 'Leave and discard unsaved changes?'))) { event.preventDefault(); event.stopPropagation(); }
    };
    window.addEventListener('beforeunload', before);
    document.addEventListener('click', navigation, true);
    return () => { window.removeEventListener('beforeunload', before); document.removeEventListener('click', navigation, true); };
  }, [dirty, stockDirty, locale]);
  function adopt(row: AdminDetail) { const next = content(row); setProduct(row); setDraft(next); setBaseline(next); setComparison(null); setEditorEpoch(value => value + 1); }
  function sectionChanged(value: boolean) { setStockDirty(value); setSaved(false); }
  function sectionSaved(row: AdminDetail, selectedId?: string, saved = true) { adopt(row); setStockDirty(false); setSaved(saved); setError(null); if (selectedId) setSelectedVariant(selectedId); }
  function update(next: Partial<ProductContent>) { setDraft(value => ({ ...value, ...next })); setSaved(false); }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null); setSaved(false);
    try {
      const body = { ...draft, highlights: (draft.highlights || []).map(line => line.trim()).filter(Boolean) };
      const row = product ? await saveAdminProduct(product.id, { ...body, expected_version: product.version }) : await createAdminProduct(body);
      adopt(row); setSaved(true);
      if (id === 'new') router.replace(`/${locale}/admin/products/${row.id}`);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function loadLatest() {
    if (!product) return;
    setBusy(true);
    try { setComparison(await getAdminProduct(product.id)); } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function changeStatus(status: AdminDetail['status']) {
    if (!product) return;
    setBusy(true); setError(null); setSaved(false);
    try { adopt(await setProductStatus(product, status)); setSaved(true); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  const publishable = Boolean(product?.image_ready && product.image && product.variants.length && !dirty);
  const title = product?.name || text(locale, 'محصول جدید', 'New product');
  return <>
    <nav className="admin-breadcrumb" data-unsaved={dirty || stockDirty} aria-label={text(locale, 'مسیر صفحه', 'Breadcrumb')}><Link href={`/${locale}/admin/products`}>{text(locale, 'محصولات', 'Products')}</Link><span>/</span><span>{text(locale, 'ویرایش محصول', 'Product editor')}</span></nav>
    <div className="admin-heading"><div><h1 dir="auto">{title}</h1><p>{text(locale, 'اطلاعات دقیق، انتخاب مطمئن‌تر.', 'Accurate details. Better-informed choices.')}</p></div>{product && <StatusBadge status={product.status} locale={locale}/>}</div>
    {loading ? <p role="status">{text(locale, 'در حال دریافت اطلاعات…', 'Loading product…')}</p> : <>
      <CatalogNotice error={error} locale={locale}/>
      {!!error && !product && id !== 'new' && <button className="button secondary" onClick={() => { setLoading(true); setAttempt(n => n + 1); }}>{text(locale, 'تلاش دوباره', 'Try again')}</button>}
      {!!error && product && <button className="button secondary" disabled={busy || stockDirty} onClick={() => void loadLatest()}>{text(locale, 'بارگیری نسخهٔ تازه برای مقایسه', 'Load latest version to compare')}</button>}
      {saved && <p role="status" className="admin-notice success"><CheckCircle2 size={20}/>{text(locale, 'تغییرات ذخیره شد.', 'Changes saved.')}</p>}
      {comparison && <section className="admin-panel admin-conflict"><h2>{text(locale, 'مقایسه با نسخهٔ فعلی', 'Compare with current version')}</h2><p>{text(locale, 'فرم شما هنوز تغییر نکرده است. نسخهٔ فعلی را بررسی کنید؛ پذیرش آن، فرم ذخیره‌نشده را جایگزین می‌کند.', 'Your draft has not changed. Review the current version; accepting it replaces your unsaved form.')}</p><div className="admin-conflict-columns"><div><h3>{text(locale, 'نوشتهٔ شما', 'Your draft')}</h3><SnapshotFields value={draft} locale={locale}/></div><div><h3>{text(locale, 'نسخهٔ فعلی', 'Current version')}</h3><SnapshotFields value={content(comparison)} locale={locale}/></div></div><button className="button secondary" onClick={() => { adopt(comparison); setError(null); }}>{text(locale, 'جایگزینی فرم با نسخهٔ فعلی', 'Replace form with current version')}</button></section>}
      {(product || id === 'new') && <>
        <div className="admin-tabs" role="tablist" onKeyDown={event => { if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return; const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")]; const index = buttons.indexOf(document.activeElement as HTMLButtonElement); const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (index + (event.key === "ArrowRight" ? (locale === "fa" ? -1 : 1) : (locale === "fa" ? 1 : -1)) + buttons.length) % buttons.length; event.preventDefault(); buttons[next]?.focus(); buttons[next]?.click(); }} aria-label={text(locale, 'بخش‌های محصول', 'Product sections')}>{[['content', text(locale, 'اطلاعات پایه', 'Basic information')], ['variants', text(locale, 'مدل و مشخصات', 'Models & specifications')], ['stock', text(locale, 'گونه‌ها و موجودی', 'Variants & stock')], ['prices', text(locale, 'قیمت بازارها', 'Market prices')], ['images', text(locale, 'تصاویر', 'Images')], ['history', text(locale, 'سابقهٔ تغییرات', 'Change history')]].map(([key, label]) => <button key={key} id={`tab-${key}`} role="tab" tabIndex={tab === key ? 0 : -1} aria-selected={tab === key} aria-controls={`panel-${key}`} disabled={busy || ((dirty || stockDirty) && key !== tab) || (key !== 'content' && !product)} onClick={() => { setTab(key); if (key !== 'variants' && selectedVariant === 'new') setSelectedVariant(''); setError(null); setComparison(null); setSaved(false); }}>{label}</button>)}</div>
        {tab === 'content' && <div id="panel-content" role="tabpanel" aria-labelledby="tab-content" className="admin-editor-layout">
          <form className="admin-panel admin-form" onSubmit={submit}><fieldset disabled={busy}>
            <div className="admin-panel-heading"><h2>{text(locale, 'اطلاعات محصول', 'Product information')}</h2>{dirty && <span>{text(locale, 'ذخیره‌نشده', 'Unsaved changes')}</span>}</div>
            <label>{text(locale, 'نام محصول و مدل', 'Product name and model')}<input value={draft.name} onChange={e => update({ name: e.target.value })} required maxLength={240} dir="auto"/></label>
            <div className="admin-form-grid"><label>{text(locale, 'نامک نشانی', 'URL slug')}<input aria-label={text(locale, 'نامک نشانی', 'URL slug')} aria-describedby="slug-help" value={draft.slug} onChange={e => update({ slug: e.target.value })} dir="ltr" required pattern="[a-z0-9]+(-[a-z0-9]+)*" maxLength={160}/><small id="slug-help">{text(locale, 'حروف کوچک انگلیسی، رقم و خط تیره؛ مانند gaming-keyboard.', 'Lowercase letters, digits and hyphens, such as gaming-keyboard.')}</small></label>
            <label>{text(locale, 'برند', 'Brand')}<input value={draft.brand || ''} onChange={e => update({ brand: e.target.value })} maxLength={120} dir="auto"/></label></div>
            <label>{text(locale, 'دسته‌بندی', 'Category')}<select required value={draft.category_id} onChange={e => update({ category_id: e.target.value })}><option value="">{text(locale, 'انتخاب دسته', 'Select category')}</option>{categories.map(category => <option key={category.id} value={category.id}>{category.name[locale]}</option>)}</select></label>
            <label>{text(locale, 'توضیحات فارسی', 'Persian description')}<textarea value={draft.description.fa} onChange={e => update({ description: { ...draft.description, fa: e.target.value } })} required maxLength={4000} dir="rtl" rows={5}/></label>
            <label>{text(locale, 'توضیحات انگلیسی', 'English description')}<textarea value={draft.description.en} onChange={e => update({ description: { ...draft.description, en: e.target.value } })} required maxLength={4000} dir="ltr" rows={5}/></label>
            <label>{text(locale, 'ویژگی‌های برجسته؛ هر مورد در یک خط', 'Highlights; one per line')}<textarea value={(draft.highlights || []).join('\n')} onChange={e => update({ highlights: e.target.value.split('\n') })} rows={4} maxLength={4820} dir="auto"/></label>
            <div className="admin-save-bar"><button className="button primary" disabled={!dirty || busy}><Save size={18}/>{busy ? text(locale, 'در حال ذخیره…', 'Saving…') : text(locale, 'ذخیرهٔ تغییرات', 'Save changes')}</button><span>{text(locale, 'ذخیرهٔ اطلاعات، وضعیت انتشار را تغییر نمی‌دهد.', 'Saving content does not change publication status.')}</span></div>
          </fieldset></form>
          <aside className="admin-editor-aside"><section className="admin-panel"><h2>{text(locale, 'آمادگی انتشار', 'Publication readiness')}</h2><ul className="admin-readiness"><Readiness ready={!!product}>{text(locale, 'اطلاعات پایهٔ ذخیره‌شده', 'Saved basic information')}</Readiness><Readiness ready={!!product?.variants.length}>{text(locale, 'حداقل یک گونهٔ معتبر', 'At least one valid variant')}</Readiness><Readiness ready={!!product?.image_ready}>{text(locale, 'تصویر آماده', 'Ready image')}</Readiness></ul>
          {product && <div className="admin-status-actions">{product.status !== 'published' && <ConfirmAction locale={locale} label={text(locale, 'انتشار محصول', 'Publish product')} title={text(locale, 'محصول منتشر شود؟', 'Publish this product?')} busy={!publishable || busy} onConfirm={() => changeStatus('published')}>{text(locale, 'محصول در کاتالوگ عمومی نمایش داده می‌شود. انتشار به معنی فعال‌شدن فروش نیست.', 'The product will appear in the public catalog. Publication does not enable purchasing.')}</ConfirmAction>}
          {product.status !== 'draft' && <ConfirmAction locale={locale} label={text(locale, 'بازگشت به پیش‌نویس', 'Return to draft')} title={text(locale, 'از نمایش عمومی خارج شود؟', 'Remove from public browsing?')} busy={dirty || busy} onConfirm={() => changeStatus('draft')}>{text(locale, 'اطلاعات حفظ می‌شود و محصول از فروشگاه پنهان خواهد شد.', 'Product data is preserved and the item is hidden from the storefront.')}</ConfirmAction>}
          {product.status !== 'archived' && <ConfirmAction locale={locale} label={text(locale, 'بایگانی محصول', 'Archive product')} title={text(locale, 'محصول بایگانی شود؟', 'Archive this product?')} busy={dirty || busy} onConfirm={() => changeStatus('archived')}>{text(locale, 'اطلاعات و سابقه حذف نمی‌شوند؛ محصول دیگر در فهرست عمومی دیده نمی‌شود.', 'Data and history are preserved; the product is no longer publicly listed.')}</ConfirmAction>}</div>}
          {dirty && <p className="admin-hint">{text(locale, 'پیش از تغییر وضعیت، ویرایش‌ها را ذخیره کنید.', 'Save content changes before changing status.')}</p>}</section>
          <section className="admin-panel admin-image-note"><Box size={30}/><h2>{text(locale, 'تصویر محصول', 'Product image')}</h2><p>{text(locale, 'در بخش تصاویر، فایل را همراه متن جایگزین بارگذاری کنید. تصویر پس از پردازش موفق آماده می‌شود.', 'Upload a file with alternative text in Images. It becomes ready after successful processing.')}</p></section></aside>
        </div>}
        {product && ['variants', 'stock', 'prices'].includes(tab) && <section id={`panel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`} className="admin-panel">
          <h2>{tab === 'variants' ? text(locale, 'مدل و مشخصات فنی', 'Models & technical specifications') : tab === 'prices' ? text(locale, 'قیمت مستقل بازارها', 'Independent market prices') : text(locale, 'گونه‌ها و موجودی', 'Variants & stock')}</h2>
          <p className="admin-hint">{text(locale, 'هر گونه یک شناسهٔ کالا دارد. مشخصات و موجودی آن مشترک است؛ قیمت هر بازار مستقل ثبت می‌شود.', 'Each variant has its own SKU. Its specifications and stock are shared; market prices are recorded separately.')}</p>
          <label className="admin-variant-picker">{text(locale, 'انتخاب گونه', 'Choose variant')}<select disabled={stockDirty || busy} value={selectedVariant || product.variants[0]?.id || 'new'} onChange={e => { setSelectedVariant(e.target.value); setSaved(false); }}>
            {product.variants.map(variant => <option key={variant.id} value={variant.id}>{variant.sku}</option>)}
            {tab === 'variants' && <option value="new">{text(locale, 'افزودن گونهٔ جدید', 'Add a new variant')}</option>}
          </select></label>
          {tab === 'variants' && <AdminVariantEditor key={`variant-${selectedVariant}-${editorEpoch}`} product={product} variant={product.variants.find(item => item.id === (selectedVariant || product.variants[0]?.id))} locale={locale} onDirty={sectionChanged} onSaved={sectionSaved}/>}
          {tab !== 'variants' && (product.variants.find(item => item.id === (selectedVariant || product.variants[0]?.id)) ? product.variants.filter(item => item.id === (selectedVariant || product.variants[0]?.id)).map(variant => tab === 'stock'
            ? <StockEditor key={`stock-${variant.id}-${editorEpoch}`} product={product} variant={variant} locale={locale} onDirty={sectionChanged} onSaved={row => sectionSaved(row)}/>
            : <AdminOfferEditor key={`offer-${variant.id}-${editorEpoch}`} product={product} variant={variant} market={selectedMarket} onMarketChange={setSelectedMarket} locale={locale} onDirty={sectionChanged} onSaved={sectionSaved}/>)
            : <p className="admin-notice"><AlertCircle size={20}/>{text(locale, 'ابتدا از بخش مدل و مشخصات یک گونه ذخیره یا انتخاب کنید.', 'First save or select a variant in Models & specifications.')}</p>)}
        </section>}
        {tab === 'images' && product && <section id="panel-images" role="tabpanel" aria-labelledby="tab-images"><AdminProductGallery product={product} locale={locale} onDirty={sectionChanged} onProduct={setProduct}/></section>}
        {tab === 'history' && product && <section id="panel-history" role="tabpanel" aria-labelledby="tab-history"><AuditHistory productId={product.id} locale={locale}/></section>}
      </>}
    </>}
  </>;
}

function StockEditor({ product, variant, locale, onSaved, onDirty }: { product: AdminDetail; variant: AdminDetail['variants'][number]; locale: Locale; onSaved: (row: AdminDetail) => void; onDirty: (dirty: boolean) => void }) {
  const [onHand, setOnHand] = useState(String(variant.on_hand));
  const [verified, setVerified] = useState(variant.stock_verified);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  async function save() {
    setBusy(true); setError(null);
    try { onSaved(await saveAdminStock(product.id, variant.id, { expected_version: product.version, expected_stock_version: variant.version, on_hand: Number(onHand), stock_verified: verified ?? false, reason: reason.trim() })); }
    catch (e) { setError(e); } finally { setBusy(false); dialog.current?.close(); }
  }
  return <form className="admin-stock-form admin-form" onChange={() => onDirty(true)} onSubmit={e => { e.preventDefault(); dialog.current?.showModal(); }}>
    <div className="admin-panel-heading"><h3><bdi dir="ltr">{variant.sku}</bdi></h3><span>{text(locale, `رزروشده: ${variant.reserved}`, `Reserved: ${variant.reserved}`)}</span></div>
    <p>{variant.packaging[locale]}</p><fieldset disabled={busy}><div className="admin-form-grid"><label>{text(locale, 'موجودی کل', 'Physical stock')}<input type="number" value={onHand} onChange={e => setOnHand(e.target.value)} min={variant.reserved} max={1000000} step={1} required dir="ltr"/></label><label>{text(locale, 'علت اصلاح موجودی', 'Stock adjustment reason')}<input value={reason} onChange={e => setReason(e.target.value)} required pattern=".*\S.*" maxLength={500}/></label></div><label className="admin-checkbox"><input type="checkbox" checked={verified} onChange={e => setVerified(e.target.checked)}/>{text(locale, 'موجودی بررسی و تأیید شده است', 'Physical stock has been verified')}</label><button className="button secondary" disabled={busy || (Number(onHand) === variant.on_hand && verified === variant.stock_verified)}>{text(locale, 'بررسی و ثبت موجودی', 'Review stock adjustment')}</button></fieldset><button type="button" className="text-link" disabled={busy} onClick={() => { setOnHand(String(variant.on_hand)); setVerified(variant.stock_verified); setReason(''); setError(null); onDirty(false); }}>{text(locale, 'کنارگذاشتن تغییرات موجودی', 'Discard stock changes')}</button><CatalogNotice error={error} locale={locale}/>
    {!!error && <button type="button" className="button secondary" disabled={busy} onClick={async () => { if (!window.confirm(text(locale, 'فرم موجودی با آخرین داده جایگزین شود؟', 'Replace this stock form with the latest data?'))) return; try { onSaved(await getAdminProduct(product.id)); } catch (e) { setError(e); } }}>{text(locale, 'بارگیری آخرین موجودی', 'Reload latest stock')}</button>}
    <dialog ref={dialog} className="feature-dialog" aria-label={text(locale, 'تأیید اصلاح موجودی', 'Confirm stock adjustment')}><div className="dialog-content"><h2>{text(locale, 'اصلاح موجودی ثبت شود؟', 'Save this stock adjustment?')}</h2><p><bdi>{variant.sku}</bdi></p><p>{text(locale, `موجودی کل: ${variant.on_hand} ← ${onHand}`, `Physical stock: ${variant.on_hand} → ${onHand}`)}</p><p>{reason}</p><div className="admin-actions"><button type="button" className="button secondary" disabled={busy} onClick={() => dialog.current?.close()}>{text(locale, 'انصراف', 'Cancel')}</button><button type="button" className="button primary" disabled={busy} onClick={() => void save()}>{text(locale, 'تأیید تغییر موجودی', 'Confirm stock change')}</button></div></div></dialog>
  </form>;
}

function AuditHistory({ productId, locale }: { productId: string; locale: Locale }) {
  const [data, setData] = useState<AuditPage | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => { let alive = true; productAudit(productId, page).then(value => { if (alive) { setData(value); setError(null); } }).catch(e => { if (alive) { setError(e); setData(null); } }).finally(() => { if (alive) setLoading(false); }); return () => { alive = false; }; }, [productId, page, attempt]);
  const actions: Record<string, [string, string]> = { 'image.queued': ['بارگذاری تصویر', 'Image uploaded'], 'image.activated': ['فعال‌شدن تصویر', 'Image activated'], 'image.removed': ['حذف تصویر از گالری', 'Image removed'], 'image.moved': ['تغییر ترتیب تصاویر', 'Image reordered'], 'product.created': ['ایجاد محصول', 'Product created'], 'product.edited': ['ویرایش اطلاعات', 'Content edited'], 'product.status_changed': ['تغییر وضعیت انتشار', 'Publication changed'], 'variant.created': ['افزودن گونه', 'Variant added'], 'variant.edited': ['ویرایش گونه', 'Variant edited'], 'stock.adjusted': ['اصلاح موجودی', 'Stock adjusted'], 'offer.changed': ['تغییر قیمت بازار', 'Market offer changed'] };
  return <div className="admin-panel"><h2>{text(locale, 'سابقهٔ تغییرات', 'Change history')}</h2><CatalogNotice error={error} locale={locale}/>{!!error && <button className="button secondary" onClick={() => { setLoading(true); setAttempt(n => n + 1); }}>{text(locale, 'تلاش دوباره', 'Try again')}</button>}{loading ? <p role="status">{text(locale, 'در حال دریافت سابقه…', 'Loading history…')}</p> : data && <>{!data.items.length && <p>{text(locale, 'هنوز تغییری از مدیریت ثبت نشده است.', 'No administration changes have been recorded yet.')}</p>}<ol className="admin-audit">{data.items.map(entry => <li key={entry.id}><strong>{actions[entry.action] ? text(locale, ...actions[entry.action]) : entry.action}</strong><time dateTime={entry.created_at}>{new Intl.DateTimeFormat(locale === 'fa' ? 'fa-IR' : 'en-US', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Tehran' }).format(new Date(entry.created_at))}</time><p>{entry.reason}</p><small>{text(locale, 'شناسهٔ مدیر:', 'Staff ID:')} <bdi>{entry.actor_id}</bdi></small><details><summary>{text(locale, 'مقادیر قبل و بعد', 'Before and after values')}</summary><div className="admin-conflict-columns"><SnapshotFields value={entry.before} locale={locale}/><SnapshotFields value={entry.after} locale={locale}/></div></details></li>)}</ol>{data.total > data.page_size && <div className="admin-pagination"><button className="button secondary" disabled={page <= 1} onClick={() => { setLoading(true); setPage(n => n - 1); }}><ChevronLeft size={16}/>{text(locale, 'قبلی', 'Previous')}</button><span>{page}</span><button className="button secondary" disabled={page * data.page_size >= data.total} onClick={() => { setLoading(true); setPage(n => n + 1); }}>{text(locale, 'بعدی', 'Next')}<ChevronRight size={16}/></button></div>}</>}</div>;
}
