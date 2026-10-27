'use client';
import { useRef, useState, useEffect } from 'react';
import Image from 'next/image';
import createClient from 'openapi-fetch';
import { Cpu, CircuitBoard, MemoryStick, HardDrive, Box, Zap, Fan, Monitor, Keyboard, Mouse, Headphones, Armchair, Plus, X, ShieldQuestion, Info, CheckCircle2, AlertTriangle } from 'lucide-react';
import { usePreferences } from './preferences';
import { text, type Locale } from '@/lib/content';
import type { components, paths } from '@/lib/api/catalog-schema';

type Product = components['schemas']['Product'];
type Evaluation = components['schemas']['Evaluation'];
type Selection = components['schemas']['Selection'];
type Role = Selection['role'];
type Row = { key: string; role: Role; id: string; quantity: number };
const api = createClient<paths>();
const core: Role[] = ['cpu','motherboard','memory','storage','gpu','case','psu','cooler'];
const extra: Role[] = ['monitor','keyboard','mouse','audio','chair','desk','accessory'];
const names: Record<Role,[string,string]> = {cpu:['پردازنده','Processor'],motherboard:['مادربرد','Motherboard'],memory:['رم','Memory'],storage:['ذخیره‌سازی','Storage'],gpu:['کارت گرافیک','Graphics card'],case:['کیس','Case'],psu:['پاور','Power supply'],cooler:['خنک‌کننده','Cooling'],monitor:['مانیتور','Monitor'],keyboard:['کیبورد','Keyboard'],mouse:['ماوس','Mouse'],audio:['صدا','Audio'],chair:['صندلی','Chair'],desk:['میز','Desk'],accessory:['لوازم جانبی','Accessory']};
const icons = {cpu:Cpu,motherboard:CircuitBoard,memory:MemoryStick,storage:HardDrive,gpu:Monitor,case:Box,psu:Zap,cooler:Fan,monitor:Monitor,keyboard:Keyboard,mouse:Mouse,audio:Headphones,chair:Armchair,desk:Box,accessory:Plus};
const statuses = {compatible:['کنترل‌های اصلی گذرانده شد','Core checks passed'],incompatible:['قطعات ناسازگارند','Conflicting components'],incomplete:['انتخاب قطعات کامل نیست','Incomplete selection'],needs_review:['نیازمند بررسی بیشتر','Needs further review']};
export function BuildWorkspace({ products, locale }: {products:Product[];locale:Locale}) {
  const { market } = usePreferences();
  const [rows,setRows] = useState<Row[]>([...core,...extra].map(role=>({key:role,role,id:'',quantity:1})));
  const [dedicated,setDedicated] = useState(false);
  const [mode,setMode] = useState<'complete_build'|'parts_only'>('complete_build');
  const [response,setResponse] = useState<{key:string;data?:Evaluation;failed?:boolean}|null>(null);
  const [pending,setPending] = useState<string|null>(null);
  const request = useRef<AbortController|null>(null);
  useEffect(()=>()=>request.current?.abort(),[]);
  const choices = products.flatMap(p=>p.variants.filter(v=>v.specifications.kind!=='prebuilt').map(v=>({p,v,role:v.specifications.kind==='peripheral'?v.specifications.role:v.specifications.kind})));
  const selections: Selection[] = rows.filter(r=>r.id).map(r=>({slot_key:r.key,role:r.role,variant_id:r.id,quantity:r.quantity}));
  const key = JSON.stringify([market,mode,dedicated,selections]);
  const result = response?.key===key ? response : null;
  let parts = 0, peripherals = 0, unpriced = 0;
  for(const row of rows.filter(r=>r.id)) {
    const offer=choices.find(c=>c.v.id===row.id)?.v.offers?.find(o=>o.market===market);
    if(!offer) unpriced++;
    else if(extra.includes(row.role)) peripherals+=offer.amount_minor*row.quantity;
    else parts+=offer.amount_minor*row.quantity;
  }
  const money = (value:number) => market==='ir'?`${new Intl.NumberFormat(locale).format(value/10)} ${text(locale,'تومان','toman')}`:new Intl.NumberFormat(locale,{style:'currency',currency:'USD'}).format(value/100);
  const label = (role:Role) => names[role][locale==='fa'?0:1];
  function update(key:string,changes:Partial<Row>) { setRows(items=>items.map(row=>row.key===key?{...row,...changes}:row)); }
  function add(role:'storage'|'memory') { setRows(items=>{ if(items.length>=32) return items; const next=Math.max(0,...items.filter(r=>r.role===role).map(r=>Number(r.key.split(':')[1])||1))+1; return [...items,{key:`${role}:${next}`,role,id:'',quantity:1}]; }); }
  async function evaluate() {
    request.current?.abort(); const controller=new AbortController(); request.current=controller;
    setPending(key);
    const prior = response?.data;
    try {
      const {data,error}=await api.POST('/api/v1/catalog/build-evaluations',{body:{market,currency:market==='ir'?'IRR':'USD',mode,requires_dedicated_gpu:dedicated,selections,previous:prior?{selection_hash:prior.selection_hash,spec_versions:prior.spec_versions,ruleset_version:prior.ruleset_version}:null},signal:controller.signal});
      if(!controller.signal.aborted) setResponse({key,data,failed:Boolean(error)});
    } catch { if(!controller.signal.aborted) setResponse({key,failed:true}); }
    finally { if(!controller.signal.aborted) setPending(null); }
  }
  function renderRow(row:Row) {
    const available=choices.filter(c=>c.role===row.role);
    const selected=available.find(c=>c.v.id===row.id);
    const Icon=icons[row.role];
    return <div className="component-row" key={row.key}>
      <div className="component-name"><Icon size={26}/><label htmlFor={`slot-${row.key}`}>{label(row.role)}{row.key.includes(':')?<small>#{row.key.split(':')[1]}</small>:null}</label></div>
      <div className="component-selection"><select id={`slot-${row.key}`} value={row.id} onChange={e=>update(row.key,{id:e.target.value})} aria-describedby={`hint-${row.key}`}><option value="">{text(locale,'انتخاب قطعه','Choose a component')}</option>{available.map(({p,v})=><option key={v.id} value={v.id}>{p.name} · {v.packaging[locale]}</option>)}</select><small id={`hint-${row.key}`}>{!available.length?text(locale,'هنوز محصول مستندی برای این بخش ثبت نشده است.','No documented products in this category yet.'):selected?<bdi>{selected.v.sku}</bdi>:text(locale,'مدل و بسته‌بندی را بررسی کن.','Check the exact model and packaging.')}</small></div>
      <div className="component-actions">{['memory','storage','accessory'].includes(row.role)&&row.id&&<label><span className="sr-only">{text(locale,'تعداد','Quantity')} {label(row.role)}</span><input aria-label={`${text(locale,'تعداد','Quantity')} ${label(row.role)}`} type="number" min={1} max={10} value={row.quantity} onChange={e=>update(row.key,{quantity:Math.max(1,Math.min(10,Math.floor(Number(e.target.value)||1)))})}/></label>}
        {(row.id||row.key.includes(':'))&&<button type="button" className="icon-button" aria-label={`${text(locale,'حذف','Remove')} ${label(row.role)}`} onClick={()=>row.key.includes(':')?setRows(items=>items.filter(r=>r.key!==row.key)):update(row.key,{id:''})}><X size={17}/></button>}</div>
    </div>;
  }
  return <>
    <p className="workspace-notice"><Info size={18}/>{text(locale,'انتخاب‌ها در این صفحه موقت‌اند؛ ذخیره‌سازی حساب، سفارش و خدمات اسمبل فیزیکی هنوز فعال نیستند.','Selections on this page are temporary. Account saving, ordering and physical assembly services are not active.')}</p>
    <div className="builder-layout"><div className="builder-main">
      <section className="workspace-panel"><div className="workspace-panel-heading"><h2>{text(locale,'قطعات اصلی','Core components')}</h2><span>{text(locale,'از پردازنده تا خنک‌کننده','FROM PROCESSOR TO COOLING')}</span></div>{rows.filter(r=>core.includes(r.role)).map(renderRow)}<div className="add-slots"><button type="button" className="text-link" onClick={()=>add('storage')} disabled={rows.length>=32}><Plus size={16}/>{text(locale,'درایو دیگر','Another drive')}</button><button type="button" className="text-link" onClick={()=>add('memory')} disabled={rows.length>=32}><Plus size={16}/>{text(locale,'کیت حافظهٔ دیگر','Another memory kit')}</button></div></section>
      <details className="workspace-panel optional-equipment"><summary>{text(locale,'تجهیزات جانبی اختیاری','Optional setup equipment')}</summary>{rows.filter(r=>extra.includes(r.role)).map(renderRow)}</details>
      <section className="workspace-panel build-intent"><h2>{text(locale,'نوع انتخاب','Build intent')}</h2><label className="radio-option"><input type="checkbox" checked={dedicated} onChange={e=>setDedicated(e.target.checked)}/>{text(locale,'برای کاربرد من کارت گرافیک مجزا لازم است','My workflow requires a dedicated graphics card')}</label><label className="field"><span>{text(locale,'حالت بررسی','Evaluation mode')}</span><select value={mode} onChange={e=>setMode(e.target.value as typeof mode)}><option value="complete_build">{text(locale,'سیستم کامل','Complete build')}</option><option value="parts_only">{text(locale,'فقط قطعات جداگانه','Parts only')}</option></select></label>{mode==='parts_only'&&<p>{text(locale,'انتخاب قطعات جداگانه، سازگار بودن یک سیستم کامل را تأیید نمی‌کند.','Choosing parts individually does not certify a compatible complete system.')}</p>}</section>
    </div><aside className="build-summary"><div className="build-summary-art"><Image src="/images/showroom.webp" alt={text(locale,'تصویر مفهومی؛ نمای دقیق انتخاب شما نیست','Concept illustration; not a render of your selected build')} fill sizes="(max-width:900px) 100vw, 30vw"/><span>{text(locale,'سیستم تو، انتخاب تو','YOUR BUILD. YOUR RULES.')}</span></div><div className="workspace-panel">
      <h2>{text(locale,'خلاصهٔ پیکربندی','Your configuration')}</h2><dl className="build-totals"><div><dt>{text(locale,'قطعات اصلی','Components')}</dt><dd><bdi>{selections.length?money(parts):'—'}</bdi></dd></div><div><dt>{text(locale,'تجهیزات جانبی','Setup equipment')}</dt><dd><bdi>{selections.length?money(peripherals):'—'}</bdi></dd></div><div className="partial-total"><dt>{text(locale,'جمع جزئی مرجع','Partial reference total')}</dt><dd><bdi>{selections.length?money(parts+peripherals):'—'}</bdi></dd></div></dl>
      {unpriced>0&&<p className="build-warning">{new Intl.NumberFormat(locale).format(unpriced)} {text(locale,'انتخاب قیمت ندارد؛ جمع جزئی کامل نیست.','selections have no price; this subtotal is incomplete.')}</p>}
      <p className="summary-note">{text(locale,'این مبلغ قابل پرداخت نیست. موجودی، ارسال و مالیات هنگام خرید بررسی می‌شوند؛ خدمات اسمبل ارائه نمی‌شود.','This is not a payable quote. Stock, delivery and tax need checkout verification; assembly labor is not offered.')}</p>
      <button type="button" className="button primary evaluate-button" disabled={pending===key} onClick={evaluate}><ShieldQuestion size={20}/>{pending===key?text(locale,'در حال بررسی…','Evaluating…'):text(locale,'بررسی سازگاری','Check compatibility')}</button>
      <div className="evaluation-result" aria-live="polite" aria-busy={pending===key}>
        {!result&&<p>{text(locale,'برای این انتخاب‌ها هنوز نتیجهٔ معتبر نداریم.','These selections have no current evaluation yet.')}</p>}
        {result?.failed&&<p role="alert">{text(locale,'بررسی دریافت نشد؛ انتخاب‌ها حفظ شده‌اند. دوباره تلاش کن.','Evaluation could not be loaded. Your selections are preserved; please retry.')}</p>}
        {result?.data&&<><h3 className={`evaluation-status status-${result.data.status}`}>{result.data.status==='compatible'?<CheckCircle2 size={20}/>:<AlertTriangle size={20}/>} {statuses[result.data.status][locale==='fa'?0:1]}</h3>
          {result.data.estimated_power_w!==null&&<p>{text(locale,'پاور موردنیاز برآوردی با حاشیهٔ احتیاط:','Estimated PSU capacity with headroom:')} <bdi>{new Intl.NumberFormat(locale).format(result.data.estimated_power_w)} W</bdi></p>}
          {result.data.stale_reasons.length>0&&<p>{text(locale,'نتیجهٔ قبلی قدیمی بود؛ این بررسی با وضعیت فعلی انجام شد.','Previous evidence was stale; this evaluation uses the current state.')}</p>}
          <ul className="finding-list">{result.data.findings.map((f,i)=><li key={`${f.code}-${i}`} className={`finding-${f.status}`}><p>{f.message[locale]}</p><small>{f.corrective_action[locale]}</small>{f.evidence.slice(0,1).map(e=><a key={e.url} href={e.url} target="_blank" rel="noopener noreferrer">{text(locale,'منبع مشخصات','Specification source')} ↗</a>)}</li>)}</ul>
          <p className="summary-note">{text(locale,'موجودی رزرو نشده است. نتیجه با تغییر قطعه، بازار یا مشخصات نیازمند بررسی دوباره است.','No stock is reserved. Changing parts, market or specifications requires a fresh evaluation.')}</p></>}
      </div>
    </div></aside></div>
  </>;
}
