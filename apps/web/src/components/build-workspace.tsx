'use client';
import { useRef, useState, useEffect } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import createClient from 'openapi-fetch';
import { Cpu, CircuitBoard, MemoryStick, HardDrive, Box, Zap, Fan, Monitor, Keyboard, Mouse, Headphones, Armchair, Plus, X, ShieldQuestion, CheckCircle2, AlertTriangle } from 'lucide-react';
import { usePreferences } from './preferences';
import { text, type Locale } from '@/lib/content';
import type { components, paths } from '@/lib/api/catalog-schema';
import { CartError, cartErrorCopy, openBuild, reviewGroup, reviewSavedBuild, saveBuild, saveGroup, transferBuild, type BuildReview, type Cart, type GroupEdit, type GroupReview, type SavedBuild } from '@/lib/cart-client';
import { buildsKey, cartKey, useCart } from './cart-query';

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
  const params = useSearchParams();
  const group = params.get('group');
  if (group) return <GroupWorkspace products={products} locale={locale} id={group} />;
  return <DraftWorkspace products={products} locale={locale} id={params.get('draft')} />;
}

function DraftWorkspace({products, locale, id}: {products: Product[]; locale: Locale; id: string | null}) {
  const { market } = usePreferences();
  const draft = useQuery({ queryKey: [...buildsKey(market), id], enabled: Boolean(id), queryFn: ({ signal }) => openBuild(id!, signal), refetchOnMount: 'always', refetchOnWindowFocus: false });
  if (id && (draft.isPending || (draft.isFetching && !draft.isFetchedAfterMount))) return <p role="status">{text(locale,'در حال بازکردن پیش‌نویس…','Opening saved build…')}</p>;
  if (id && (draft.isError || draft.data?.market !== market)) return <div className="workspace-panel">
    <p role="alert">{text(locale,'این پیش‌نویس در بازار یا نشست فعلی قابل بازکردن نیست.','This draft is unavailable in the current market or session.')}</p>
    <Link className="button secondary" href={`/${locale}/build/saved`}>{text(locale,'پیش‌نویس‌ها','Saved builds')}</Link>
  </div>;
  return <BuildEditor key={`${market}:${id ?? 'new'}`} products={products} locale={locale} draft={id ? draft.data : undefined} />;
}

type Group = Cart['groups'][number];

function groupSelections(cart: Cart, id: string): SavedBuild['selections'] {
  return cart.lines.flatMap(line => line.group_id === id && line.slot_key
    ? [{ slot_key: line.slot_key, variant_id: line.variant_id, quantity: line.quantity }]
    : []);
}

function GroupWorkspace({ products, locale, id }: { products: Product[]; locale: Locale; id: string }) {
  const { market } = usePreferences();
  const cart = useCart(market);
  const group = cart.data?.groups.find(item => item.id === id);
  if (cart.isPending) return <p role="status">{text(locale, 'در حال بازکردن سیستم…', 'Opening cart system…')}</p>;
  if (cart.isError || !cart.data || !group) return <div className="workspace-panel">
    <p role="alert">{text(locale, 'این سیستم در سبد بازار فعلی در دسترس نیست.', 'This system is unavailable in the current market cart.')}</p>
    <Link className="button secondary" href={`/${locale}/cart`}>{text(locale, 'بازگشت به سبد', 'Back to cart')}</Link>
  </div>;
  return <BuildEditor key={`${cart.data.id}:${group.id}`} products={products} locale={locale} groupEdit={{ cart: cart.data, group }} />;
}

function initialRows(selections: SavedBuild['selections'] = []): Row[] {
  const saved = selections.map(line => ({ key: line.slot_key, role: line.slot_key.split(':')[0] as Role, id: line.variant_id, quantity: line.quantity ?? 1 }));
  return [...saved, ...[...core, ...extra].filter(role => !saved.some(row => row.role === role)).map(role => ({ key: role, role, id: '', quantity: 1 }))];
}

function BuildEditor({ products, locale, draft, groupEdit }: { products: Product[]; locale: Locale; draft?: SavedBuild; groupEdit?: { cart: Cart; group: Group } }) {
  const { market } = usePreferences();
  const router = useRouter();
  const client = useQueryClient();
  const [base, setBase] = useState(groupEdit);
  const [rows,setRows] = useState<Row[]>(() => initialRows(groupEdit ? groupSelections(groupEdit.cart, groupEdit.group.id) : draft?.selections));
  const [dedicated,setDedicated] = useState(groupEdit?.group.requires_dedicated_gpu ?? draft?.requires_dedicated_gpu ?? false);
  const [mode,setMode] = useState<'complete_build'|'parts_only'>(groupEdit?.group.mode ?? draft?.mode ?? 'complete_build');
  const [name, setName] = useState(groupEdit?.group.name ?? draft?.name ?? '');
  const [groupReport, setGroupReport] = useState<{ proposal: GroupEdit; review: GroupReview }>();
  const [saved, setSaved] = useState(draft);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState<Error | null>(null);
  const [receipt, setReceipt] = useState(false);
  const [ambiguous, setAmbiguous] = useState<BuildReview>();
  const transferAttempt = useRef<{ digest: string; key: string } | null>(null);
  const [response,setResponse] = useState<{key:string;data?:Evaluation;failed?:boolean}|null>(null);
  const [pending,setPending] = useState<string|null>(null);
  const request = useRef<AbortController|null>(null);
  useEffect(()=>()=>request.current?.abort(),[]);
  const choices = products.flatMap(p=>p.variants.filter(v=>v.specifications.kind!=='prebuilt').map(v=>({p,v,role:v.specifications.kind==='peripheral'?v.specifications.role:v.specifications.kind})));
  const selections: Selection[] = rows.filter(r=>r.id).map(r=>({slot_key:r.key,role:r.role,variant_id:r.id,quantity:r.quantity}));
  const content = { name: name.trim(), mode, requires_dedicated_gpu: dedicated, selections: selections.map(({ slot_key, variant_id, quantity }) => ({ slot_key, variant_id, quantity })) };
  const proposal = base && { ...content, market, expected_version: base.cart.version, expected_group_version: base.group.version };
  const currentGroupReport = groupReport && JSON.stringify(groupReport.proposal) === JSON.stringify(proposal) ? groupReport.review : undefined;
  const staleGroup = Boolean(base && groupEdit && (base.cart.version !== groupEdit.cart.version || base.group.version !== groupEdit.group.version));
  const normalize = (lines: SavedBuild['selections']) => lines.map(({ slot_key, variant_id, quantity }) => [slot_key, variant_id, quantity ?? 1]).sort((a, b) => String(a[0]).localeCompare(String(b[0])));
  const dirty = !saved || content.name !== saved.name || saved.mode !== mode || saved.requires_dedicated_gpu !== dedicated || JSON.stringify(normalize(saved.selections)) !== JSON.stringify(normalize(content.selections));
  const review = useQuery({ queryKey: [...buildsKey(market), 'review', saved?.id, saved?.version],
    queryFn: ({ signal }) => reviewSavedBuild(saved!.id, signal), enabled: Boolean(saved) && !dirty && !ambiguous, staleTime: 0 });
  const report = !dirty && review.data?.build.version === saved?.version ? ambiguous ?? review.data : undefined;
  const key = JSON.stringify([market,mode,dedicated,selections]);
  const result = response?.key===key ? response : null;
  let parts = 0, peripherals = 0, unpriced = 0, pricedParts = 0, pricedPeripherals = 0;
  for(const row of rows.filter(r=>r.id)) {
    const offer=choices.find(c=>c.v.id===row.id)?.v.offers?.find(o=>o.market===market);
    if(!offer) unpriced++;
    else if(extra.includes(row.role)) { peripherals+=offer.amount_minor*row.quantity; pricedPeripherals++; }
    else { parts+=offer.amount_minor*row.quantity; pricedParts++; }
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
      const {data,error}=await api.POST('/api/v1/catalog/build-evaluations',{body:{market,currency:market==='ir'?'IRR':'USD',mode,requires_dedicated_gpu:dedicated,selections,previous:prior?{selection_hash:prior.selection_hash,spec_versions:prior.spec_versions,ruleset_version:prior.ruleset_version}:null},signal:AbortSignal.any([controller.signal,AbortSignal.timeout(8000)])});
      if(!controller.signal.aborted) setResponse({key,data,failed:Boolean(error)});
    } catch { if(!controller.signal.aborted) setResponse({key,failed:true}); }
    finally { if(!controller.signal.aborted) setPending(null); }
  }

  async function persist() {
    setBusy(true); setSaveError(null); setReceipt(false);
    try {
      const next = await saveBuild(market, content, saved);
      setSaved(next);
      client.setQueryData([...buildsKey(market), next.id], next);
      void client.invalidateQueries({ queryKey: [...buildsKey(market), 'list'] });
      if (!draft) router.replace(`/${locale}/build?draft=${encodeURIComponent(next.id)}`);
    } catch (error) { setSaveError(error as Error); }
    finally { setBusy(false); }
  }

  function reloadGroup() {
    if (!groupEdit) return;
    setBase(groupEdit);
    setRows(initialRows(groupSelections(groupEdit.cart, groupEdit.group.id)));
    setName(groupEdit.group.name);
    setMode(groupEdit.group.mode);
    setDedicated(groupEdit.group.requires_dedicated_gpu);
    setGroupReport(undefined);
    setSaveError(null);
  }

  async function checkGroup() {
    if (!base || !proposal || busy || staleGroup) return;
    setBusy(true); setSaveError(null); setGroupReport(undefined);
    try { setGroupReport({ proposal, review: await reviewGroup(base.cart, base.group.id, proposal) }); }
    catch (error) { setSaveError(error as Error); void client.invalidateQueries({ queryKey: cartKey(market) }); }
    finally { setBusy(false); }
  }

  async function confirmGroup() {
    if (!base || !proposal || !currentGroupReport?.review_digest || busy || staleGroup) return;
    setBusy(true); setSaveError(null);
    try {
      await saveGroup(base.cart, base.group.id, proposal, currentGroupReport.review_digest);
      void client.invalidateQueries({ queryKey: cartKey(market) });
      router.replace(`/${locale}/cart`);
    } catch (error) {
      setSaveError(error as Error);
      setGroupReport(undefined);
      void client.invalidateQueries({ queryKey: cartKey(market) });
    } finally { setBusy(false); }
  }

  async function confirmTransfer(current: BuildReview) {
    if (!current.review_digest || busy) return;
    if (transferAttempt.current?.digest !== current.review_digest) {
      transferAttempt.current = { digest: current.review_digest, key: crypto.randomUUID() };
    }
    setBusy(true); setSaveError(null);
    try {
      await transferBuild(current, transferAttempt.current.key);
      setAmbiguous(undefined);
      setReceipt(true);
      void client.invalidateQueries({ queryKey: cartKey(market) });
      await review.refetch();
    } catch (error) {
      setSaveError(error as Error);
      if (error instanceof CartError && error.status === 409) {
        setAmbiguous(undefined);
        await review.refetch();
      } else if (!(error instanceof CartError) || error.status === 0 || error.status >= 500) {
        setAmbiguous(current);
      }
    } finally { setBusy(false); }
  }
  function renderRow(row:Row) {
    const available=choices.filter(c=>c.role===row.role);
    const selected=available.find(c=>c.v.id===row.id);
    const Icon=icons[row.role];
    return <div className="component-row" key={row.key}>
      <div className="component-name"><Icon size={26}/><label htmlFor={`slot-${row.key}`}>{label(row.role)}{row.key.includes(':')?<small>#{row.key.split(':')[1]}</small>:null}</label></div>
      <div className="component-selection"><select id={`slot-${row.key}`} value={row.id} onChange={e=>update(row.key,{id:e.target.value})} aria-describedby={`hint-${row.key}`}><option value="">{text(locale,'انتخاب قطعه','Choose a component')}</option>{row.id&&!selected&&<option value={row.id}>{text(locale,'قطعهٔ ذخیره‌شده در فهرست فعلی نیست','Saved component is missing from the current list')}</option>}{available.map(({p,v})=><option key={v.id} value={v.id}>{p.name} · {v.packaging[locale]}</option>)}</select><small id={`hint-${row.key}`}>{!available.length?text(locale,'هنوز محصول مستندی برای این بخش ثبت نشده است.','No documented products in this category yet.'):selected?<bdi>{selected.v.sku}</bdi>:text(locale,'مدل و بسته‌بندی را بررسی کن.','Check the exact model and packaging.')}</small></div>
      <div className="component-actions">{['memory','storage','accessory'].includes(row.role)&&row.id&&<label><span className="sr-only">{text(locale,'تعداد','Quantity')} {label(row.role)}</span><input aria-label={`${text(locale,'تعداد','Quantity')} ${label(row.role)}`} type="number" min={1} max={10} value={row.quantity} onChange={e=>update(row.key,{quantity:Math.max(1,Math.min(10,Math.floor(Number(e.target.value)||1)))})}/></label>}
        {(row.id||row.key.includes(':'))&&<button type="button" className="icon-button" aria-label={`${text(locale,'حذف','Remove')} ${label(row.role)}`} onClick={()=>row.key.includes(':')?setRows(items=>items.filter(r=>r.key!==row.key)):update(row.key,{id:''})}><X size={17}/></button>}</div>
    </div>;
  }
  return <>
    <div className="workspace-panel build-session">
      <label className="field"><span>{text(locale,'نام سیستم','Build name')}</span><input value={name} maxLength={100} disabled={busy || Boolean(ambiguous)} onChange={event => setName(event.target.value)} /></label>
      <div className="detail-actions">
        {base ? <>
          <button type="button" className="button primary" disabled={busy || staleGroup || !content.name} onClick={() => void checkGroup()}>{text(locale,'بازبینی تغییرات سیستم','Review system changes')}</button>
          <Link className="button secondary" href={`/${locale}/cart`}>{text(locale,'بازگشت به سبد','Back to cart')}</Link>
        </> : <>
          <button type="button" className="button primary" disabled={busy || !dirty || !content.name} onClick={() => void persist()}>{text(locale,'ذخیرهٔ پیش‌نویس','Save build')}</button>
          <Link className="button secondary" href={`/${locale}/build/saved`}>{text(locale,'پیش‌نویس‌ها','Saved builds')}</Link>
          {saved && <Link className="button secondary" href={`/${locale}/build`}>{text(locale,'سیستم جدید','New build')}</Link>}
        </>}
      </div>
      {saveError && <p role="alert">{cartErrorCopy(saveError, locale)}</p>}
      {staleGroup && <div className="cart-notice"><p role="alert">{text(locale, 'سبد تغییر کرده است. برای ادامه، ترکیب فعلی سبد را بارگیری کن.', 'The cart changed. Load its current configuration to continue.')}</p>
        <button type="button" className="button secondary" disabled={busy} onClick={reloadGroup}>{text(locale, 'بارگیری ترکیب فعلی و کنارگذاشتن ویرایش‌ها', 'Load current configuration and discard edits')}</button></div>}
      {currentGroupReport && !staleGroup && <section className="build-transfer" aria-label={text(locale, 'نتیجهٔ بازبینی سیستم', 'System change review')}>
        {currentGroupReport.evaluation && <><h3>{statuses[currentGroupReport.evaluation.status][locale === 'fa' ? 0 : 1]}</h3><ul>{currentGroupReport.evaluation.findings.map((finding, index) => <li key={`${finding.code}-${index}`}>{finding.message[locale]}</li>)}</ul></>}
        <ul>{currentGroupReport.lines.map(line => <li key={line.slot_key}><bdi>{line.summary?.name ?? line.slot_key}</bdi> · {line.summary?.offer ? money(line.summary.offer.amount_minor) : text(locale, 'قیمت نامشخص', 'Price unavailable')} · {line.status === 'available' ? text(locale, 'موجود', 'Available') : text(locale, 'نیاز به بررسی', 'Check availability')}</li>)}</ul>
        {currentGroupReport.blocker && <p role="alert">{text(locale, 'برای ثبت، نتیجهٔ سازگاری و موجودی اقلام را بررسی کن.', 'Resolve compatibility and availability before saving.')}</p>}
        {currentGroupReport.review_digest && <button type="button" className="button primary" disabled={busy} onClick={() => void confirmGroup()}>{text(locale, 'تأیید و ثبت تغییرات سیستم', 'Confirm system changes')}</button>}
      </section>}
      {saved && !dirty && <p role="status">{text(locale,'پیش‌نویس ذخیره شده است.','Build saved.')}</p>}
      {saved && !dirty && <section aria-label={text(locale,'بازبینی انتقال','Transfer review')} className="build-transfer">
        {review.isFetching && <p>{text(locale,'در حال بازبینی…','Checking the latest catalog…')}</p>}
        {review.isError && <p role="alert">{text(locale,'بازبینی در دسترس نیست.','The latest review is unavailable.')}</p>}
        {report?.evaluation && <><h3>{statuses[report.evaluation.status][locale === 'fa' ? 0 : 1]}</h3><ul>{report.evaluation.findings.map((finding, index) => <li key={`${finding.code}-${index}`}>{finding.message[locale]}</li>)}</ul></>}
        {report && <ul>{report.lines.map(line => <li key={line.slot_key}><bdi>{line.summary?.name ?? line.slot_key}</bdi> · {line.summary?.offer ? money(line.summary.offer.amount_minor) : text(locale,'قیمت نامشخص','Price unavailable')} · {line.status === 'available' ? text(locale,'موجود','Available') : text(locale,'نیاز به بررسی','Check availability')}</li>)}</ul>}
        {report?.blocker && <p>{text(locale,'برای انتقال، نتیجهٔ سازگاری و وضعیت اقلام را بررسی کن.','Review compatibility and item availability before transferring.')}</p>}
        {review.data && review.data.build.version !== saved.version && <p role="alert">{text(locale,'نسخهٔ پیش‌نویس تغییر کرده است. از فهرست دوباره باز کن.','The draft has changed. Reopen it from Saved builds.')}</p>}
        <div className="detail-actions"><button type="button" className="button secondary" disabled={busy || review.isFetching || Boolean(ambiguous)} onClick={() => void review.refetch()}>{text(locale,'بازبینی دوباره','Review again')}</button>
        {report?.review_digest && (!review.isError || ambiguous) && <button type="button" className="button primary" disabled={busy || review.isFetching} onClick={() => void confirmTransfer(report)}>{ambiguous ? text(locale,'بررسی نتیجهٔ درخواست قبلی','Retry the previous transfer') : text(locale,'تأیید و افزودن سیستم به سبد','Confirm and add system to cart')}</button>}</div>
        {receipt && <Link className="text-link" href={`/${locale}/cart`}>{text(locale,'سیستم به سبد اضافه شد. دیدن سبد','System added. View cart')}</Link>}
      </section>}
    </div>
    <fieldset className="build-editor-fields" disabled={busy || Boolean(ambiguous)}><div className="builder-layout"><div className="builder-main">
      <section className="workspace-panel"><div className="workspace-panel-heading"><h2>{text(locale,'قطعات اصلی','Core components')}</h2><span>{text(locale,'از پردازنده تا خنک‌کننده','FROM PROCESSOR TO COOLING')}</span></div>{rows.filter(r=>core.includes(r.role)).map(renderRow)}<div className="add-slots"><button type="button" className="text-link" onClick={()=>add('storage')} disabled={rows.length>=32}><Plus size={16}/>{text(locale,'درایو دیگر','Another drive')}</button><button type="button" className="text-link" onClick={()=>add('memory')} disabled={rows.length>=32}><Plus size={16}/>{text(locale,'کیت حافظهٔ دیگر','Another memory kit')}</button></div></section>
      <details className="workspace-panel optional-equipment"><summary>{text(locale,'تجهیزات جانبی اختیاری','Optional setup equipment')}</summary>{rows.filter(r=>extra.includes(r.role)).map(renderRow)}</details>
      <section className="workspace-panel build-intent"><h2>{text(locale,'نوع انتخاب','Build intent')}</h2><label className="radio-option"><input type="checkbox" checked={dedicated} onChange={e=>setDedicated(e.target.checked)}/>{text(locale,'برای کاربرد من کارت گرافیک مجزا لازم است','My workflow requires a dedicated graphics card')}</label><label className="field"><span>{text(locale,'حالت بررسی','Evaluation mode')}</span><select value={mode} onChange={e=>setMode(e.target.value as typeof mode)}><option value="complete_build">{text(locale,'سیستم کامل','Complete build')}</option><option value="parts_only">{text(locale,'فقط قطعات جداگانه','Parts only')}</option></select></label>{mode==='parts_only'&&<p>{text(locale,'انتخاب قطعات جداگانه، سازگار بودن یک سیستم کامل را تأیید نمی‌کند.','Choosing parts individually does not certify a compatible complete system.')}</p>}</section>
    </div><aside className="build-summary"><div className="build-summary-art"><Image src="/images/showroom.webp" alt={text(locale,'تصویر مفهومی؛ نمای دقیق انتخاب شما نیست','Concept illustration; not a render of your selected build')} fill sizes="(max-width:900px) 100vw, 30vw"/><span>{text(locale,'سیستم تو، انتخاب تو','YOUR BUILD. YOUR RULES.')}</span></div><div className="workspace-panel">
      <h2>{text(locale,'خلاصهٔ پیکربندی','Your configuration')}</h2><dl className="build-totals"><div><dt>{text(locale,'قطعات اصلی','Components')}</dt><dd><bdi>{pricedParts?money(parts):'—'}</bdi></dd></div><div><dt>{text(locale,'تجهیزات جانبی','Setup equipment')}</dt><dd><bdi>{pricedPeripherals?money(peripherals):'—'}</bdi></dd></div><div className="partial-total"><dt>{text(locale,'جمع جزئی مرجع','Partial reference total')}</dt><dd><bdi>{pricedParts+pricedPeripherals?money(parts+peripherals):'—'}</bdi></dd></div></dl>
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
    </div></aside></div></fieldset>
  </>;
}
