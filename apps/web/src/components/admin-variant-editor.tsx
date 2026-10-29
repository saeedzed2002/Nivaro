'use client';

import { useState, type FormEvent } from 'react';
import { Plus, Save, Trash2 } from 'lucide-react';
import { getAdminProduct, saveAdminVariant, type AdminDetail, type AdminVariant, type Evidence, type VariantContent } from '@/lib/admin-catalog-client';
import { hardwareLabels, specFields, type HardwareKind, type SpecField } from '@/lib/admin-form-fields';
import { text, type Locale } from '@/lib/content';
import { CatalogNotice } from './admin-shared';

type CountRow = { name: string; count: string };
type FieldValue = string | CountRow[];
function initialFields(variant?: AdminVariant): Record<string, FieldValue> {
  if (!variant) return {};
  return Object.fromEntries(Object.entries(variant.specifications).filter(([key]) => key !== 'kind').map(([key, value]) => [key,
    value === null || value === undefined ? '' : Array.isArray(value) ? value.join('\n') : typeof value === 'object' ? Object.entries(value).map(([name, count]) => ({ name, count: String(count) })) : String(value),
  ]));
}
const blankEvidence = (): Evidence => ({ url: '', checked_on: '', note: '' });

export function EvidenceFields({ value, onChange, locale, label }: { value: Evidence; onChange: (value: Evidence) => void; locale: Locale; label: string }) {
  return <fieldset className="admin-evidence"><legend>{label}</legend>
    <label>{text(locale, 'نشانی منبع', 'Source URL')}<input type="url" value={value.url} onChange={e => onChange({ ...value, url: e.target.value })} required pattern="https?://.*" dir="ltr"/></label>
    <div className="admin-form-grid"><label>{text(locale, 'تاریخ بررسی (میلادی)', 'Checked on (Gregorian)')}<input type="date" value={value.checked_on} onChange={e => onChange({ ...value, checked_on: e.target.value })} required dir="ltr"/></label>
    <label>{text(locale, 'یادداشت منبع', 'Source note')}<input value={value.note} onChange={e => onChange({ ...value, note: e.target.value })} required pattern=".*\S.*" maxLength={500} dir="auto"/></label></div>
  </fieldset>;
}

function TechnicalField({ definition, value, onChange, locale }: { definition: SpecField; value: FieldValue; onChange: (next: FieldValue) => void; locale: Locale }) {
  const label = text(locale, definition.fa, definition.en);
  if (definition.type === 'counts') {
    const rows = Array.isArray(value) ? value : [];
    return <fieldset className="admin-counts"><legend>{label}</legend>
      {!rows.length && <p className="admin-hint">{text(locale, 'نامعلوم؛ فقط اطلاعات تأییدشده را وارد کنید.', 'Unknown; enter only verified facts.')}</p>}
      {rows.map((row, index) => <div className="admin-count-row" key={index}>
        <label>{text(locale, 'نام اتصال یا اندازه', 'Connector or form name')}<input value={row.name} required pattern=".*\S.*" maxLength={120} dir="ltr" onChange={e => onChange(rows.map((item, i) => i === index ? { ...item, name: e.target.value } : item))}/></label>
        <label>{text(locale, 'تعداد', 'Count')}<input type="number" value={row.count} min={1} max={1000000} step={1} required dir="ltr" onChange={e => onChange(rows.map((item, i) => i === index ? { ...item, count: e.target.value } : item))}/></label>
        <button className="icon-button" type="button" aria-label={text(locale, `حذف ردیف ${index + 1}`, `Remove row ${index + 1}`)} onClick={() => onChange(rows.filter((_, i) => i !== index))}><Trash2 size={17}/></button>
      </div>)}
      <button className="text-link" type="button" onClick={() => onChange([...rows, { name: '', count: '1' }])}>{text(locale, 'افزودن ردیف', 'Add row')}</button>
    </fieldset>;
  }
  const stringValue = typeof value === 'string' ? value : '';
  if (definition.type === 'boolean' || definition.options) {
    const options = definition.options || ['true', 'false'];
    const translations: Record<string, string> = { true: 'بله', false: 'خیر', air: 'بادی', liquid: 'مایع', monitor: 'مانیتور', keyboard: 'کیبورد', mouse: 'ماوس', audio: 'تجهیزات صوتی', chair: 'صندلی', desk: 'میز', accessory: 'لوازم جانبی' };
    return <label>{label}<select value={stringValue} required={definition.required} onChange={e => onChange(e.target.value)}><option value="">{text(locale, 'نامعلوم / انتخاب نشده', 'Unknown / not selected')}</option>{options.map(option => <option key={option} value={option}>{locale === 'fa' ? translations[option] || option : option === 'true' ? 'Yes' : option === 'false' ? 'No' : option}</option>)}</select></label>;
  }
  if (definition.type === 'list') return <label>{label}<textarea value={stringValue} onChange={e => onChange(e.target.value)} rows={3} maxLength={8000} dir="ltr" placeholder={text(locale, 'هر مقدار در یک خط؛ خالی یعنی نامعلوم', 'One value per line; leave blank if unknown')}/></label>;
  return <label>{label}<input type={definition.type === 'number' ? 'number' : 'text'} value={stringValue} onChange={e => onChange(e.target.value)} min={definition.type === 'number' ? 1 : undefined} max={definition.type === 'number' ? 1000000 : undefined} step={1} maxLength={240} required={definition.required} dir="ltr"/></label>;
}

export function AdminVariantEditor({ product, variant, locale, onDirty, onSaved }: { product: AdminDetail; variant?: AdminVariant; locale: Locale; onDirty: (value: boolean) => void; onSaved: (value: AdminDetail, selectedId?: string, saved?: boolean) => void }) {
  const [sku, setSku] = useState(variant?.sku || '');
  const [packaging, setPackaging] = useState(variant?.packaging || { fa: '', en: '' });
  const [kind, setKind] = useState<HardwareKind>(variant?.specifications.kind || 'cpu');
  const [fields, setFields] = useState(() => initialFields(variant));
  const [evidence, setEvidence] = useState<Evidence[]>(variant?.evidence || []);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [validation, setValidation] = useState('');
  function changed() { setDirty(true); onDirty(true); setValidation(''); }
  function discard() { setSku(variant?.sku || ''); setPackaging(variant?.packaging || { fa: '', en: '' }); setKind(variant?.specifications.kind || 'cpu'); setFields(initialFields(variant)); setEvidence(variant?.evidence || []); setDirty(false); onDirty(false); setError(null); setValidation(''); }
  async function submit(event: FormEvent) {
    event.preventDefault(); setValidation('');
    const specifications: Record<string, unknown> = { kind };
    for (const definition of specFields[kind]) {
      const value = fields[definition.key] || '';
      if (definition.type === 'counts') {
        const rows = Array.isArray(value) ? value : [];
        if (new Set(rows.map(row => row.name.trim())).size !== rows.length) { setValidation(text(locale, 'نام ردیف‌های اتصال یا اندازه نباید تکراری باشد.', 'Connector or form names must be unique within each field.')); return; }
        specifications[definition.key] = rows.length ? Object.fromEntries(rows.map(row => [row.name.trim(), Number(row.count)])) : null;
      } else {
        const raw = String(value).trim();
        specifications[definition.key] = definition.type === 'list' ? (raw ? raw.split('\n').map(line => line.trim()).filter(Boolean) : kind === 'prebuilt' ? [] : null)
          : !raw ? null : definition.type === 'boolean' ? raw === 'true' : definition.type === 'number' ? Number(raw) : raw;
      }
    }
    if (kind === 'prebuilt' && (specifications.component_descriptions as string[]).length > 32) { setValidation(text(locale, 'حداکثر ۳۲ توضیح قطعه مجاز است.', 'At most 32 component descriptions are allowed.')); return; }
    setBusy(true); setError(null);
    try {
      const row = await saveAdminVariant(product.id, variant?.id, { expected_version: product.version, sku, packaging, specifications: specifications as VariantContent['specifications'], evidence });
      onSaved(row, row.variants.find(item => item.sku === sku)?.id, true);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <form className="admin-form admin-variant-form" onSubmit={submit}>
    <fieldset disabled={busy}><div className="admin-form-grid">
      <label>{text(locale, 'شناسهٔ کالا', 'SKU')}<input value={sku} onChange={e => { setSku(e.target.value.toUpperCase()); changed(); }} required pattern="[A-Z0-9][A-Z0-9._-]*" maxLength={100} dir="ltr"/></label>
      <label>{text(locale, 'نوع قطعه', 'Hardware type')}<select value={kind} disabled={!!variant} onChange={e => { setKind(e.target.value as HardwareKind); setFields({}); changed(); }}>{(Object.keys(hardwareLabels) as HardwareKind[]).map(item => <option key={item} value={item}>{text(locale, ...hardwareLabels[item])}</option>)}</select></label>
      <label>{text(locale, 'شرح بسته‌بندی فارسی', 'Persian packaging')}<input value={packaging.fa} onChange={e => { setPackaging({ ...packaging, fa: e.target.value }); changed(); }} required pattern=".*\S.*" maxLength={4000} dir="rtl"/></label>
      <label>{text(locale, 'شرح بسته‌بندی انگلیسی', 'English packaging')}<input value={packaging.en} onChange={e => { setPackaging({ ...packaging, en: e.target.value }); changed(); }} required pattern=".*\S.*" maxLength={4000} dir="ltr"/></label>
    </div><h3>{text(locale, 'مشخصات فنی', 'Technical specifications')}</h3><p className="admin-hint">{text(locale, 'خالی یعنی نامعلوم؛ صفر یا حدس را جایگزین اطلاعات مفقود نکنید. نوع قطعه پس از ایجاد تغییر نمی‌کند.', 'Blank means unknown. Do not replace missing facts with zero or guesses. Hardware type cannot change after creation.')}</p>
    <div className="admin-spec-grid">{specFields[kind].map(definition => <TechnicalField key={`${kind}-${definition.key}`} definition={definition} value={fields[definition.key] || ''} locale={locale} onChange={value => { setFields(current => ({ ...current, [definition.key]: value })); changed(); }}/>)}</div>
    <h3>{text(locale, 'منابع مشخصات', 'Specification sources')}</h3><p className="admin-hint">{text(locale, 'نبود منبع به معنی تأیید سازگاری نیست. فقط منبعی را ثبت کنید که بررسی کرده‌اید.', 'Missing evidence does not establish compatibility. Record only sources you have checked.')}</p>
    {evidence.map((item, index) => <div className="admin-evidence-row" key={index}><EvidenceFields value={item} locale={locale} label={text(locale, `منبع ${index + 1}`, `Source ${index + 1}`)} onChange={value => { setEvidence(current => current.map((row, i) => i === index ? value : row)); changed(); }}/><button type="button" className="text-link" onClick={() => { setEvidence(current => current.filter((_, i) => i !== index)); changed(); }}>{text(locale, 'حذف منبع', 'Remove source')}</button></div>)}
    <button className="button secondary" type="button" disabled={evidence.length >= 20} onClick={() => { setEvidence(current => [...current, blankEvidence()]); changed(); }}><Plus size={16}/>{text(locale, 'افزودن منبع', 'Add source')}</button>
    <div className="admin-save-bar"><button className="button primary" disabled={busy || (!dirty && !!variant)}><Save size={17}/>{text(locale, 'ذخیرهٔ گونه', 'Save variant')}</button><button type="button" className="text-link" onClick={discard}>{text(locale, 'کنارگذاشتن تغییرات گونه', 'Discard variant changes')}</button></div></fieldset>
    {validation && <p role="alert" className="admin-notice error">{validation}</p>}<CatalogNotice error={error} locale={locale}/>
    {!!error && <button type="button" className="button secondary" disabled={busy} onClick={async () => { if (!window.confirm(text(locale, 'فرم گونه کنار گذاشته و اطلاعات تازه بارگیری شود؟', 'Discard the variant form and load current data?'))) return; try { onSaved(await getAdminProduct(product.id), variant?.id, false); } catch (e) { setError(e); } }}>{text(locale, 'بارگیری نسخهٔ تازهٔ گونه', 'Reload current variant')}</button>}
  </form>;
}
