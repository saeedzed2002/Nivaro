'use client';

import { useRef, useState, type FormEvent } from 'react';
import { Save } from 'lucide-react';
import { getAdminProduct, saveAdminOffer, type AdminDetail, type AdminVariant, type Evidence, type OfferChange } from '@/lib/admin-catalog-client';
import { marketAmountInput, parseMarketAmount } from '@/lib/admin-form-fields';
import { text, type Locale } from '@/lib/content';
import { CatalogNotice } from './admin-shared';
import { EvidenceFields } from './admin-variant-editor';

type Market = OfferChange['market'];
export function AdminOfferEditor({ product, variant, locale, market, onMarketChange, onDirty, onSaved }: { product: AdminDetail; variant: AdminVariant; locale: Locale; market: Market; onMarketChange: (value: Market) => void; onDirty: (value: boolean) => void; onSaved: (value: AdminDetail, selectedId?: string, saved?: boolean) => void }) {
  const initial = (variant.offers || []).find(offer => offer.market === market);
  const [amount, setAmount] = useState(initial ? marketAmountInput(initial.amount_minor, market) : '');
  const [seller, setSeller] = useState(initial?.seller || '');
  const [source, setSource] = useState<Evidence>(initial?.source || { url: '', checked_on: '', note: '' });
  const [reference, setReference] = useState(initial?.reference_only ?? true);
  const [available, setAvailable] = useState(initial?.available_for_sale ?? false);
  const [reason, setReason] = useState('');
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [validation, setValidation] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);
  const offer = (variant.offers || []).find(row => row.market === market);
  const amountMinor = parseMarketAmount(amount, market);
  const eligible = product.status === 'published' && product.image_ready && variant.stock_verified;
  const unit = market === 'ir' ? text(locale, 'تومان', 'tomans') : text(locale, 'دلار', 'USD');
  const currentPrice = offer ? `${marketAmountInput(offer.amount_minor, market)} ${unit}` : text(locale, 'ثبت نشده', 'Not recorded');
  function changed() { setDirty(true); onDirty(true); setValidation(''); }
  function reset(next: Market) {
    const row = (variant.offers || []).find(item => item.market === next);
    onMarketChange(next); setAmount(row ? marketAmountInput(row.amount_minor, next) : ''); setSeller(row?.seller || ''); setSource(row?.source || { url: '', checked_on: '', note: '' }); setReference(row?.reference_only ?? true); setAvailable(row?.available_for_sale ?? false); setReason(''); setDirty(false); onDirty(false); setError(null); setValidation('');
  }
  function review(event: FormEvent) {
    event.preventDefault();
    if (amountMinor === null) { setValidation(text(locale, 'مبلغ مثبت وارد کنید؛ تومان بدون اعشار و دلار حداکثر دو رقم اعشار. جداکنندهٔ هزارگان مجاز نیست.', 'Enter a positive amount: whole tomans or dollars with at most two decimal places. No grouping separators.')); return; }
    dialog.current?.showModal();
  }
  async function save() {
    if (amountMinor === null) return;
    setBusy(true); setError(null);
    try { onSaved(await saveAdminOffer(product.id, variant.id, { expected_version: product.version, expected_price_version: offer?.price_version || 0, market, currency: market === 'ir' ? 'IRR' : 'USD', amount_minor: amountMinor, seller, source, reference_only: reference, available_for_sale: available, reason }), variant.id, true); }
    catch (e) { setError(e); } finally { setBusy(false); dialog.current?.close(); }
  }
  return <form className="admin-form admin-offer-form" onSubmit={review}>
    <label>{text(locale, 'بازار قیمت', 'Price market')}<select disabled={dirty || busy} value={market} onChange={e => reset(e.target.value as Market)}><option value="ir">{text(locale, 'ایران — تومان', 'Iran — tomans')}</option><option value="international">{text(locale, 'بین‌المللی — دلار', 'International — USD')}</option></select></label>
    <p className="admin-notice">{text(locale, 'هر بازار قیمت مستقلی دارد. تغییر زبان، واحد این فرم یا قیمت بازار دیگر را تغییر نمی‌دهد.', 'Each market has its own price. Changing language does not convert this form or update the other market.')}</p>
    <p className="admin-current-price">{text(locale, 'قیمت فعلی:', 'Current price:')} <bdi dir="ltr">{currentPrice}</bdi></p>
    <fieldset disabled={busy}><div className="admin-form-grid">
      <label>{market === 'ir' ? text(locale, 'مبلغ (تومان کامل)', 'Amount (whole tomans)') : text(locale, 'مبلغ (دلار)', 'Amount (USD)')}<input inputMode={market === 'ir' ? 'numeric' : 'decimal'} value={amount} onChange={e => { setAmount(e.target.value); changed(); }} required maxLength={18} dir="ltr" aria-describedby="offer-unit-help"/></label>
      <label>{text(locale, 'فروشنده', 'Seller')}<input value={seller} onChange={e => { setSeller(e.target.value); changed(); }} required pattern=".*\S.*" maxLength={120} dir="auto"/></label>
    </div><p id="offer-unit-help" className="admin-hint">{market === 'ir' ? text(locale, 'مبلغ را به تومان کامل وارد کنید؛ تبدیل به ریال فقط هنگام ذخیره انجام می‌شود.', 'Enter whole tomans; conversion to rials occurs only when saving.') : text(locale, 'حداکثر دو رقم اعشار؛ مانند 129.99 دلار. تبدیل نرخ ارز انجام نمی‌شود.', 'Up to two decimal places, such as 129.99 USD. No currency exchange conversion.')}</p>
    <EvidenceFields value={source} locale={locale} label={text(locale, 'منبع قیمت', 'Price source')} onChange={value => { setSource(value); changed(); }}/>
    <label className="admin-checkbox"><input type="checkbox" checked={reference} onChange={e => { setReference(e.target.checked); if (e.target.checked) setAvailable(false); changed(); }}/>{text(locale, 'فقط قیمت مرجع؛ غیرقابل فروش', 'Research reference only; not for sale')}</label>
    <label className="admin-checkbox"><input type="checkbox" checked={available} disabled={reference || (!eligible && !available)} onChange={e => { setAvailable(e.target.checked); changed(); }}/>{text(locale, 'عرضه برای فروش در این بازار', 'Offer for sale in this market')}</label>
    {!eligible && <p className="admin-hint">{text(locale, 'عرضه به محصول منتشرشده، تصویر آماده و موجودی بررسی‌شده نیاز دارد. این گزینه راه‌اندازی پرداخت یا ارسال بین‌المللی نیست.', 'Sale eligibility needs publication, a ready image and verified stock. This option does not activate payments or international fulfillment.')}</p>}
    <label>{text(locale, 'علت تغییر قیمت', 'Price change reason')}<input value={reason} onChange={e => { setReason(e.target.value); changed(); }} required pattern=".*\S.*" maxLength={500} dir="auto"/></label>
    <div className="admin-save-bar"><button className="button primary" disabled={!dirty || busy}><Save size={17}/>{text(locale, 'بررسی و ثبت قیمت', 'Review price change')}</button><button type="button" className="text-link" onClick={() => reset(market)}>{text(locale, 'کنارگذاشتن تغییرات قیمت', 'Discard price changes')}</button></div></fieldset>
    {validation && <p role="alert" className="admin-notice error">{validation}</p>}<CatalogNotice error={error} locale={locale}/>
    {!!error && <button type="button" className="button secondary" disabled={busy} onClick={async () => { if (!window.confirm(text(locale, 'فرم قیمت کنار گذاشته و قیمت فعلی بارگیری شود؟', 'Discard the price form and load the current price?'))) return; try { onSaved(await getAdminProduct(product.id), variant.id, false); } catch (e) { setError(e); } }}>{text(locale, 'بارگیری قیمت فعلی', 'Reload current price')}</button>}
    <dialog ref={dialog} className="feature-dialog" aria-label={text(locale, 'تأیید تغییر قیمت', 'Confirm price change')}><div className="dialog-content"><h2>{text(locale, 'قیمت این بازار تغییر کند؟', 'Change this market price?')}</h2><p><bdi>{variant.sku}</bdi> · {market === 'ir' ? text(locale, 'ایران', 'Iran') : text(locale, 'بین‌المللی', 'International')}</p><p><bdi dir="ltr">{currentPrice} → {amountMinor !== null ? marketAmountInput(amountMinor, market) : '—'} {unit}</bdi></p><p>{reference ? text(locale, 'قیمت مرجع؛ فروش غیرفعال', 'Reference price; sales disabled') : available ? text(locale, 'عرضه در این بازار فعال', 'Offered for sale in this market') : text(locale, 'قیمت ثبت‌شده؛ فروش غیرفعال', 'Recorded price; sales disabled')}</p><p>{reason}</p><div className="admin-actions"><button type="button" className="button secondary" disabled={busy} onClick={() => dialog.current?.close()}>{text(locale, 'انصراف', 'Cancel')}</button><button type="button" className="button primary" disabled={busy} onClick={() => void save()}>{text(locale, 'تأیید ثبت قیمت', 'Confirm price save')}</button></div></div></dialog>
  </form>;
}
