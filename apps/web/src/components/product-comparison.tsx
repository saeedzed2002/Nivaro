'use client';
import { useEffect, useState } from 'react';
import { ProductArtwork } from './product-artwork';
import Link from 'next/link';
import createClient from 'openapi-fetch';
import { ArrowUpRight, Info, Scale } from 'lucide-react';
import { usePreferences } from './preferences';
import { text, type Locale } from '@/lib/content';
import { specLabel, specValue } from '@/lib/specifications';
import type { components, paths } from '@/lib/api/catalog-schema';

type Product = components['schemas']['Product'];
type Comparison = components['schemas']['Comparison'];
const api = createClient<paths>();
export function ProductComparison({ products, locale, initialSlug }: { products: Product[]; locale: Locale; initialSlug?: string }) {
  const { market } = usePreferences();
  const initial = products.find(p => p.slug === initialSlug) ?? products.find(p => p.category === 'cpu') ?? products[0];
  const preferred = (p?: Product) => p?.variants.find(v => v.offers?.some(o => o.market === market))?.id ?? p?.variants[0]?.id ?? '';
  const [category, setCategory] = useState(initial?.category ?? 'cpu');
  const [left, setLeft] = useState(preferred(initial));
  const [right, setRight] = useState(preferred(products.find(p => p.category === initial?.category && p.id !== initial?.id)));
  const [differences, setDifferences] = useState(false);
  const [result, setResult] = useState<{ key: string; data?: Comparison; failed?: boolean } | null>(null);
  const key = `${market}:${left}:${right}`;
  const canCompare = Boolean(left && right && left !== right);
  const current = result?.key === key ? result : null;
  useEffect(() => {
    if (!canCompare) return;
    const controller = new AbortController();
    api.POST('/api/v1/catalog/comparisons', { body: { market, currency: market === 'ir' ? 'IRR' : 'USD', variant_ids: [left,right] }, signal: controller.signal })
      .then(({ data, error }) => { if (!controller.signal.aborted) setResult({ key, data, failed: Boolean(error) }); })
      .catch(() => { if (!controller.signal.aborted) setResult({ key, failed: true }); });
    return () => controller.abort();
  }, [key, left, right, market, canCompare]);
  const options = products.filter(p => p.category === category).flatMap(p => p.variants.map(v => ({ p, v })));
  const selected = [left,right].map(id => options.find(o => o.v.id === id));
  const money = (minor: number, currency: 'USD' | 'IRR') => currency === 'USD' ? new Intl.NumberFormat(locale,{style:'currency',currency}).format(minor/100) : `${new Intl.NumberFormat(locale).format(minor/10)} ${text(locale,'تومان','toman')}`;
  return <>
    <div className="compare-toolbar"><label className="field"><span>{text(locale,'دستهٔ مقایسه','Comparison category')}</span><select value={category} onChange={e=>{setCategory(e.target.value);setLeft('');setRight('');}}>{[...new Set(products.map(p=>p.category))].map(c=><option key={c} value={c}>{({cpu:text(locale,'پردازنده','Processors'),gpu:text(locale,'گرافیک','Graphics'),pc:text(locale,'سیستم آماده','Prebuilt PCs'),keyboard:text(locale,'کیبورد','Keyboards'),motherboard:text(locale,'مادربرد','Motherboards'),memory:text(locale,'رم','Memory'),storage:text(locale,'ذخیره‌سازی','Storage'),case:text(locale,'کیس','Cases'),psu:text(locale,'پاور','Power supplies'),cooler:text(locale,'خنک‌کننده','Cooling')} as Record<string,string>)[c] ?? c}</option>)}</select></label><label className="radio-option"><input type="checkbox" checked={differences} onChange={e=>setDifferences(e.target.checked)}/>{text(locale,'فقط تفاوت‌ها','Differences only')}</label></div>
    <div className="comparison-grid">
      {[left,right].map((id,index)=><section className="compare-product" key={index}>
        <label className="field"><span>{index===0?text(locale,'محصول اول','First product'):text(locale,'محصول دوم','Second product')}</span><select value={id} onChange={e=>(index===0?setLeft:setRight)(e.target.value)}><option value="">{text(locale,'انتخاب محصول','Choose a product')}</option>{options.map(({p,v})=><option key={v.id} value={v.id} disabled={v.id===(index===0?right:left)}>{p.name} · {v.packaging[locale]}</option>)}</select></label>
        {selected[index] ? <><div className="compare-art"><ProductArtwork image={selected[index]!.p.image} locale={locale} sizes="(max-width:600px) 45vw, 35vw"/></div><h2><bdi>{selected[index]!.p.name}</bdi></h2><p>{selected[index]!.v.packaging[locale]}</p><Link className="text-link" href={`/${locale}/products/${selected[index]!.p.slug}`}>{text(locale,'جزئیات محصول','Product details')}<ArrowUpRight size={16}/></Link></> : <div className="compare-placeholder"><Scale size={40}/><p>{text(locale,'یک محصول از همین دسته انتخاب کن','Choose a product in this category')}</p></div>}
      </section>)}
    </div>
    <div className="comparison-status" role="status" aria-live="polite">{!canCompare ? text(locale,'برای مقایسه، دو انتخاب متفاوت از یک دسته لازم است.','Select two different variants in the same category.') : !current ? text(locale,'در حال دریافت مشخصات…','Loading specifications…') : current.failed ? text(locale,'مقایسه دریافت نشد. انتخاب‌ها را تغییر بده یا صفحه را دوباره بارگذاری کن.','Comparison could not be loaded. Change selections or reload to retry.') : null}</div>
    {current?.data && <div className="comparison-table-wrap" tabIndex={0} role="region" aria-label={text(locale,'جدول مقایسه','Comparison table')}><table className="comparison-table"><caption className="sr-only">{text(locale,'مقایسهٔ مشخصات ثبت‌شده','Recorded specification comparison')}</caption><thead><tr><th scope="col">{text(locale,'مشخصات','Specification')}</th>{current.data.columns.map(c=><th scope="col" key={c.variant.id}><bdi>{c.name}</bdi><small>{c.variant.packaging[locale]}</small></th>)}</tr></thead><tbody>
      <tr><th scope="row">{text(locale,'قیمت مرجع این بازار','This market’s reference price')}</th>{current.data.columns.map(c=><td key={c.variant.id}>{c.offer ? <><strong><bdi>{money(c.offer.amount_minor,c.offer.currency)}</bdi></strong><a className="source-link" href={c.offer.source.url} target="_blank" rel="noopener noreferrer">{c.offer.seller} ↗</a><small><bdi>{c.offer.source.checked_on}</bdi></small></> : text(locale,'نامشخص','Unknown')}</td>)}</tr>
      {current.data.rows.filter(r=>!differences||r.different).map(row=><tr key={row.key} className={row.different?'is-different':''}><th scope="row">{specLabel(row.key,locale)}</th>{row.values.map((value,index)=><td key={index}><bdi>{specValue(value,locale)}</bdi></td>)}</tr>)}
    </tbody></table>{differences&&!current.data.rows.some(r=>r.different)&&<p className="comparison-status">{text(locale,'در مشخصات ثبت‌شده تفاوتی وجود ندارد.','No differences in the recorded specifications.')}</p>}</div>}
    <p className="workspace-notice"><Info size={18}/>{text(locale,'مقادیر نامعلوم، صفر نیستند. این مقایسه برندهٔ کلی تعیین نمی‌کند؛ قیمت‌ها مرجعند و تصاویر، عکس دقیق مدل نیستند.','Unknown values are not zero. This comparison declares no overall winner. Prices are references and images are not exact-SKU photos.')}</p>
  </>;
}
