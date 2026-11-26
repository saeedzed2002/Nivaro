'use client';
import { useRef, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Cpu, CircuitBoard, MemoryStick, HardDrive, Box, Zap, Fan, Monitor, Keyboard, Mouse, Headphones, Armchair, Plus, X, ShoppingBag } from 'lucide-react';
import { usePreferences } from './preferences';
import { text, type Locale } from '@/lib/content';
import type { components } from '@/lib/api/catalog-schema';
import { addCartItems, CartError, cartErrorCopy, ensureCart, openBuild, reviewGroup, reviewSavedBuild, saveBuild, saveGroup, transferBuild, type BuildReview, type Cart, type GroupEdit, type GroupReview, type SavedBuild } from '@/lib/cart-client';
import { buildsKey, cartKey, useCart } from './cart-query';

type Product = components['schemas']['Product'];
type Selection = components['schemas']['Selection'];
type Role = Selection['role'];
type Row = { key: string; role: Role; id: string; quantity: number };
const core: Role[] = ['cpu','motherboard','memory','storage','gpu','case','psu','cooler'];
const extra: Role[] = ['monitor','keyboard','mouse','audio','chair','desk','accessory'];
const names: Record<Role,[string,string]> = {cpu:['پردازنده','Processor'],motherboard:['مادربرد','Motherboard'],memory:['رم','Memory'],storage:['ذخیره‌سازی','Storage'],gpu:['کارت گرافیک','Graphics card'],case:['کیس','Case'],psu:['پاور','Power supply'],cooler:['خنک‌کننده','Cooling'],monitor:['مانیتور','Monitor'],keyboard:['کیبورد','Keyboard'],mouse:['ماوس','Mouse'],audio:['صدا','Audio'],chair:['صندلی','Chair'],desk:['میز','Desk'],accessory:['لوازم جانبی','Accessory']};
const icons = {cpu:Cpu,motherboard:CircuitBoard,memory:MemoryStick,storage:HardDrive,gpu:Monitor,case:Box,psu:Zap,cooler:Fan,monitor:Monitor,keyboard:Keyboard,mouse:Mouse,audio:Headphones,chair:Armchair,desk:Box,accessory:Plus};
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
  const [name, setName] = useState(groupEdit?.group.name ?? draft?.name ?? '');
  const [groupReport, setGroupReport] = useState<{ proposal: GroupEdit; review: GroupReview }>();
  const [saved, setSaved] = useState(draft);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState<Error | null>(null);
  const [addedSelection, setAddedSelection] = useState<string>();
  const [cartError, setCartError] = useState<Error | null>(null);
  const [adding, setAdding] = useState(false);
  const cartAttempt = useRef<{ selection: string; cart: Cart } | null>(null);
  const groupAttempt = useRef<{ version: number; review: BuildReview; key: string } | null>(null);
  const choices = products.flatMap(p=>p.variants.filter(v=>v.specifications.kind!=='prebuilt').map(v=>({p,v,role:v.specifications.kind==='peripheral'?v.specifications.role:v.specifications.kind})));
  const selections: Selection[] = rows.filter(r=>r.id).map(r=>({slot_key:r.key,role:r.role,variant_id:r.id,quantity:r.quantity}));
  const content = { name: name.trim(), mode: 'parts_only' as const, requires_dedicated_gpu: false, selections: selections.map(({ slot_key, variant_id, quantity }) => ({ slot_key, variant_id, quantity })) };
  const proposal = base && { ...content, market, expected_version: base.cart.version, expected_group_version: base.group.version };
  const currentGroupReport = groupReport && JSON.stringify(groupReport.proposal) === JSON.stringify(proposal) ? groupReport.review : undefined;
  const staleGroup = Boolean(base && groupEdit && (base.cart.version !== groupEdit.cart.version || base.group.version !== groupEdit.group.version));
  const normalize = (lines: SavedBuild['selections']) => lines.map(({ slot_key, variant_id, quantity }) => [slot_key, variant_id, quantity ?? 1]).sort((a, b) => String(a[0]).localeCompare(String(b[0])));
  const dirty = !saved || content.name !== saved.name || JSON.stringify(normalize(saved.selections)) !== JSON.stringify(normalize(content.selections));
  const selectionKey = JSON.stringify([market, selections]);
  const choicesById = new Map(choices.map(choice => [choice.v.id, choice]));
  let total = 0, unpriced = 0;
  for(const row of selections) {
    const offer=choicesById.get(row.variant_id)?.v.offers?.find(o=>o.market===market);
    if(!offer) unpriced++;
    else total += offer.amount_minor * row.quantity;
  }
  const money = (value:number) => market==='ir'?`${new Intl.NumberFormat(locale).format(value/10)} ${text(locale,'تومان','toman')}`:new Intl.NumberFormat(locale,{style:'currency',currency:'USD'}).format(value/100);
  const label = (role:Role) => names[role][locale==='fa'?0:1];
  function update(key:string,changes:Partial<Row>) { setCartError(null); setRows(items=>items.map(row=>row.key===key?{...row,...changes}:row)); }
  function add(role:'storage'|'memory') { setRows(items=>{ if(items.length>=32) return items; const next=Math.max(0,...items.filter(r=>r.role===role).map(r=>Number(r.key.split(':')[1])||1))+1; return [...items,{key:`${role}:${next}`,role,id:'',quantity:1}]; }); }
  async function addSelection() {
    if (adding || !selections.length || unpriced) return;
    setAdding(true); setCartError(null);
    try {
      if (saved?.mode === 'parts_only' && !dirty) {
        const previous = groupAttempt.current;
        const attempt = previous?.version === saved.version ? previous : {
          version: saved.version, review: await reviewSavedBuild(saved.id), key: crypto.randomUUID(),
        };
        if (attempt.review.build.version !== saved.version) throw new CartError('build.review_changed', 409);
        groupAttempt.current = attempt;
        await transferBuild(attempt.review, attempt.key);
        groupAttempt.current = null;
      } else {
        // Keep the expected version across transport retries so a lost response cannot add twice.
        const current = cartAttempt.current;
        const cart = current?.selection === selectionKey ? current.cart : await ensureCart(market);
        cartAttempt.current = { selection: selectionKey, cart };
        await addCartItems(cart, selections.map(({ variant_id, quantity }) => ({ variant_id, quantity })));
      }
      setAddedSelection(selectionKey);
      cartAttempt.current = null;
    } catch (error) {
      setCartError(error as Error);
      if (error instanceof CartError && error.status > 0 && error.status < 500) {
        groupAttempt.current = null;
        if (error.status !== 409) cartAttempt.current = null;
      }
    } finally {
      void client.invalidateQueries({ queryKey: cartKey(market) });
      setAdding(false);
    }
  }

  async function persist() {
    setBusy(true); setSaveError(null);
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

  function renderRow(row:Row) {
    const available=choices.filter(c=>c.role===row.role && c.v.offers?.some(offer => offer.market === market));
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
      <label className="field"><span>{text(locale,'نام سیستم','Build name')}</span><input value={name} maxLength={100} disabled={busy || adding} onChange={event => setName(event.target.value)} /></label>
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
        <ul>{currentGroupReport.lines.map(line => <li key={line.slot_key}><bdi>{line.summary?.name ?? line.slot_key}</bdi> · {line.summary?.offer ? money(line.summary.offer.amount_minor) : text(locale, 'قیمت نامشخص', 'Price unavailable')} · {line.status === 'available' ? text(locale, 'موجود', 'Available') : text(locale, 'نیاز به بررسی', 'Check availability')}</li>)}</ul>
        {currentGroupReport.blocker && <p role="alert">{text(locale, 'وضعیت اقلام را در سبد بررسی کن.', 'Review item availability in the cart.')}</p>}
        {currentGroupReport.review_digest && <button type="button" className="button primary" disabled={busy} onClick={() => void confirmGroup()}>{text(locale, 'تأیید و ثبت تغییرات سیستم', 'Confirm system changes')}</button>}
      </section>}
      {saved && !dirty && <p role="status">{text(locale,'پیش‌نویس ذخیره شده است.','Build saved.')}</p>}
    </div>
    <fieldset className="build-editor-fields" disabled={busy || adding}><div className="builder-layout"><div className="builder-main">
      <section className="workspace-panel"><div className="workspace-panel-heading"><h2>{text(locale,'قطعات اصلی','Core components')}</h2><span>{text(locale,'از پردازنده تا خنک‌کننده','FROM PROCESSOR TO COOLING')}</span></div>{rows.filter(r=>core.includes(r.role)).map(renderRow)}<div className="add-slots"><button type="button" className="text-link" onClick={()=>add('storage')} disabled={rows.length>=32}><Plus size={16}/>{text(locale,'درایو دیگر','Another drive')}</button><button type="button" className="text-link" onClick={()=>add('memory')} disabled={rows.length>=32}><Plus size={16}/>{text(locale,'کیت حافظهٔ دیگر','Another memory kit')}</button></div></section>
      <details className="workspace-panel optional-equipment"><summary>{text(locale,'تجهیزات جانبی اختیاری','Optional setup equipment')}</summary>{rows.filter(r=>extra.includes(r.role)).map(renderRow)}</details>
    </div><aside className="build-summary"><div className="build-summary-art"><Image src="/images/showroom.webp" alt={text(locale,'تصویر مفهومی سیستم گیمینگ','Concept illustration of a gaming PC')} fill sizes="(max-width:900px) 100vw, 30vw"/><span>{text(locale,'سیستم تو، انتخاب تو','YOUR BUILD. YOUR RULES.')}</span></div><div className="workspace-panel">
      <h2>{text(locale,'خلاصهٔ انتخاب‌ها','Selected parts')}</h2>
      <dl className="build-totals" aria-live="polite">
        <div><dt>{text(locale,'تعداد قطعات','Parts selected')}</dt><dd>{new Intl.NumberFormat(locale).format(selections.reduce((count, item) => count + item.quantity, 0))}</dd></div>
        <div className="partial-total"><dt>{unpriced ? text(locale,'جمع قطعات دارای قیمت','Total for priced parts') : text(locale,'جمع قیمت قطعات','Parts total')}</dt><dd><bdi>{total ? money(total) : '—'}</bdi></dd></div>
      </dl>
      {unpriced > 0 && <p className="build-warning">{new Intl.NumberFormat(locale).format(unpriced)} {text(locale,'ردیف انتخاب‌شده در این بازار قیمت ندارد.','selected rows have no price in this market.')}</p>}
      {!selections.length && <p className="summary-note">{text(locale,'برای دیدن جمع قیمت، یک قطعه انتخاب کن.','Choose a part to see your total.')}</p>}
      {!base && <button type="button" className="button primary build-cart-button" disabled={!selections.length || Boolean(unpriced) || adding || addedSelection === selectionKey} onClick={() => void addSelection()}>
        <ShoppingBag size={20}/>{adding ? text(locale,'در حال افزودن…','Adding…') : text(locale,'افزودن به سبد خرید','Add to cart')}
      </button>}
      {cartError && <p role="alert">{cartErrorCopy(cartError, locale)} <Link className="text-link" href={`/${locale}/cart`}>{text(locale,'بررسی سبد','Check cart')}</Link></p>}
      {addedSelection === selectionKey && <p role="status">{text(locale,'قطعات به سبد اضافه شدند.','Parts added to your cart.')} <Link className="text-link" href={`/${locale}/cart`}>{text(locale,'دیدن سبد','View cart')}</Link></p>}
    </div></aside></div></fieldset>
  </>;
}
